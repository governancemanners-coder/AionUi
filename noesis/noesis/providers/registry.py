"""
Provider registry + router.

The registry knows every provider class, instantiates the ones the user has
configured, and routes a chat request to the right backend. It supports:

  * explicit selection   — ``router.chat(..., provider="kimi")``
  * ``provider/model``    — ``router.chat(..., model="openrouter/anthropic/claude-3.5-sonnet")``
  * automatic selection   — first available provider in the configured priority
  * fallback chains       — try each provider in order until one succeeds
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional, Type

from .base import ChatResult, Provider, ProviderConfig, ProviderError
from .claude import ClaudeCodeProvider, ClaudeProvider
from .gemini import GeminiProvider
from .kimi import KimiProvider
from .openai_compat import CustomProvider
from .openrouter import OpenRouterProvider

#: Every provider class the harness ships with, by canonical name.
PROVIDER_CLASSES: Dict[str, Type[Provider]] = {
    OpenRouterProvider.name: OpenRouterProvider,
    ClaudeProvider.name: ClaudeProvider,
    ClaudeCodeProvider.name: ClaudeCodeProvider,
    KimiProvider.name: KimiProvider,
    GeminiProvider.name: GeminiProvider,
    CustomProvider.name: CustomProvider,
}

#: Default order for "auto" selection — subscription-friendly first.
DEFAULT_PRIORITY = ["claude-code", "kimi", "gemini", "claude", "openrouter", "custom"]


class ProviderRouter:
    def __init__(
        self,
        providers: Optional[Dict[str, Provider]] = None,
        priority: Optional[List[str]] = None,
    ):
        self.providers: Dict[str, Provider] = providers or {}
        self.priority = priority or DEFAULT_PRIORITY

    # ── construction ─────────────────────────────────────────────
    @classmethod
    def from_configs(
        cls,
        configs: Dict[str, ProviderConfig],
        priority: Optional[List[str]] = None,
    ) -> "ProviderRouter":
        providers: Dict[str, Provider] = {}
        for name, cfg in configs.items():
            klass = PROVIDER_CLASSES.get(name)
            if klass is None:
                raise ProviderError(f"unknown provider {name!r}; known: {sorted(PROVIDER_CLASSES)}")
            providers[name] = klass(cfg)
        return cls(providers, priority)

    def register(self, provider: Provider) -> None:
        self.providers[provider.name] = provider

    # ── selection ────────────────────────────────────────────────
    def available_providers(self) -> List[str]:
        return [n for n, p in self.providers.items() if p.available()]

    def _split_model(self, model: Optional[str]):
        """Return ``(provider_name_or_None, model_or_None)`` from ``provider/model``."""
        if model and "/" in model:
            head, tail = model.split("/", 1)
            if head in self.providers:
                return head, tail
        return None, model

    def select(self, provider: Optional[str] = None, model: Optional[str] = None) -> Provider:
        prov_from_model, _ = self._split_model(model)
        name = provider or prov_from_model
        if name:
            p = self.providers.get(name)
            if p is None:
                raise ProviderError(f"provider {name!r} not configured")
            if not p.available():
                raise ProviderError(f"provider {name!r} is configured but not usable (no key/CLI)")
            return p
        # auto: first available in priority order, then any available
        for candidate in self.priority:
            p = self.providers.get(candidate)
            if p and p.available():
                return p
        for p in self.providers.values():
            if p.available():
                return p
        raise ProviderError(
            "no provider is usable — configure an API key or install a provider CLI"
        )

    # ── requests ─────────────────────────────────────────────────
    def chat(
        self,
        messages: Iterable[Any],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **opts: Any,
    ) -> ChatResult:
        p = self.select(provider, model)
        _, bare_model = self._split_model(model)
        return p.chat(messages, model=bare_model, **opts)

    def stream(
        self,
        messages: Iterable[Any],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **opts: Any,
    ) -> Iterator[str]:
        p = self.select(provider, model)
        _, bare_model = self._split_model(model)
        return p.stream(messages, model=bare_model, **opts)

    def chat_with_fallback(
        self,
        messages: Iterable[Any],
        chain: Optional[List[str]] = None,
        model: Optional[str] = None,
        **opts: Any,
    ) -> ChatResult:
        """Try providers in ``chain`` (or priority order) until one succeeds."""
        order = chain or [n for n in self.priority if n in self.providers]
        errors: List[str] = []
        for name in order:
            p = self.providers.get(name)
            if not p or not p.available():
                continue
            try:
                return p.chat(messages, model=self._split_model(model)[1], **opts)
            except ProviderError as e:  # pragma: no cover - network dependent
                errors.append(f"{name}: {e}")
        raise ProviderError("all providers in fallback chain failed:\n" + "\n".join(errors))

    def describe(self) -> List[Dict[str, Any]]:
        return [p.describe() for p in self.providers.values()]
