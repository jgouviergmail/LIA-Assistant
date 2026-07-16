"""Telephony background reapers (spec P4.3).

- ``telephony_stale_call_reaper``: sweeps ``dialing``/``in_progress`` calls that
  never received a terminal webhook (process crash / vendor never called back) to
  ``failed`` — so a user is never stuck behind a phantom "in progress" call and
  the one-active-call slot (F12) is freed.
- ``telephony_retention_reaper``: clears ``summary``/``structured_data`` past
  their retention TTL (D-8). The row is kept for audit; only its content is
  purged.

Both are registered flag-guarded in ``startup/schedulers.py`` and run under the
scheduler leader election, so exactly one instance sweeps at a time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from src.core.config import settings
from src.domains.telephony.repository import TelephonyRepository
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

# Per-sweep batch bound (internal; not a user-tuning knob). Oldest-PENDING first,
# so the backlog drains deterministically across ticks.
_NOTIFICATION_REAP_BATCH = 50
# Per-sweep bound for the pre-synthesis return inbox (T1 approach A).
_RETURN_REAP_BATCH = 25


async def telephony_stale_call_reaper() -> None:
    """Mark in-flight calls with no terminal webhook as failed (crash recovery)."""
    async with get_db_context() as db:
        count = await TelephonyRepository(db).recover_stale(
            settings.telephony_stale_call_timeout_minutes
        )
        await db.commit()
    if count:
        logger.info("telephony_stale_calls_reaped", count=count)


async def telephony_retention_reaper() -> None:
    """Purge call summary/structured_data past their retention TTL (D-8)."""
    async with get_db_context() as db:
        count = await TelephonyRepository(db).purge_expired()
        await db.commit()
    if count:
        logger.info("telephony_calls_purged", count=count)


async def telephony_notification_reaper() -> None:
    """Re-dispatch return notifications a crash left PENDING (T1 durability).

    ``process_completed_call`` commits the call result AND a PENDING outbox record
    (``notification_status`` + minimal ``notification_payload``) atomically, then
    dispatches. A hard crash in that window leaves a durable PENDING row; this
    reaper (single-instance under leader election + ``max_instances=1``) re-dispatches
    it from the persisted payload — no re-synthesis, no lost return. Rows are only
    picked up past a grace window (so the live dispatch of a just-completed call is
    not raced) and retries are bounded before the row is marked FAILED.
    """
    from src.domains.users.models import User
    from src.infrastructure.observability.metrics_telephony import (
        telephony_notification_recovered_total,
    )
    from src.infrastructure.proactive.notification import NotificationDispatcher

    cutoff = datetime.now(UTC) - timedelta(seconds=settings.telephony_notification_grace_seconds)
    max_attempts = settings.telephony_notification_max_attempts

    async with get_db_context() as db:
        repo = TelephonyRepository(db)
        pending = await repo.fetch_recoverable_notifications(
            cutoff=cutoff, max_attempts=max_attempts, limit=_NOTIFICATION_REAP_BATCH
        )
        # Snapshot the fields needed before any commit (the dispatcher commits
        # mid-loop, which would expire the loaded ORM instances).
        jobs = [
            (call.id, call.user_id, dict(call.notification_payload or {}), call.status.value)
            for call in pending
        ]

    if not jobs:
        return

    delivered = failed = skipped = 0
    for call_id, user_id, payload, call_status in jobs:
        async with get_db_context() as db:
            repo = TelephonyRepository(db)
            user = await db.get(User, user_id)
            if user is None:
                await repo.mark_notification_delivered(call_id)  # nothing to deliver
                skipped += 1
                continue
            try:
                await NotificationDispatcher().dispatch(
                    user=user,
                    content=payload.get("content", ""),
                    task_type="phone_call",
                    target_id=str(call_id),
                    metadata={"call_status": call_status, "recovered": True},
                    db=db,
                    title=payload.get("title"),
                )
            except Exception as exc:  # noqa: BLE001 — one failure must not stop the batch
                await repo.record_notification_failure(call_id, max_attempts=max_attempts)
                logger.warning(
                    "telephony_notification_recover_failed",
                    call_id=str(call_id),
                    error_type=type(exc).__name__,
                )
                failed += 1
                continue
            await repo.mark_notification_delivered(call_id)
            delivered += 1

    telephony_notification_recovered_total.labels(result="delivered").inc(delivered)
    telephony_notification_recovered_total.labels(result="failed").inc(failed)
    telephony_notification_recovered_total.labels(result="skipped").inc(skipped)
    logger.info(
        "telephony_notifications_recovered",
        delivered=delivered,
        failed=failed,
        skipped=skipped,
    )


async def telephony_return_reaper() -> None:
    """Replay return SYNTHESES a crash stranded before completion (T1 approach A).

    The webhook handler commits an encrypted ``RECEIVED`` inbox row BEFORE the 200,
    so a crash during the fire-and-forget synthesis is recoverable. This reaper
    (single-instance under leader election + ``max_instances=1``):

    1. retires inbox rows past the max-age cutoff to ``FAILED`` (purging the
       encrypted transcript), so a permanently-failing synthesis stops retrying;
    2. re-runs :func:`process_completed_call` for ``RECEIVED`` rows older than the
       grace window (so the live dispatch of a just-received webhook is not raced),
       decrypting the persisted payload. ``process_completed_call`` is idempotent
       and, on success, purges the transcript via ``mark_completed``.
    """
    import json

    from src.core.security.utils import decrypt_data
    from src.domains.telephony.return_synthesis import process_completed_call
    from src.infrastructure.observability.metrics_telephony import (
        telephony_return_recovered_total,
    )

    now = datetime.now(UTC)
    grace_cutoff = now - timedelta(seconds=settings.telephony_return_grace_seconds)
    max_age_cutoff = now - timedelta(minutes=settings.telephony_return_max_age_minutes)

    async with get_db_context() as db:
        repo = TelephonyRepository(db)
        expired = await repo.expire_stale_returns(max_age_cutoff=max_age_cutoff)
        recoverable = await repo.fetch_recoverable_returns(
            grace_cutoff=grace_cutoff, max_age_cutoff=max_age_cutoff, limit=_RETURN_REAP_BATCH
        )
        # Snapshot before any commit (process_completed_call opens its own session).
        jobs = [(call.id, call.return_webhook_encrypted) for call in recoverable]

    if expired:
        telephony_return_recovered_total.labels(result="expired").inc(expired)

    recovered = failed = 0
    for call_id, encrypted in jobs:
        if not encrypted:
            continue
        try:
            payload = json.loads(decrypt_data(encrypted))
        except Exception as exc:  # noqa: BLE001 — a corrupt inbox row must not stop the batch
            logger.warning(
                "telephony_return_payload_undecodable",
                call_id=str(call_id),
                error_type=type(exc).__name__,
            )
            failed += 1
            continue
        try:
            await process_completed_call(call_id, payload)
        except Exception as exc:  # noqa: BLE001 — one failure must not stop the batch
            logger.warning(
                "telephony_return_recover_failed",
                call_id=str(call_id),
                error_type=type(exc).__name__,
            )
            failed += 1
            continue
        recovered += 1

    if recovered or failed or expired:
        telephony_return_recovered_total.labels(result="recovered").inc(recovered)
        telephony_return_recovered_total.labels(result="failed").inc(failed)
        logger.info(
            "telephony_returns_recovered",
            recovered=recovered,
            failed=failed,
            expired=expired,
        )
