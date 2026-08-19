"""
Shared helpers for subscription (CLI-backed) providers.

Subscription mode reuses a vendor's already-authenticated local CLI — e.g.
``claude`` (Claude Code), ``gemini`` (Gemini CLI), ``kimi`` — by invoking it as
a subprocess and capturing stdout. This lets the harness ride an existing paid
subscription instead of paying per-token via an API key.

The functions here are intentionally thin and testable: :func:`which` resolves
an executable, and :func:`run_cli` shells out with a timeout and returns the
captured text. Concrete providers build their own argv and prompt encoding.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional

from .base import Message, ProviderError

DEFAULT_TIMEOUT = 180


def which(executable: Optional[str]) -> Optional[str]:
    """Resolve ``executable`` to a full path, honouring absolute paths.

    Returns ``None`` when it is not found so callers can treat subscription
    mode as simply unavailable rather than erroring.
    """
    if not executable:
        return None
    if os.path.isabs(executable):
        return executable if os.path.exists(executable) else None
    return shutil.which(executable)


def messages_to_prompt(messages: List[Message]) -> str:
    """Flatten a chat transcript into a single prompt for CLIs that take one.

    System messages are hoisted to the top; the rest are rendered as a simple
    ``Role: content`` transcript ending on an ``Assistant:`` cue.
    """
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    turns = [m for m in messages if m.role != "system"]
    lines: List[str] = []
    if system:
        lines.append(system.strip())
        lines.append("")
    for m in turns:
        label = "User" if m.role == "user" else m.role.capitalize()
        lines.append(f"{label}: {m.content}")
    lines.append("Assistant:")
    return "\n".join(lines)


def run_cli(
    argv: List[str],
    stdin_text: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[dict] = None,
) -> str:
    """Run ``argv``, feed ``stdin_text``, return stdout (stripped).

    Raises :class:`ProviderError` on non-zero exit, missing binary, or timeout.
    """
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
    except FileNotFoundError as e:
        raise ProviderError(f"CLI not found: {argv[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise ProviderError(f"CLI timed out after {timeout}s: {argv[0]}") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise ProviderError(f"{argv[0]} exited {proc.returncode}: {err[:500]}")
    return (proc.stdout or "").strip()
