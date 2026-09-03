"""Redis key families and their scope (ADR-260).

Every key family LIA writes to Redis is listed here with the scope that decides
who may delete it. The conversation reset used to delete every key matching
``*:{user_id}*`` — which is how the recurrence ledger, the Gmail delta anchor
and the adaptive thresholds were wiped 161 times in 56 days on the primary
production account (measured 2026-09-03). A family now declares what it is:

- ``CONVERSATION``: state of the running conversation (HITL, active run, tool
  contexts) — purged by a conversation reset.
- ``USER_CACHE``: per-user caches with a TTL — purged by a reset (privacy and
  freshness), harmless to lose.
- ``USER_LEARNING``: what LIA learned about the user — NEVER purged by a
  reset; purged by account deletion and by the explicit "forget" surfaces.
- ``USER_RUNTIME``: sessions, rate limits, SSE registries, one-time tokens —
  never purged by a reset (deleting a rate-limit key at reset was a bypass).
- ``GLOBAL``: not user-scoped.

The match is longest-prefix on ``:``-separated segments, so
``briefing:v2:lastgood`` wins over ``briefing:v2``. An UNDECLARED family is
never purged by a reset: silent deletion is how learning died invisibly, so
the safe default is to keep and to count (``reset_undeclared_family_total``).
The boot guard (:func:`assert_key_families_complete`) refuses to start when a
``core.constants`` prefix names a family this registry does not know.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


class KeyScope(str, Enum):
    """Who may delete a key of this family."""

    CONVERSATION = "conversation"
    USER_CACHE = "user_cache"
    USER_LEARNING = "user_learning"
    USER_RUNTIME = "user_runtime"
    GLOBAL = "global"


#: Family prefix (``:``-separated segments, no trailing colon) → scope.
KEY_FAMILIES: dict[str, KeyScope] = {
    # --- conversation: purged by a reset ---------------------------------
    "hitl_pending": KeyScope.CONVERSATION,
    "hitl:request_ts": KeyScope.CONVERSATION,
    "chat:run": KeyScope.CONVERSATION,
    "chat:active_run": KeyScope.CONVERSATION,
    "chat:listeners": KeyScope.CONVERSATION,
    "chat:cancel": KeyScope.CONVERSATION,
    "browser:session": KeyScope.CONVERSATION,
    # --- per-user caches: purged by a reset ------------------------------
    "contacts_list": KeyScope.USER_CACHE,
    "contacts_search": KeyScope.USER_CACHE,
    "contacts_details": KeyScope.USER_CACHE,
    "places_search": KeyScope.USER_CACHE,
    "places_nearby": KeyScope.USER_CACHE,
    "gmail:message": KeyScope.USER_CACHE,
    "gmail:search": KeyScope.USER_CACHE,
    "gmail:labels": KeyScope.USER_CACHE,
    "relations:context:v2": KeyScope.USER_CACHE,
    "briefing:v2": KeyScope.USER_CACHE,
    "heartbeat:birthdays": KeyScope.USER_CACHE,
    "heartbeat:departure": KeyScope.USER_CACHE,
    "user_connectors": KeyScope.USER_CACHE,
    "interest_analysis": KeyScope.USER_CACHE,
    "usage_limit": KeyScope.USER_CACHE,
    "conv:user": KeyScope.USER_CACHE,
    "meetings:start": KeyScope.USER_CACHE,
    "skills:url_import": KeyScope.USER_CACHE,
    "rag": KeyScope.USER_CACHE,
    "bm25": KeyScope.USER_CACHE,
    # --- learning: NEVER purged by a reset -------------------------------
    "recurrence": KeyScope.USER_LEARNING,
    "gmail_history_anchor": KeyScope.USER_LEARNING,
    "adaptive": KeyScope.USER_LEARNING,
    "briefing:v2:lastgood": KeyScope.USER_LEARNING,
    "presence": KeyScope.USER_LEARNING,
    "heartbeat:wake": KeyScope.USER_LEARNING,
    "psyche:state": KeyScope.USER_LEARNING,
    # --- runtime: never purged by a reset --------------------------------
    "session": KeyScope.USER_RUNTIME,
    "user": KeyScope.USER_RUNTIME,
    "user_notifications": KeyScope.USER_RUNTIME,
    "sse:connection": KeyScope.USER_RUNTIME,
    "sse:streams": KeyScope.USER_RUNTIME,
    "oauth_lock": KeyScope.USER_RUNTIME,
    "oauth:health:notified": KeyScope.USER_RUNTIME,
    "oauth:state": KeyScope.USER_RUNTIME,
    "apikey:user": KeyScope.USER_RUNTIME,
    "ws:audio": KeyScope.USER_RUNTIME,
    "ws_ticket": KeyScope.USER_RUNTIME,
    "usage_limit_ws_ticket": KeyScope.USER_RUNTIME,
    "hitl_rate_limit": KeyScope.USER_RUNTIME,
    "health_metrics_ingest": KeyScope.USER_RUNTIME,
    "webauthn:reg": KeyScope.USER_RUNTIME,
    "webauthn:auth": KeyScope.USER_RUNTIME,
    "webauthn:stepup": KeyScope.USER_RUNTIME,
    "mfa:pending": KeyScope.USER_RUNTIME,
    "native:handoff": KeyScope.USER_RUNTIME,
    "jti:used": KeyScope.USER_RUNTIME,
    "apple_rate_limit": KeyScope.USER_RUNTIME,
    "channel": KeyScope.USER_RUNTIME,
    "channel_otp": KeyScope.USER_RUNTIME,
    "channel_otp_attempts": KeyScope.USER_RUNTIME,
    "channel_rate": KeyScope.USER_RUNTIME,
    "mcp_oauth_state": KeyScope.USER_RUNTIME,
    # --- global ---------------------------------------------------------------
    "llm_cache": KeyScope.GLOBAL,
    "web_search": KeyScope.GLOBAL,
    "web_fetch": KeyScope.GLOBAL,
    "push:debounce": KeyScope.GLOBAL,
    "scheduler": KeyScope.GLOBAL,
    "scheduler_lock": KeyScope.GLOBAL,
    "diagnostics": KeyScope.GLOBAL,
    "system": KeyScope.GLOBAL,
    "http": KeyScope.GLOBAL,
    "ratelimit": KeyScope.GLOBAL,
    "product": KeyScope.GLOBAL,
    "pricing": KeyScope.GLOBAL,
    "plan:patterns": KeyScope.GLOBAL,
    "heartbeat:geocode": KeyScope.GLOBAL,
    "telegram_update": KeyScope.GLOBAL,
    "channel_msg_lock": KeyScope.GLOBAL,
}

#: Families whose keys carry no ``:`` separator after the prefix
#: (``async_model_price_gpt-4o``). Matched by ``startswith`` only.
BARE_PREFIX_FAMILIES: dict[str, KeyScope] = {
    "async_model_price_": KeyScope.GLOBAL,
    "async_currency_rate_": KeyScope.GLOBAL,
}

_RESET_PURGED: frozenset[KeyScope] = frozenset({KeyScope.CONVERSATION, KeyScope.USER_CACHE})
_USER_SCOPED: frozenset[KeyScope] = frozenset(
    {KeyScope.CONVERSATION, KeyScope.USER_CACHE, KeyScope.USER_LEARNING, KeyScope.USER_RUNTIME}
)

#: Constant names in ``core.constants`` that declare a Redis key prefix.
_PREFIX_CONSTANT_NAME = re.compile(
    r"^(REDIS_KEY_.*_PREFIX|.*_REDIS_PREFIX|.*_KEY_PREFIX|.*_CACHE_PREFIX)$"
)


def _as_str(key: str | bytes) -> str:
    return key.decode() if isinstance(key, bytes) else key


def family_of(key: str | bytes) -> str | None:
    """Longest declared family prefix of ``key`` on ``:`` boundaries.

    Args:
        key: A full Redis key (str or bytes).

    Returns:
        The declared family prefix, or None when no family claims the key.
    """
    name = _as_str(key)
    parts = name.split(":")
    for length in range(len(parts), 0, -1):
        candidate = ":".join(parts[:length])
        if candidate in KEY_FAMILIES:
            return candidate
    for bare in BARE_PREFIX_FAMILIES:
        if name.startswith(bare):
            return bare
    return None


def scope_of(key: str | bytes) -> KeyScope | None:
    """Declared scope of ``key``'s family, or None when undeclared."""
    family = family_of(key)
    if family is None:
        return None
    return KEY_FAMILIES.get(family) or BARE_PREFIX_FAMILIES[family]


