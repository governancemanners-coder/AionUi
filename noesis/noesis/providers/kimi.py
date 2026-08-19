"""
Kimi / Moonshot provider — dual auth.

  * API key (BYOK): Moonshot exposes an OpenAI-compatible endpoint, so the HTTP
    path reuses :class:`OpenAICompatProvider`.
  * Subscription: drive the ``kimi`` CLI (Kimi Code) so an existing Kimi
    subscription is used instead of per-token API billing.

The vendor endpoint differs by region; ``.ai`` is the international host and
``.cn`` the mainland one — override ``base_url`` in config to switch.
"""
from __future__ import annotations

from typing import Any, List, Optional

from .base import AuthMode, ChatResult, Message
from .cli import messages_to_prompt, run_cli, which
from .openai_compat import OpenAICompatProvider


class KimiProvider(OpenAICompatProvider):
    name = "kimi"
    api_base = "https://api.moonshot.ai/v1"
    _api_capable = True
    _cli_capable = True

    def default_model(self) -> Optional[str]:
        return "kimi-k2-0711-preview"

    def _default_cli(self) -> str:
        return "kimi"

    def _has_cli(self) -> bool:
        return bool(which(self.config.cli_path or self._default_cli()))

    def _chat_cli(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        cli = which(self.config.cli_path or self._default_cli()) or self._default_cli()
        prompt = messages_to_prompt(messages)
        argv = [cli, "--model", model, "--print"]
        text = run_cli(argv, stdin_text=prompt)
        return ChatResult(text=text, provider=self.name, model=model, auth_mode=AuthMode.SUBSCRIPTION)
