"""
Provider base types.

The provider layer is the harness's single door to every model backend. Each
concrete provider is an *adapter* that can authenticate in one of two ways:

  * ``AuthMode.API_KEY``      — bring-your-own-key, a plain HTTP call.
  * ``AuthMode.SUBSCRIPTION`` — reuse an existing paid subscription by driving
                                the vendor's local CLI / OAuth session, so no
                                per-token API billing is incurred.

An adapter that supports both picks whichever is configured (subscription is
preferred by default because it is what the user is already paying for).

Everything here is stdlib-only and synchronous. Streaming is exposed as a
generator of text deltas so callers never depend on asyncio or aiohttp.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional


class AuthMode(str, enum.Enum):
    """How a provider proves who it is."""

    API_KEY = "api_key"          # BYOK — a key/token in config or env
    SUBSCRIPTION = "subscription"  # reuse a paid sub via its local CLI / OAuth


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request (network, auth, config)."""


@dataclass
class Message:
    """A single chat message. ``role`` is one of system/user/assistant/tool."""

    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


def normalize_messages(messages: Iterable[Any]) -> List[Message]:
    """Accept dicts or Message objects; return a clean list of Message."""
    out: List[Message] = []
    for m in messages:
        if isinstance(m, Message):
            out.append(m)
        elif isinstance(m, dict):
            out.append(Message(role=m.get("role", "user"), content=m.get("content", "")))
        else:
            raise TypeError(f"unsupported message type: {type(m)!r}")
    return out


@dataclass
class ChatResult:
    """The outcome of a (non-streaming) chat call."""

    text: str
    provider: str
    model: str
    auth_mode: AuthMode
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[Any] = None

    def __str__(self) -> str:  # convenient for REPL printing
        return self.text


@dataclass
class ProviderConfig:
    """Per-provider configuration, normally hydrated from :mod:`noesis.config`."""

    enabled: bool = True
    # BYOK
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    # Subscription (CLI-backed)
    cli_path: Optional[str] = None
    # Model selection
    default_model: Optional[str] = None
    # Which auth to prefer when both are usable.
    prefer: AuthMode = AuthMode.SUBSCRIPTION
    # Free-form escape hatch (organization headers, project ids, etc.)
    extra: Dict[str, Any] = field(default_factory=dict)


class Provider:
    """Abstract base every backend adapter implements.

    Subclasses set :attr:`name`, declare the auth modes they can offer via
    :meth:`supported_auth`, and implement :meth:`_chat_api` and/or
    :meth:`_chat_cli`. The public :meth:`chat` handles auth-mode selection so
    every adapter behaves identically to the router.
    """

    name: str = "base"
    #: Modes this adapter *implements*, regardless of what is configured.
    _api_capable: bool = False
    _cli_capable: bool = False

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig()

    # ── capability / availability ────────────────────────────────
    def supported_auth(self) -> List[AuthMode]:
        modes: List[AuthMode] = []
        if self._api_capable:
            modes.append(AuthMode.API_KEY)
        if self._cli_capable:
            modes.append(AuthMode.SUBSCRIPTION)
        return modes

    def usable_auth(self) -> List[AuthMode]:
        """Auth modes that are actually configured *and* implemented."""
        if not self.config.enabled:
            return []
        modes: List[AuthMode] = []
        if self._api_capable and self._has_api_key():
            modes.append(AuthMode.API_KEY)
        if self._cli_capable and self._has_cli():
            modes.append(AuthMode.SUBSCRIPTION)
        return modes

    def available(self) -> bool:
        return bool(self.usable_auth())

    def _has_api_key(self) -> bool:
        return bool(self.config.api_key)

    def _has_cli(self) -> bool:
        from .cli import which

        return bool(which(self.config.cli_path or self._default_cli()))

    def _default_cli(self) -> str:
        """The CLI executable name for subscription mode (override per adapter)."""
        return self.name

    # ── model ────────────────────────────────────────────────────
    def resolve_model(self, model: Optional[str]) -> str:
        m = model or self.config.default_model or self.default_model()
        if not m:
            raise ProviderError(f"{self.name}: no model specified and no default configured")
        return m

    def default_model(self) -> Optional[str]:
        return None

    def _select_auth(self, auth: Optional[AuthMode]) -> AuthMode:
        usable = self.usable_auth()
        if not usable:
            raise ProviderError(
                f"{self.name}: not configured — set an API key or install its CLI "
                f"(supported: {[m.value for m in self.supported_auth()]})"
            )
        if auth is not None:
            if auth not in usable:
                raise ProviderError(f"{self.name}: auth mode {auth.value} not usable")
            return auth
        if self.config.prefer in usable:
            return self.config.prefer
        return usable[0]

    # ── public API ───────────────────────────────────────────────
    def chat(
        self,
        messages: Iterable[Any],
        model: Optional[str] = None,
        auth: Optional[AuthMode] = None,
        **opts: Any,
    ) -> ChatResult:
        mode = self._select_auth(auth)
        msgs = normalize_messages(messages)
        mdl = self.resolve_model(model)
        if mode is AuthMode.API_KEY:
            return self._chat_api(msgs, mdl, **opts)
        return self._chat_cli(msgs, mdl, **opts)

    def stream(
        self,
        messages: Iterable[Any],
        model: Optional[str] = None,
        auth: Optional[AuthMode] = None,
        **opts: Any,
    ) -> Iterator[str]:
        """Yield text deltas. Default: fall back to a single non-streamed chunk."""
        result = self.chat(messages, model=model, auth=auth, **opts)
        yield result.text

    # ── adapter hooks ────────────────────────────────────────────
    def _chat_api(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        raise ProviderError(f"{self.name}: API-key chat not implemented")

    def _chat_cli(self, messages: List[Message], model: str, **opts: Any) -> ChatResult:
        raise ProviderError(f"{self.name}: subscription/CLI chat not implemented")

    # ── introspection ────────────────────────────────────────────
    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "supported_auth": [m.value for m in self.supported_auth()],
            "usable_auth": [m.value for m in self.usable_auth()],
            "available": self.available(),
            "default_model": self.config.default_model or self.default_model(),
        }