def is_reset_purgeable(key: str | bytes) -> bool:
    """Whether a conversation reset may delete this key.

    Only families declared ``CONVERSATION`` or ``USER_CACHE`` qualify. An
    undeclared family answers False: keeping an unknown key costs a cache
    miss, deleting it may cost weeks of learning.
    """
    return scope_of(key) in _RESET_PURGED


def is_user_scoped(key: str | bytes) -> bool:
    """Whether account deletion must delete this key (any user-scoped family)."""
    return scope_of(key) in _USER_SCOPED


def scan_patterns_for(*identifiers: str) -> list[str]:
    """The SCAN globs that reach every key carrying one of ``identifiers``.

    Three shapes per identifier (``*:{id}:*``, ``*:{id}``, ``{id}:*``) — the
    historical reset patterns, kept verbatim so no key that used to be matched
    escapes the scan; the registry decides what happens to a match.

    Args:
        identifiers: User / conversation ids (string form); duplicates are
            collapsed (conversation.id == user.id in production).

    Returns:
        Ordered, de-duplicated glob patterns.
    """
    patterns: list[str] = []
    for identifier in identifiers:
        patterns.extend((f"*:{identifier}:*", f"*:{identifier}", f"{identifier}:*"))
    return list(dict.fromkeys(patterns))


