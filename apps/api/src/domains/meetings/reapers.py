"""Meetings background reapers (ADR-258).

- ``meetings_job_reaper``: marks silent recordings ``interrupted`` (the client is
  gone), returns processing jobs whose lease expired to ``stopped`` (the worker
  died) and re-drives ``stopped`` meetings nobody claimed (the fire-and-forget
  died before the claim). Every transition is a conditional UPDATE in the
  repository; this module only decides WHEN.
- ``meetings_audio_retention_reaper``: purges the audio of terminal meetings
  past their retention (or immediately when the user keeps nothing).

Both are registered flag-guarded in ``startup/schedulers.py`` with jitter and
run under the scheduler leader election.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from src.core.config import settings
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.repository import MeetingRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_meetings import meeting_reaper_transitions_total

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
        requeued = await repo.requeue_expired_leases()
        orphans = await repo.fetch_stopped_orphans(
            grace_seconds=settings.meetings_reaper_interval_seconds, limit=_REDRIVE_BATCH
        )
        await db.commit()

    if interrupted:
        meeting_reaper_transitions_total.labels(outcome="interrupted").inc(interrupted)
    if requeued:
        meeting_reaper_transitions_total.labels(outcome="requeued").inc(requeued)
    if orphans:
        from src.domains.meetings.processing import launch_processing

        for meeting_id in orphans:
            launch_processing(meeting_id)
        meeting_reaper_transitions_total.labels(outcome="redriven").inc(len(orphans))
    if interrupted or requeued or orphans:
        logger.info(
            "meetings_reaped",
            interrupted=interrupted,
            requeued=requeued,
            redriven=len(orphans),
        )


async def meetings_audio_retention_reaper() -> None:
    """Delete kept audio past its deadline; the row keeps every derived fact."""
    store = MeetingAudioStore(settings.meetings_storage_path)
    purged = 0
    async with get_db_context() as db:
        repo = MeetingRepository(db)
        due = await repo.fetch_audio_to_purge(limit=_PURGE_BATCH)
        for meeting in due:
            await store.purge_meeting(meeting.user_id, meeting.id)
            await repo.mark_audio_purged(meeting.id, purged_at=datetime.now(UTC))
            purged += 1
        await db.commit()
    if purged:
        meeting_reaper_transitions_total.labels(outcome="audio_purged").inc(purged)
        logger.info("meetings_audio_purged", count=purged)
