"""
OpenRouter provider — one API key, hundreds of models.

OpenRouter speaks the OpenAI ``/chat/completions`` contract, so this is a thin
subclass. BYOK only (OpenRouter is itself a key aggregator; there is no
"subscription CLI" to ride).
"""
from __future__ import annotations

from typing import Dict, Optional

from .openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    api_base = "https://openrouter.ai/api/v1"

    def default_model(self) -> Optional[str]:
        return "anthropic/claude-3.5-sonnet"

    def _headers(self) -> Dict[str, str]:
        headers = super()._headers()
        # OpenRouter uses these for rankings/attribution; harmless if unset.
        ref = self.config.extra.get("referer") or self.config.extra.get("http_referer")
        title = self.config.extra.get("title", "noesis")
        if ref:
            headers["HTTP-Referer"] = ref
        headers["X-Title"] = title
        return headers
