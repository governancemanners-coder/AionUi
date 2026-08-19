"""
OpenAI-compatible chat provider.

A large fraction of the ecosystem speaks the OpenAI ``/chat/completions`` shape:
OpenRouter, Moonshot/Kimi, Together, Groq, local Ollama, LM Studio, and most
"custom" endpoints. This one adapter covers all of them; concrete providers
subclass it only to set a name, default base URL, and default model.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from .base import AuthMode, ChatResult, Message, Provider, ProviderError
from .http import post_json, stream_sse


class OpenAICompatProvider(Provider):
    """Chat over the OpenAI ``/chat/completions`` contract (API-key mode)."""

    name = "openai-compat"
    _api_capable = True
    _cli_capable = False

    #: Default endpoint root, e.g. ``https://api.openai.com/v1``.
    api_base = "https://api.openai.com/v1"

    def _base_url(self) -> str:
        return (self.config.base_url or self.api_base).rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        headers.update(self.config.extra.get("headers", {}))
        return headers

    def _payload(self, messages: List[Message], model: str, stream: bool, opts: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
        }
        for key in ("temperature", "max_tokens", "top_p", "stop"):
            if key in opts and opts[key] is not None:
                payload[key] = opts[key]
        return payload

    def _chat_api(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        url = f"{self._base_url()}/chat/completions"
        data = post_json(url, self._payload(messages, model, False, opts), self._headers())
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{self.name}: unexpected response shape: {json.dumps(data)[:300]}") from e
        return ChatResult(
            text=text or "",
            provider=self.name,
            model=model,
            auth_mode=AuthMode.API_KEY,
            usage=data.get("usage", {}) or {},
            raw=data,
        )

    def stream(self, messages, model=None, auth=None, **opts) -> Iterator[str]:
        mode = self._select_auth(auth)
        if mode is not AuthMode.API_KEY:
            yield from super().stream(messages, model=model, auth=auth, **opts)
            return
        from .base import normalize_messages

        msgs = normalize_messages(messages)
        mdl = self.resolve_model(model)
        url = f"{self._base_url()}/chat/completions"
        for frame in stream_sse(url, self._payload(msgs, mdl, True, opts), self._headers()):
            try:
                delta = json.loads(frame)["choices"][0]["delta"].get("content")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue
            if delta:
                yield delta


class CustomProvider(OpenAICompatProvider):
    """A user-supplied OpenAI-compatible endpoint (self-hosted, proxy, gateway).

    ``base_url`` must be set in config. Works with Ollama's OpenAI-compatible
    ``/v1`` as well; leave the api_key blank for servers that don't need one.
    """

    name = "custom"

    def _headers(self) -> Dict[str, str]:
        # Custom / local endpoints frequently need no auth header.
        headers: Dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        headers.update(self.config.extra.get("headers", {}))
        return headers

    def _has_api_key(self) -> bool:
        # A custom endpoint is "configured" as soon as it has a base URL.
        return bool(self.config.base_url)
