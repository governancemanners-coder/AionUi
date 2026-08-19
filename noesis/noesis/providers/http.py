"""
Tiny stdlib HTTP helper for provider adapters.

Uses ``urllib.request`` so the package has no third-party HTTP dependency and
runs unchanged on Termux. Supports JSON POST and line-delimited streaming
(SSE-style ``data:`` frames) via a generator.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional

from .base import ProviderError

DEFAULT_TIMEOUT = 120


def post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """POST ``payload`` as JSON and decode a JSON response."""
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # pragma: no cover - network dependent
        detail = e.read().decode("utf-8", "replace") if e.fp else str(e)
        raise ProviderError(f"HTTP {e.code} from {url}: {detail[:500]}") from e
    except urllib.error.URLError as e:  # pragma: no cover - network dependent
        raise ProviderError(f"cannot reach {url}: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:  # pragma: no cover
        raise ProviderError(f"non-JSON response from {url}: {body[:200]}") from e


def stream_sse(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Iterator[str]:
    """POST ``payload`` and yield raw ``data:`` frame bodies from an SSE stream.

    The caller is responsible for parsing each frame (providers differ). A
    frame equal to ``[DONE]`` terminates the stream and is not yielded.
    """
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:  # pragma: no cover - network dependent
        detail = e.read().decode("utf-8", "replace") if e.fp else str(e)
        raise ProviderError(f"HTTP {e.code} from {url}: {detail[:500]}") from e
    except urllib.error.URLError as e:  # pragma: no cover - network dependent
        raise ProviderError(f"cannot reach {url}: {e.reason}") from e
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            frame = line[len("data:"):].strip()
            if frame == "[DONE]":
                break
            yield frame