async def scan_keys(redis: Any, patterns: list[str], *, count: int = 100) -> set[str]:
    """Every key matching any of ``patterns`` (SCAN, never KEYS).

    Args:
        redis: Async Redis client exposing ``scan(cursor, match=, count=)``.
        patterns: Glob patterns from :func:`scan_patterns_for`.
        count: SCAN hint per round-trip.

    Returns:
        The matched keys, decoded, de-duplicated across patterns.
    """
    matched: set[str] = set()
    for pattern in patterns:
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=count)
            matched.update(_as_str(key) for key in keys)
            if cursor == 0:
                break
    return matched


def assert_key_families_complete() -> None:
    """Boot-time guard (ADR-085 doctrine): every Redis prefix constant of
    ``core.constants`` names a family this registry declares, and no family
    is declared twice across the two tables.

    Raises:
        RuntimeError: On any undeclared prefix or duplicate family.
    """
    from src.core import constants as c

    duplicates = sorted(set(KEY_FAMILIES) & set(BARE_PREFIX_FAMILIES))
    if duplicates:
        raise RuntimeError(f"Redis key families declared twice: {duplicates}")

    missing: list[str] = []
    for attr in dir(c):
        if not _PREFIX_CONSTANT_NAME.match(attr):
            continue
        value = getattr(c, attr)
        if not isinstance(value, str) or not value:
            continue
        # A prefix constant may or may not carry its trailing separator
        # ("session:" vs "sse:connection"): probe the key a writer would build.
        probe = value + "x" if value.endswith((":", "_")) else value + ":x"
        if family_of(probe) is None:
            missing.append(f"{attr}={value!r}")
    if missing:
        raise RuntimeError(
            "Redis key prefixes without a declared scope in "
            f"infrastructure/cache/key_families.py: {sorted(missing)}"
        )
