"""One reading of the Ollama server URL.

LIA stores a single URL for the Ollama server, typed by an operator, and two
readers consume it: the chat adapter (``langchain-ollama``, native ``/api/chat``,
ADR-267) and the discovery (``/api/tags``, ``/api/show``). Both talk to the
server ROOT. Operators used to type the OpenAI-compatible ``/v1`` suffix -- the
admin placeholder even suggested it while the shim was in use -- so the suffix is
tolerated and stripped here, once, for every reader. Measured in production
(2026-09-05): the stored URL and the documented one disagreed on that suffix, and
the two readers tolerated different shapes.

:func:`ollama_native_root` is idempotent. Values that are not URLs -- the
``NOT_CONFIGURED`` placeholder the credential resolver returns so the app can
boot -- pass through unchanged, so the failure they cause still names them.
"""

from __future__ import annotations

import os

from src.core.constants import OLLAMA_BASE_URL_ENV, OLLAMA_OPENAI_COMPAT_PATH

__all__ = ["ollama_native_root", "resolve_ollama_url"]

_URL_SCHEMES = ("http://", "https://")


def _is_url(value: str) -> bool:
    return value.lower().startswith(_URL_SCHEMES)


def resolve_ollama_url() -> str | None:
    """Read the configured Ollama URL, as typed, from the DB cache then the environment.

    The same resolution order as every provider credential (admin UI first,
    ``.env`` as the fallback). Blank values count as unset: an empty variable
    is not an address.

    Returns:
        The raw configured value, or ``None`` when nothing is configured.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    raw = (LLMConfigOverrideCache.get_api_key("ollama") or "").strip()
    if not raw:
        raw = os.environ.get(OLLAMA_BASE_URL_ENV, "").strip()
    return raw or None


def ollama_native_root(raw: str) -> str:
    """The root the server answers at: no trailing slash, no ``/v1`` suffix.

    Args:
        raw: The configured value, in any shape an operator may have typed.

    Returns:
        The root URL, or ``raw`` unchanged when it is not a URL.
    """
    value = raw.strip()
    if not _is_url(value):
        return raw
    root = value.rstrip("/")
    if root.endswith(OLLAMA_OPENAI_COMPAT_PATH):
        root = root[: -len(OLLAMA_OPENAI_COMPAT_PATH)]
    return root.rstrip("/")
