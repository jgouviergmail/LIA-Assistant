"""The outbound proxy a voice WebSocket must go through, when the deployment sets one.

Every other client in the stack picks the proxy up on its own — httpx and
requests read the environment by default. A voice WebSocket opened through
aiohttp does not: aiohttp reads no proxy unless it is handed one, and with
``trust_env`` it looks a ``wss://`` address up under ``WSS_PROXY`` alone, never
``HTTPS_PROXY`` (read in its source). ``edge-tts`` was the first call that
ignored the deployment's only route out (measured 2026-08-07 in the
demonstrator's envelope, where the API container sits on no routed network:
« ignores the proxy » means « never connects »); Fish Audio's socket is the
second (ADR-345). One reading for both.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def configured_proxy(env: Mapping[str, str] | None = None) -> str | None:
    """Outbound proxy this process must use, if the deployment sets one.

    Args:
        env: Environment to read; defaults to the process environment. Passed
            explicitly by tests because ``os.environ`` is case-INSENSITIVE on
            Windows, where the two conventional spellings collapse into one
            and the precedence between them cannot be observed.

    Returns:
        The proxy URL, or ``None`` for a direct deployment — which keeps a
        direct connection byte for byte.
    """
    source = os.environ if env is None else env
    for name in ("HTTPS_PROXY", "https_proxy"):
        value = (source.get(name) or "").strip()
        if value:
            return value
    return None


__all__ = ["configured_proxy"]
