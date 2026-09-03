"""Redis purge of a conversation reset, by declared key family (ADR-260).

Extracted from ``conversations/service.py`` (frozen at its audited size). The
historical purge scanned six user/conversation patterns and deleted every
match — including the recurrence ledger, the Gmail delta anchor, the adaptive
thresholds and the briefing's last-known-good values, none of which is the
conversation. The scan is unchanged (no key escapes it); the DECISION now
reads the registry: a key is deleted only when its family is declared
``CONVERSATION`` or ``USER_CACHE``. Everything else is counted and kept.

Best-effort by doctrine: the caller wraps this in ``suppress`` — a failed
purge costs a cache miss, never a failed reset.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from src.infrastructure.cache.key_families import (
    family_of,
    is_reset_purgeable,
    scan_keys,
    scan_patterns_for,
    scope_of,
)
from src.infrastructure.observability.metrics_key_families import (
    conversation_reset_keys_deleted_total,
    conversation_reset_keys_kept_total,
    reset_undeclared_family_total,
)

logger = structlog.get_logger(__name__)

_DELETE_BATCH_SIZE = 100


def reset_scan_patterns(user_id: str, conversation_id: str) -> list[str]:
    """The SCAN patterns a reset inspects — the historical six, de-duplicated
    (see :func:`scan_patterns_for`); a key that used to be matched is still
    matched, the registry decides its fate."""
    return scan_patterns_for(user_id, conversation_id)


# A head that LOOKS like an identifier (uuid, long hex digest, long number) is
# never used as a label value: label cardinality must be bounded by
# construction, not by the fact that today's keys happen to be well named.
_ID_SHAPED = re.compile(r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F-]{20,}|[0-9a-fA-F]{16,}|\d{8,})$")


def _undeclared_label(key: str, ids: set[str]) -> str:
    """Bounded metric label for an undeclared key: its first segment, unless
    that segment IS (or looks like) an identifier — an id must never become a
    label value, whatever entity it names."""
    head = key.split(":", 1)[0]
    if head in ids or _ID_SHAPED.match(head):
        return "id_prefixed"
    return head


async def purge_conversation_keys(
    redis: Any,
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, int]:
    """Delete the reset-purgeable keys of a user/conversation, keep the rest.

    Args:
        redis: Async Redis client.
        user_id: The user's id (string form).
        conversation_id: The conversation's id (string form).

    Returns:
        Deleted key counts per family (exact).
    """
    ids = {user_id, conversation_id}
    matched = await scan_keys(redis, reset_scan_patterns(user_id, conversation_id))

    to_delete: list[str] = []
    deleted_by_family: dict[str, int] = {}
    kept_by_scope: dict[str, int] = {}
    for key in sorted(matched):
        family = family_of(key)
        if family is None:
            kept_by_scope["undeclared"] = kept_by_scope.get("undeclared", 0) + 1
            reset_undeclared_family_total.labels(family=_undeclared_label(key, ids)).inc()
            continue
        if is_reset_purgeable(key):
            to_delete.append(key)
            deleted_by_family[family] = deleted_by_family.get(family, 0) + 1
            continue
        scope = scope_of(key)
        scope_label = scope.value if scope is not None else "undeclared"
        kept_by_scope[scope_label] = kept_by_scope.get(scope_label, 0) + 1

    for start in range(0, len(to_delete), _DELETE_BATCH_SIZE):
        await redis.delete(*to_delete[start : start + _DELETE_BATCH_SIZE])

    for family, count in deleted_by_family.items():
        conversation_reset_keys_deleted_total.labels(family=family).inc(count)
    for scope_label, count in kept_by_scope.items():
        conversation_reset_keys_kept_total.labels(scope=scope_label).inc(count)

    logger.info(
        "redis_purged_for_reset",
        user_id=user_id,
        conversation_id=conversation_id,
        total_keys_deleted=len(to_delete),
        deleted_by_family=deleted_by_family,
        kept_by_scope=kept_by_scope,
    )
    return deleted_by_family
