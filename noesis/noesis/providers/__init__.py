"""Unified multi-provider LLM layer (subscription + BYOK)."""

from .base import (
    AuthMode,
    ChatResult,
    Message,
    Provider,
    ProviderConfig,
    ProviderError,
)
from .claude import ClaudeCodeProvider, ClaudeProvider
from .gemini import GeminiProvider
from .kimi import KimiProvider
from .openai_compat import CustomProvider, OpenAICompatProvider
from .openrouter import OpenRouterProvider
from .registry import PROVIDER_CLASSES, DEFAULT_PRIORITY, ProviderRouter

__all__ = [
    "AuthMode",
    "ChatResult",
    "Message",
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "OpenAICompatProvider",
    "CustomProvider",
    "OpenRouterProvider",
    "ClaudeProvider",
    "ClaudeCodeProvider",
    "KimiProvider",
    "GeminiProvider",
    "ProviderRouter",
    "PROVIDER_CLASSES",
    "DEFAULT_PRIORITY",
]
