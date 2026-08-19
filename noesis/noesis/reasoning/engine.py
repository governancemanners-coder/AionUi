"""
Reasoning engine.

Binds a :class:`ProviderRouter` (optional) to the reasoning strategies and
exposes a single :meth:`reason` entry point. Strategy can be chosen explicitly
or via a ``cot:`` / ``react:`` / ``reflexion:`` / ``tot:`` prefix on the query.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..providers.base import ChatResult
from ..providers.registry import ProviderRouter
from .strategies import STRATEGIES, ReasoningTrace, Strategy


class ReasoningEngine:
    def __init__(
        self,
        router: Optional[ProviderRouter] = None,
        default_strategy: Strategy = Strategy.COT,
        default_model: Optional[str] = None,
    ):
        self.router = router
        self.default_strategy = default_strategy
        self.default_model = default_model

    def has_model(self) -> bool:
        return bool(self.router and self.router.available_providers())

    def complete(self, messages: List[Dict[str, str]], **opts: Any) -> ChatResult:
        if not self.router:
            raise RuntimeError("no provider router configured")
        return self.router.chat(messages, model=self.default_model, **opts)

    def reason(
        self,
        query: str,
        strategy: Optional[Strategy] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReasoningTrace:
        query, prefixed = self._parse_prefix(query)
        chosen = strategy or prefixed or self.default_strategy
        return STRATEGIES[chosen](self, query, context)

    @staticmethod
    def _parse_prefix(query: str):
        for strat in Strategy:
            tag = f"{strat.value}:"
            if query.lower().startswith(tag):
                return query[len(tag):].strip(), strat
        return query, None
