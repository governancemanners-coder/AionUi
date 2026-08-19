"""
Gemini provider — dual auth.

  * API key (BYOK): the Google Generative Language API
    (``/v1beta/models/{model}:generateContent``), with Gemini's own
    ``contents``/``parts`` request shape.
  * Subscription: drive the ``gemini`` CLI (Gemini Code Assist / Gemini CLI) so
    an existing Google AI subscription is used instead of API billing.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import AuthMode, ChatResult, Message, Provider, ProviderError
from .cli import messages_to_prompt, run_cli, which
from .http import post_json


class GeminiProvider(Provider):
    name = "gemini"
    _api_capable = True
    _cli_capable = True

    api_base = "https://generativelanguage.googleapis.com/v1beta"

    def default_model(self) -> Optional[str]:
        return "gemini-1.5-flash"

    def _default_cli(self) -> str:
        return "gemini"

    # ── API-key mode ─────────────────────────────────────────────
    def _to_contents(self, messages: List[Message]):
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        return system, contents

    def _chat_api(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        system, contents = self._to_contents(messages)
        url = f"{self.api_base}/models/{model}:generateContent?key={self.config.api_key}"
        payload: Dict[str, Any] = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        gen: Dict[str, Any] = {}
        if opts.get("temperature") is not None:
            gen["temperature"] = opts["temperature"]
        if opts.get("max_tokens") is not None:
            gen["maxOutputTokens"] = opts["max_tokens"]
        if gen:
            payload["generationConfig"] = gen
        data = post_json(url, payload)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"gemini: unexpected response: {json.dumps(data)[:300]}") from e
        return ChatResult(
            text=text,
            provider=self.name,
            model=model,
            auth_mode=AuthMode.API_KEY,
            usage=data.get("usageMetadata", {}) or {},
            raw=data,
        )

    # ── subscription (Gemini CLI) mode ───────────────────────────
    def _chat_cli(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        cli = which(self.config.cli_path or self._default_cli()) or self._default_cli()
        prompt = messages_to_prompt(messages)
        argv = [cli, "-m", model, "-p", prompt]
        text = run_cli(argv)
        return ChatResult(text=text, provider=self.name, model=model, auth_mode=AuthMode.SUBSCRIPTION)
