"""Meetings background reapers (ADR-258).

- ``meetings_job_reaper``: marks silent recordings ``interrupted`` (the client is
  gone), fails imports whose upload went silent (``import_incomplete``, their
  chunks deleted — a half file can never be processed), returns processing
  jobs whose lease expired to ``stopped`` (the worker died) — or dead-letters
  them when the retry budget is already spent — and re-drives ``stopped``
  meetings nobody claimed (the fire-and-forget died before the claim). Every
  transition is a conditional UPDATE in the repository; this module only
  decides WHEN.
- ``meetings_audio_retention_reaper``: purges the audio of terminal meetings
  past their retention (or immediately when the user keeps nothing).

Both are registered flag-guarded in ``startup/schedulers.py`` with jitter and
run under the scheduler leader election.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.models import MeetingAudioFormat
from src.domains.meetings.repository import MeetingRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_meetings import (
    meeting_imports_total,
    meeting_reaper_transitions_total,
    meetings_total,
)

logger = structlog.get_logger(__name__)

# Per-sweep bounds (internal, not user-tuning knobs): the backlog drains
# deterministically across ticks instead of one tick doing unbounded work.
_REDRIVE_BATCH = 20
_PURGE_BATCH = 50


async def meetings_job_reaper() -> None:
    """Interrupt stale recordings, requeue expired leases, re-drive orphans."""
    async with get_db_context() as db:
        repo = MeetingRepository(db)
        interrupted = await repo.interrupt_stale_recordings(
            settings.meetings_recording_stale_minutes
        )
        abandoned = await repo.fail_stale_imports(settings.meetings_import_stale_minutes)
        requeued, dead_lettered = await repo.requeue_expired_leases(
            settings.meetings_job_max_attempts
        )
        # Fenced regeneration heartbeats determine expiry; legacy queued rows
        # fall back to their update timestamp after a hard kill.
        cleared = await repo.clear_stale_regenerations(settings.meetings_job_lease_ttl_seconds)
        orphans = await repo.fetch_stopped_orphans(
            grace_seconds=settings.meetings_reaper_interval_seconds, limit=_REDRIVE_BATCH
        )
        await db.commit()

    _count_transitions(
        interrupted=interrupted,
        requeued=requeued,
        dead_lettered=dead_lettered,
        regeneration_cleared=cleared,
    )
    if dead_lettered:
        meetings_total.labels(status="failed").inc(dead_lettered)
    if abandoned:
        await _purge_abandoned_imports(abandoned)
    if orphans:
        from src.domains.meetings.processing import launch_processing

        for meeting_id in orphans:
            launch_processing(meeting_id)
        meeting_reaper_transitions_total.labels(outcome="redriven").inc(len(orphans))
    if any((interrupted, abandoned, requeued, dead_lettered, cleared, orphans)):
        logger.info(
            "meetings_reaped",
            interrupted=interrupted,
            imports_abandoned=len(abandoned),
            requeued=requeued,
            dead_lettered=dead_lettered,
            regeneration_cleared=cleared,
            redriven=len(orphans),
        )


def _count_transitions(**counts: int) -> None:
    """Count each simple transition the sweep made, by its outcome label."""
    for outcome, count in counts.items():
        if count:
            meeting_reaper_transitions_total.labels(outcome=outcome).inc(count)


async def _purge_abandoned_imports(
    abandoned: list[tuple[UUID, UUID, MeetingAudioFormat]],
) -> None:
    """Delete the chunks of imports the sweep failed, after its commit: none will complete."""
    store = MeetingAudioStore(settings.meetings_storage_path)
    purged = [
        meeting_id
        for meeting_id, user_id, _ in abandoned
        if await store.purge_meeting(user_id, meeting_id)
    ]
    if purged:
        async with get_db_context() as db:
            repo = MeetingRepository(db)
            for meeting_id in purged:
                await repo.mark_audio_purged(meeting_id, purged_at=datetime.now(UTC))
    for _, _, audio_format in abandoned:
        meeting_imports_total.labels(format=audio_format.value, outcome="abandoned").inc()
    meeting_reaper_transitions_total.labels(outcome="import_abandoned").inc(len(abandoned))
    meetings_total.labels(status="failed").inc(len(abandoned))


async def meetings_audio_retention_reaper() -> None:
    """Delete kept audio past its deadline; the row keeps every derived fact."""
    store = MeetingAudioStore(settings.meetings_storage_path)
    purged = 0
    async with get_db_context() as db:
        repo = MeetingRepository(db)
        due = await repo.fetch_audio_to_purge(limit=_PURGE_BATCH)
        for meeting in due:
            if not await store.purge_meeting(meeting.user_id, meeting.id):
                continue
            await repo.mark_audio_purged(meeting.id, purged_at=datetime.now(UTC))
            purged += 1
        await db.commit()
    if purged:
        meeting_reaper_transitions_total.labels(outcome="audio_purged").inc(purged)
        logger.info("meetings_audio_purged", count=purged)
