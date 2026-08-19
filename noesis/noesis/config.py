"""
Configuration for the harness.

Config can come from three layers, later ones winning:

  1. built-in defaults
  2. a config file (``~/.noesis/config.json`` or ``.yaml``)
  3. environment variables (BYOK keys, CLI paths)

The result is a set of :class:`ProviderConfig` objects plus harness settings.
Environment auto-detection means "export your keys and go" works with no file.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .providers.base import AuthMode, ProviderConfig

DEFAULT_ROOT = os.environ.get("NOESIS_HOME", "~/.noesis")

# env var -> (provider, field). API keys enable BYOK mode for a provider.
_API_KEY_ENV = {
    "OPENROUTER_API_KEY": "openrouter",
    "ANTHROPIC_API_KEY": "claude",
    "MOONSHOT_API_KEY": "kimi",
    "KIMI_API_KEY": "kimi",
    "GEMINI_API_KEY": "gemini",
    "GOOGLE_API_KEY": "gemini",
}

# provider -> CLI executable that, if present, enables subscription mode.
_CLI_ENV = {
    "claude-code": ("CLAUDE_CLI", "claude"),
    "claude": ("CLAUDE_CLI", "claude"),
    "kimi": ("KIMI_CLI", "kimi"),
    "gemini": ("GEMINI_CLI", "gemini"),
}


@dataclass
class HarnessConfig:
    root: str = DEFAULT_ROOT
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    priority: List[str] = field(default_factory=list)
    default_model: Optional[str] = None
    default_strategy: str = "cot"
    working_limit: int = 8
    short_term_limit: int = 32

    @property
    def root_path(self) -> str:
        return os.path.expanduser(self.root)


def _load_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            try:
                import yaml

                return yaml.safe_load(f) or {}
            except ImportError:
                return {}
        return json.load(f)


def _find_config_file(root: str) -> Optional[str]:
    base = os.path.expanduser(root)
    for name in ("config.json", "config.yaml", "config.yml", "settings.yaml"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def _provider_from_dict(d: Dict[str, Any]) -> ProviderConfig:
    prefer = d.get("prefer", "subscription")
    return ProviderConfig(
        enabled=d.get("enabled", True),
        api_key=d.get("api_key"),
        base_url=d.get("base_url"),
        cli_path=d.get("cli_path"),
        default_model=d.get("default_model") or d.get("model"),
        prefer=AuthMode(prefer) if not isinstance(prefer, AuthMode) else prefer,
        extra=d.get("extra", {}) or {},
    )


def load_config(path: Optional[str] = None, root: str = DEFAULT_ROOT) -> HarnessConfig:
    """Build a :class:`HarnessConfig` from file + environment."""
    cfg = HarnessConfig(root=root)
    file_path = path or _find_config_file(root)
    data = _load_file(file_path) if file_path else {}

    cfg.root = data.get("root", root)
    cfg.default_model = data.get("default_model")
    cfg.default_strategy = data.get("default_strategy", "cot")
    cfg.working_limit = data.get("working_limit", 8)
    cfg.short_term_limit = data.get("short_term_limit", 32)

    # providers explicitly declared in the file
    for name, pdata in (data.get("providers") or {}).items():
        cfg.providers[name] = _provider_from_dict(pdata)

    _apply_env(cfg)

    # priority: file value, else every configured provider in a sensible order
    from .providers.registry import DEFAULT_PRIORITY

    cfg.priority = data.get("priority") or [p for p in DEFAULT_PRIORITY if p in cfg.providers] or list(
        cfg.providers
    )
    return cfg


def _apply_env(cfg: HarnessConfig) -> None:
    """Overlay environment variables: BYOK keys and CLI availability."""
    for env, provider in _API_KEY_ENV.items():
        val = os.environ.get(env)
        if val:
            pc = cfg.providers.setdefault(provider, ProviderConfig())
            if not pc.api_key:
                pc.api_key = val
                pc.prefer = AuthMode.API_KEY if provider == "openrouter" else pc.prefer

    # Subscription auto-detection can be disabled for BYOK-only setups.
    no_cli = os.environ.get("NOESIS_NO_CLI", "").lower() in ("1", "true", "yes")
    for provider, (env, default_bin) in _CLI_ENV.items():
        if no_cli:
            break
        binpath = os.environ.get(env, default_bin)
        from .providers.cli import which

        if which(binpath):
            pc = cfg.providers.setdefault(provider, ProviderConfig())
            pc.cli_path = pc.cli_path or binpath

    # A custom OpenAI-compatible endpoint via env.
    base = os.environ.get("NOESIS_CUSTOM_BASE_URL")
    if base:
        pc = cfg.providers.setdefault("custom", ProviderConfig())
        pc.base_url = base
        pc.api_key = pc.api_key or os.environ.get("NOESIS_CUSTOM_API_KEY")
        pc.default_model = pc.default_model or os.environ.get("NOESIS_CUSTOM_MODEL")
