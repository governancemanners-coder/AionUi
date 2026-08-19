"""
noesis — a knowledge-holder and memory agent harness.

Multi-tier memory, a durable soul graph, Hermes-inspired reasoning, an
immutable audit ledger, and a unified multi-provider LLM layer that speaks to
OpenRouter, Claude (API + Claude Code subscription), Kimi/Moonshot, Gemini, and
any custom OpenAI-compatible endpoint — via BYOK keys or existing paid
subscriptions.
"""

from .config import HarnessConfig, load_config
from .harness import Harness
from .version import __version__

__all__ = ["Harness", "HarnessConfig", "load_config", "__version__"]
