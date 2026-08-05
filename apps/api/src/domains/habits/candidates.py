"""Recurrence candidates under observation (ADR-214, unlock-progress lot).

A signature the recurrence ledger has SEEN but not yet locked is surfaced to
the user as "under observation", quantified with the ENFORCED existence
threshold (ADR-184: a published bound is the applied bound — never a
re-declared one). This is the recurrence counterpart of the rhythm unlock
progressbar: the user sees WHERE each nascent habit stands instead of an
unquantified silence until the lock fires.

The ledger's SEMANTICS belong to the agents domain; its STORAGE format is
the shared ``infrastructure.cache.recurrence_store`` (agents already
imports habits for the promotion path, so importing the agents service from
here would close the runtime cycle the coupling ratchet forbids — the
shared store is the factored answer, no duplicated literal). The end-to-end
shape stays pinned by
``tests/unit/domains/habits/test_candidates_ledger_contract.py``.

Enumeration uses ``SCAN`` with a match pattern (cursor-based, non-blocking):
signatures per user are few and this runs on a settings-page fetch, not a
hot path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import structlog

from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RecurrenceCandidate:
    """One signature under observation.

    Attributes:
        key: Domain signature (e.g. ``"email+contact"``).
        observed_days: Distinct local days with occurrences inside the window.
        required_days: The enforced existence threshold (published, ADR-184).
    """

    key: str
    observed_days: int
    required_days: int


def _observed_days(data: dict[str, Any], window_start: date) -> int:
    """Distinct in-window days with ≥1 occurrence from a ledger payload."""
    return sum(
        1
        for day, hours in recurrence_store.parse_days(data).items()
        if hours and day > window_start
    )


async def observed_days_for_signature(user_id: UUID, signature: str) -> list[str]:
    """The REAL occurrence dates the ledger holds for one signature.

    Honest provenance for a recurring habit: these dates ARE the basis of
    the lock (never fabricated conversation references — the ledger keeps
    no message ids on purpose). Sorted newest first; best-effort.
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return []
        data = await recurrence_store.load(
            redis, recurrence_store.redis_key(str(user_id), signature)
        )
        return sorted(
            (day.isoformat() for day, hours in recurrence_store.parse_days(data).items() if hours),
            reverse=True,
        )
    except Exception as exc:  # noqa: BLE001 — advisory source, never blocks
        logger.debug("habit_observed_days_read_failed", error=str(exc))
        return []


async def list_recurrence_candidates(
    user_id: UUID,
    *,
    local_today: date,
    exclude_keys: set[str],
    settings: Any,
    limit: int,
) -> tuple[list[RecurrenceCandidate], int]:
    """Signatures under observation for one user, capped with a stated drop.

    Args:
        user_id: Owner.
        local_today: The user's local calendar date (window anchor — same
            anchor the lock evaluation uses).
        exclude_keys: Signatures that already have a habit row (any status —
            a BLOCKED tombstone must never resurface as a candidate).
        settings: Settings view (flag, window, existence threshold).
        limit: Maximum candidates returned; the remainder is COUNTED (a cap
            is stated, never applied in silence — ADR-185 doctrine).

    Returns:
        ``(candidates, dropped_count)`` — best-effort: the ledger is
        advisory, so a missing Redis or a malformed entry degrades to an
        empty/shorter list, never an error.
    """
    if not getattr(settings, "recurrence_suggestion_enabled", False):
        return [], 0
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return [], 0
        window_start = local_today - timedelta(days=settings.recurrence_window_days)
        found: list[RecurrenceCandidate] = []
        async for key in redis.scan_iter(match=recurrence_store.user_key_pattern(str(user_id))):
            signature = recurrence_store.signature_from_key(key, str(user_id))
            if not signature or signature in exclude_keys:
                continue
            data = await recurrence_store.load(
                redis, recurrence_store.redis_key(str(user_id), signature)
            )
            observed = _observed_days(data, window_start)
            if observed <= 0:
                continue
            found.append(
                RecurrenceCandidate(
                    key=signature,
                    observed_days=observed,
                    required_days=int(settings.recurrence_min_distinct_days),
                )
            )
        found.sort(key=lambda c: (-c.observed_days, c.key))
        return found[:limit], max(0, len(found) - limit)
    except Exception as exc:  # noqa: BLE001 — advisory source, never blocks
        logger.debug("habit_candidates_read_failed", error=str(exc))
        return [], 0
