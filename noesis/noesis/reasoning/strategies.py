"""
Reasoning strategies (Hermes-inspired).

Each strategy is a small function of ``(engine, query, context) -> ReasoningTrace``.
Strategies compose provider calls and memory recall into a thinking loop. When
no provider is configured they still produce a structured trace using a local
heuristic, so the harness is useful entirely offline.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Strategy(str, Enum):
    COT = "cot"          # Chain-of-Thought — linear step-by-step
    REACT = "react"      # Reason + Act loop
    REFLEXION = "reflexion"  # answer, self-critique, revise
    TOT = "tot"          # Tree-of-Thought — branch and pick


@dataclass
class Thought:
    kind: str            # THINK / ACT / OBS / CRITIQUE / ANSWER
    content: str
    at: float = field(default_factory=time.time)


@dataclass
class ReasoningTrace:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    strategy: Strategy = Strategy.COT
    thoughts: List[Thought] = field(default_factory=list)
    answer: str = ""
    confidence: float = 0.0
    provider: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def add(self, kind: str, content: str) -> None:
        self.thoughts.append(Thought(kind=kind, content=content))


SYSTEM_COT = (
    "You are a careful reasoning engine. Think step by step, then give a final "
    "answer on a line beginning 'ANSWER:'."
)
SYSTEM_REFLEXION = (
    "You are a self-correcting reasoner. Produce a draft answer, critique it for "
    "errors, then give a corrected final answer on a line beginning 'ANSWER:'."
)


def _extract_answer(text: str) -> str:
    for line in text.splitlines():
        if line.strip().upper().startswith("ANSWER:"):
            return line.split(":", 1)[1].strip()
    return text.strip()


def _context_prefix(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return ""
    bits: List[str] = []
    recall = context.get("recall") or []
    if recall:
        bits.append("Relevant memory:\n" + "\n".join(f"- {r['text']}" for r in recall[:5]))
    working = context.get("working") or []
    if working:
        bits.append("Recent notes:\n" + "\n".join(f"- {w}" for w in working[:5]))
    return "\n\n".join(bits)


def run_cot(engine: Any, query: str, context: Optional[Dict[str, Any]] = None) -> ReasoningTrace:
    trace = ReasoningTrace(query=query, strategy=Strategy.COT)
    prefix = _context_prefix(context)
    user = (prefix + "\n\n" + query).strip() if prefix else query
    if engine.has_model():
        trace.add("THINK", "Reasoning step by step with the model.")
        result = engine.complete([{"role": "system", "content": SYSTEM_COT}, {"role": "user", "content": user}])
        trace.provider = result.provider
        trace.add("THINK", result.text)
        trace.answer = _extract_answer(result.text)
        trace.confidence = 0.75
    else:
        trace.add("THINK", "No model configured — using local heuristic.")
        trace.answer = _heuristic_answer(query, context)
        trace.confidence = 0.3
    trace.add("ANSWER", trace.answer)
    return trace


def run_reflexion(engine: Any, query: str, context: Optional[Dict[str, Any]] = None) -> ReasoningTrace:
    trace = ReasoningTrace(query=query, strategy=Strategy.REFLEXION)
    prefix = _context_prefix(context)
    user = (prefix + "\n\n" + query).strip() if prefix else query
    if engine.has_model():
        draft = engine.complete(
            [{"role": "system", "content": "Give a concise draft answer."}, {"role": "user", "content": user}]
        )
        trace.provider = draft.provider
        trace.add("THINK", f"Draft: {draft.text}")
        revised = engine.complete(
            [
                {"role": "system", "content": SYSTEM_REFLEXION},
                {"role": "user", "content": user},
                {"role": "assistant", "content": draft.text},
                {"role": "user", "content": "Critique the draft and give a corrected ANSWER:."},
            ]
        )
        trace.add("CRITIQUE", revised.text)
        trace.answer = _extract_answer(revised.text)
        trace.confidence = 0.8
    else:
        trace.add("THINK", "No model — heuristic reflexion.")
        trace.answer = _heuristic_answer(query, context)
        trace.confidence = 0.3
    trace.add("ANSWER", trace.answer)
    return trace


def run_react(engine: Any, query: str, context: Optional[Dict[str, Any]] = None) -> ReasoningTrace:
    """ReAct loop: the engine may call registered tools between reasoning steps."""
    trace = ReasoningTrace(query=query, strategy=Strategy.REACT)
    prefix = _context_prefix(context)
    trace.add("THINK", "Assessing whether a tool is needed.")
    # Tool use is delegated to the engine; here we keep a single-pass fallback.
    if engine.has_model():
        user = (prefix + "\n\n" + query).strip() if prefix else query
        result = engine.complete(
            [
                {"role": "system", "content": "Reason about the task, act if needed, then ANSWER:."},
                {"role": "user", "content": user},
            ]
        )
        trace.provider = result.provider
        trace.add("ACT", "model_completion")
        trace.add("OBS", result.text)
        trace.answer = _extract_answer(result.text)
        trace.confidence = 0.7
    else:
        trace.add("OBS", "No model — heuristic.")
        trace.answer = _heuristic_answer(query, context)
        trace.confidence = 0.3
    trace.add("ANSWER", trace.answer)
    return trace


def run_tot(engine: Any, query: str, context: Optional[Dict[str, Any]] = None) -> ReasoningTrace:
    """Tree-of-Thought: sample a few branches, pick the most confident."""
    trace = ReasoningTrace(query=query, strategy=Strategy.TOT)
    if not engine.has_model():
        trace.add("THINK", "No model — heuristic single branch.")
        trace.answer = _heuristic_answer(query, context)
        trace.confidence = 0.3
        trace.add("ANSWER", trace.answer)
        return trace
    prefix = _context_prefix(context)
    user = (prefix + "\n\n" + query).strip() if prefix else query
    branches: List[str] = []
    for i in range(3):
        r = engine.complete(
            [
                {"role": "system", "content": f"Explore approach #{i + 1}. End with ANSWER:."},
                {"role": "user", "content": user},
            ],
            temperature=0.9,
        )
        trace.provider = r.provider
        branches.append(r.text)
        trace.add("THINK", f"Branch {i + 1}: {_extract_answer(r.text)}")
    # Pick the longest-reasoned branch as a cheap proxy for the strongest one.
    best = max(branches, key=len)
    trace.answer = _extract_answer(best)
    trace.confidence = 0.72
    trace.add("ANSWER", trace.answer)
    return trace


def _heuristic_answer(query: str, context: Optional[Dict[str, Any]]) -> str:
    """Offline fallback: surface the best memory hit, else restate the question."""
    if context:
        recall = context.get("recall") or []
        if recall:
            return f"From memory: {recall[0]['text']}"
    return f"(no model configured) I recorded your query: {query!r}"


STRATEGIES = {
    Strategy.COT: run_cot,
    Strategy.REACT: run_react,
    Strategy.REFLEXION: run_reflexion,
    Strategy.TOT: run_tot,
}
