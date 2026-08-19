"""
The Harness — the knowledge-holder + memory agent.

This is the one object an application constructs. It wires together:

  * the multi-provider router (subscription + BYOK)
  * tiered memory (working / short-term / long-term / episodic)
  * the soul graph (durable structured knowledge)
  * the reasoning engine (Hermes-inspired strategies)
  * the immutable ledger (every action auditable)

Typical use::

    from noesis import Harness
    h = Harness.from_env()
    print(h.ask("What did I tell you about Rust?"))
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .config import HarnessConfig, load_config
from .memory.episodic import Episode
from .memory.manager import MemoryManager
from .providers.base import ChatResult
from .providers.registry import ProviderRouter
from .reasoning.engine import ReasoningEngine
from .reasoning.strategies import ReasoningTrace, Strategy
from .soul import SoulGraph


class Harness:
    def __init__(self, config: HarnessConfig):
        self.config = config
        self.router = ProviderRouter.from_configs(config.providers, config.priority)
        self.memory = MemoryManager(
            root=config.root,
            working_limit=config.working_limit,
            short_term_limit=config.short_term_limit,
        )
        self.soul = SoulGraph(storage_path=f"{config.root_path}/soul_graph.json")
        self.engine = ReasoningEngine(
            router=self.router,
            default_strategy=Strategy(config.default_strategy),
            default_model=config.default_model,
        )

    # ── construction ─────────────────────────────────────────────
    @classmethod
    def from_env(cls, config_path: Optional[str] = None) -> "Harness":
        return cls(load_config(config_path))

    # ── memory ───────────────────────────────────────────────────
    def remember(self, text: str, **metadata: Any):
        return self.memory.remember(text, metadata=metadata or None)

    def recall(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.memory.recall(query, top_k=top_k)

    # ── direct model access ──────────────────────────────────────
    def chat(
        self,
        messages: Iterable[Any],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **opts: Any,
    ) -> ChatResult:
        return self.router.chat(messages, provider=provider, model=model, **opts)

    # ── reasoning + memory, the main loop ────────────────────────
    def ask(
        self,
        query: str,
        strategy: Optional[Strategy] = None,
        remember: bool = True,
    ) -> ReasoningTrace:
        """Reason over ``query`` using recalled context, then persist the episode."""
        context = self.memory.context(query)
        trace = self.engine.reason(query, strategy=strategy, context=context)
        if remember:
            self.memory.record_episode(
                Episode(
                    query=query,
                    response=trace.answer,
                    trace_id=trace.id,
                    strategy=trace.strategy.value,
                    confidence=trace.confidence,
                    metadata={"provider": trace.provider} if trace.provider else {},
                )
            )
        return trace

    # ── introspection ────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "providers": self.router.describe(),
            "available_providers": self.router.available_providers(),
            "memory": self.memory.stats(),
            "soul": self.soul.get_stats(),
            "has_model": self.engine.has_model(),
        }
