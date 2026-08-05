"""Recurrence-ledger seed from ``product_outcomes`` (ADR-214 rebuild lot).

The recurrence ledger is advisory Redis: a flush costs ~a week of
relearning, and history recorded BEFORE the habits program carried no
domain labels at all. Since the domain seam ships, ``product_outcomes``
holds the durable (user, domain, produced_at) truth — so an EMPTY ledger
can be reseeded from it, which also makes recurrences retroactive over
post-deployment history on the first recompute.

Honesty bounds, in order of importance:

- the SAME human-run whitelist as every durable source: an outcome whose
  run maps to an automated session family must never seed (the
  scheduled-action metronome, proven on prod 2026-08-05);
- seed ONLY when the user's ledger is empty — live data always wins; the
  per-key NX write is belt-and-braces against a concurrent first record;
- signatures rebuild as single domains (``product_outcomes`` stores the
  primary domain only): composite signatures ("email+contact") re-learn
  live — a stated limit, not a silent one;
- best-effort everywhere: the ledger is advisory, a failed seed logs and
  returns 0.

Storage format comes from the shared ``infrastructure.cache
.recurrence_store`` — what this module writes, the agents lock evaluation
reads (end-to-end pinned in ``test_ledger_seed.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HUMAN_CHAT_SESSION_UUID_REGEX
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)

# Human outcomes only (whitelist via the run→summary join, exactly like the
# message source in habits/repository.py) with a resolved domain label.
_SEED_ACTIVITY_SQL = text("""
    SELECT po.domain AS domain,
           (po.produced_at AT TIME ZONE :tz)::date::text AS local_date,
           (EXTRACT(HOUR FROM po.produced_at AT TIME ZONE :tz)
            + EXTRACT(MINUTE FROM po.produced_at AT TIME ZONE :tz) / 60.0)::float AS local_hour
    FROM product_outcomes po
    WHERE po.user_id = :user_id
      AND po.produced_at >= :since
      AND po.domain <> 'unknown'
      AND NOT EXISTS (
          SELECT 1 FROM message_token_summary mts
          WHERE mts.run_id = po.run_id
            AND NOT (mts.session_id LIKE 'session\\_%'
                     OR mts.session_id LIKE 'channel\\_%'
                     OR mts.session_id ~ :uuid_regex)
      )
    ORDER BY po.produced_at
    """)


async def _ledger_is_empty(redis: Any, user_id: UUID) -> bool:
    async for _ in redis.scan_iter(match=recurrence_store.user_key_pattern(str(user_id))):
        return False
    return True


async def seed_ledger_from_outcomes(
    db: AsyncSession,
    user_id: UUID,
    tz_name: str,
    settings: Any,
) -> int:
    """Rebuild an EMPTY recurrence ledger from durable product outcomes.

    Args:
        db: Caller-owned session (the recompute's).
        user_id: Owner.
        tz_name: IANA timezone (day bucketing follows the user's wall clock,
            same convention as every activity source).
        settings: Settings view (flag, window, caps).

    Returns:
        Number of signatures seeded; 0 when the flag is off, the ledger is
        alive, there is nothing to seed, or anything failed (best-effort).
    """
    if not getattr(settings, "recurrence_suggestion_enabled", False):
        return 0
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return 0
        if not await _ledger_is_empty(redis, user_id):
            return 0

        since = datetime.now(UTC) - timedelta(days=settings.recurrence_window_days + 1)
        # Savepoint: this SELECT shares the recompute's session, and a failed
        # statement poisons the whole transaction — without the savepoint the
        # caller's COMMIT of the profile would die with it (ADR-204 trap).
        async with db.begin_nested():
            result = await db.execute(
                _SEED_ACTIVITY_SQL,
                {
                    "user_id": str(user_id),
                    "tz": tz_name,
                    "since": since,
                    "uuid_regex": HUMAN_CHAT_SESSION_UUID_REGEX,
                },
            )

        per_signature: dict[str, dict[str, list[float]]] = {}
        for domain, local_date, local_hour in result.all():
            hours = per_signature.setdefault(str(domain), {}).setdefault(str(local_date), [])
            if len(hours) < int(settings.recurrence_day_hours_cap):
                hours.append(round(float(local_hour), 2))

        seeded = 0
        for signature, days in per_signature.items():
            data: dict[str, Any] = {"days": days, "suggested_at": None}
            recurrence_store.trim(data, int(settings.recurrence_ledger_max_entries))
            written = await recurrence_store.store_if_absent(
                redis,
                recurrence_store.redis_key(str(user_id), signature),
                data,
                int(settings.recurrence_window_days),
            )
            if written:
                seeded += 1
        if seeded:
            logger.info(
                "recurrence_ledger_seeded",
                user_id=str(user_id),
                signatures=seeded,
            )
        return seeded
    except Exception as exc:  # noqa: BLE001 — advisory ledger, never blocks
        logger.debug("recurrence_ledger_seed_failed", error=str(exc))
        return 0
