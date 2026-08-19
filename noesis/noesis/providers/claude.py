"""
Claude provider — dual auth.

  * API key (BYOK): the Anthropic Messages API (``/v1/messages``), which has its
    own request/response shape distinct from OpenAI's.
  * Subscription: drive the ``claude`` CLI (Claude Code) in non-interactive
    ``-p/--print`` mode so an existing Claude subscription is used with no
    per-token API billing.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from .base import AuthMode, ChatResult, Message, Provider, ProviderError
from .cli import messages_to_prompt, run_cli, which
from .http import post_json, stream_sse

ANTHROPIC_VERSION = "2023-06-01"

# The Claude Code CLI accepts short aliases, not the full API model ids.
_CLI_MODEL_ALIASES = {
    "claude-3-5-sonnet-latest": "sonnet",
    "claude-3-5-haiku-latest": "haiku",
    "claude-3-opus-latest": "opus",
}


def _cli_model(model: str) -> str:
    if model in _CLI_MODEL_ALIASES:
        return _CLI_MODEL_ALIASES[model]
    # Collapse a full "claude-3-5-sonnet-..." id to its family alias when obvious.
    for family in ("opus", "sonnet", "haiku"):
        if family in model:
            return family
    return model


class ClaudeProvider(Provider):
    name = "claude"
    _api_capable = True
    _cli_capable = True

    api_base = "https://api.anthropic.com/v1"

    def default_model(self) -> Optional[str]:
        return "claude-3-5-sonnet-latest"

    def _default_cli(self) -> str:
        return "claude"

    # ── shared shaping ───────────────────────────────────────────
    def _split_system(self, messages: List[Message]):
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        turns = [m.to_dict() for m in messages if m.role != "system"]
        return system, turns

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.config.api_key or "",
            "anthropic-version": self.config.extra.get("version", ANTHROPIC_VERSION),
        }

    def _payload(self, messages: List[Message], model: str, stream: bool, opts: Dict[str, Any]) -> Dict[str, Any]:
        system, turns = self._split_system(messages)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": turns,
            "max_tokens": opts.get("max_tokens", 4096),
            "stream": stream,
        }
        if system:
            payload["system"] = system
        for key in ("temperature", "top_p", "stop_sequences"):
            if opts.get(key) is not None:
                payload[key] = opts[key]
        return payload

    # ── API-key mode ─────────────────────────────────────────────
    def _chat_api(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        url = f"{self.api_base}/messages"
        data = post_json(url, self._payload(messages, model, False, opts), self._headers())
        try:
            parts = data["content"]
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        except (KeyError, TypeError) as e:
            raise ProviderError(f"claude: unexpected response: {json.dumps(data)[:300]}") from e
        return ChatResult(
            text=text,
            provider=self.name,
            model=model,
            auth_mode=AuthMode.API_KEY,
            usage=data.get("usage", {}) or {},
            raw=data,
        )

    # ── subscription (Claude Code CLI) mode ──────────────────────
    def _chat_cli(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        cli = which(self.config.cli_path or self._default_cli()) or self._default_cli()
        prompt = messages_to_prompt(messages)
        # `claude -p` prints a single non-interactive completion to stdout.
        argv = [cli, "-p", "--model", _cli_model(model)]
        text = run_cli(argv, stdin_text=prompt)
        return ChatResult(text=text, provider=self.name, model=model, auth_mode=AuthMode.SUBSCRIPTION)

    # ── streaming (API mode only) ────────────────────────────────
    def stream(self, messages, model=None, auth=None, **opts) -> Iterator[str]:
        mode = self._select_auth(auth)
        if mode is not AuthMode.API_KEY:
            yield from super().stream(messages, model=model, auth=auth, **opts)
            return
        from .base import normalize_messages

        msgs = normalize_messages(messages)
        mdl = self.resolve_model(model)
        url = f"{self.api_base}/messages"
        for frame in stream_sse(url, self._payload(msgs, mdl, True, opts), self._headers()):
            try:
                event = json.loads(frame)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "content_block_delta":
                delta = event.get("delta", {}).get("text")
                if delta:
                    yield delta


class ClaudeCodeProvider(ClaudeProvider):
    """Subscription-first Claude: prefers the Claude Code CLI over the API."""

    name = "claude-code"

    def __init__(self, config=None):
        super().__init__(config)
        # This alias exists to make "use my Claude Code subscription" explicit.
        self.config.prefer = AuthMode.SUBSCRIPTION
