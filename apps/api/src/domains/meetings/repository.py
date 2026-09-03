"""Repositories of the meetings bounded context (ADR-258).

Every lifecycle transition is ONE conditional ``UPDATE ... WHERE status = …``:
the database decides who wins a race (two workers, a stop racing a segment,
a duplicate upload), never a SELECT followed by a check in Python. The lease
clock is the database clock (``now()``) on both sides of every comparison.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.meetings.models import (
    Meeting,
    MeetingIndexState,
    MeetingPreference,
    MeetingStage,
    MeetingStatus,
    MeetingTemplate,
)

# Statuses under which a recording still accepts segments.
LIVE_STATUSES: tuple[MeetingStatus, ...] = (MeetingStatus.RECORDING, MeetingStatus.INTERRUPTED)


def _lease_from_now(ttl_seconds: int) -> Any:
    """``now() + ttl`` as a database expression (single clock)."""
    return func.now() + text(":ttl * interval '1 second'").bindparams(ttl=ttl_seconds)


class MeetingRepository(BaseRepository[Meeting]):
    """Meetings: reads scoped by owner, transitions as atomic conditional updates."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Meeting)

    # ------------------------------------------------------------------ reads

    async def get_for_user(self, meeting_id: UUID, user_id: UUID) -> Meeting | None:
        """One meeting, only when it belongs to ``user_id``."""
        result = await self.db.execute(
            select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_live_for_user(self, user_id: UUID) -> Meeting | None:
        """The recording or interrupted meeting of the user, if any (at most one live)."""
        result = await self.db.execute(
            select(Meeting)
            .where(Meeting.user_id == user_id, Meeting.status.in_(LIVE_STATUSES))
            .order_by(Meeting.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Meeting], int]:
        """A page of the user's meetings, newest first, with the EXACT total (ADR-185)."""
        total = await self.db.scalar(
            select(func.count()).select_from(Meeting).where(Meeting.user_id == user_id)
        )
        rows = await self.db.execute(
            select(Meeting)
            .where(Meeting.user_id == user_id)
            .order_by(Meeting.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total or 0)

    # ------------------------------------------------------- recording phase

    async def record_segment(
        self, meeting_id: UUID, *, sequence: int, added_bytes: int
    ) -> tuple[MeetingStatus, int, int] | None:
        """Account one accepted segment; an interrupted recording resumes.

        ``segment_count`` becomes ``max(segment_count, sequence + 1)`` so an
        out-of-order or duplicated upload never shrinks it; ``added_bytes`` is 0
        when the segment replaced an identical earlier upload.

        Returns:
            ``(status, segment_count, audio_bytes)`` AFTER the update — read from
            RETURNING, never from the identity map (a bulk UPDATE leaves the
            loaded row stale) — or ``None`` when the meeting no longer accepts
            segments (stopped, processing, ready, failed): the caller answers 409.
        """
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status.in_(LIVE_STATUSES))
            .values(
                segment_count=func.greatest(Meeting.segment_count, sequence + 1),
                audio_bytes=Meeting.audio_bytes + added_bytes,
                last_segment_at=func.now(),
                status=MeetingStatus.RECORDING,
            )
            .returning(Meeting.status, Meeting.segment_count, Meeting.audio_bytes)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        await self.db.commit()
        return (MeetingStatus(row[0]), int(row[1]), int(row[2])) if row else None

    async def stop(self, meeting_id: UUID, *, stopped_at: datetime, segment_count: int) -> bool:
        """``recording|interrupted → stopped``. True iff this call did it."""
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status.in_(LIVE_STATUSES))
            .values(
                status=MeetingStatus.STOPPED,
                stopped_at=stopped_at,
                segment_count=func.greatest(Meeting.segment_count, segment_count),
                last_error_code=None,
                last_error_message=None,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def resume(self, meeting_id: UUID) -> bool:
        """``interrupted → recording``. True iff this call did it."""
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.INTERRUPTED)
            .values(status=MeetingStatus.RECORDING, last_segment_at=func.now())
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def interrupt_stale_recordings(self, stale_minutes: int) -> int:
        """``recording → interrupted`` for recordings silent for ``stale_minutes``.

        A recording without any segment yet is judged on its start time.
        """
        threshold = func.now() - text(":m * interval '1 minute'").bindparams(m=stale_minutes)
        stmt = (
            update(Meeting)
            .where(
                Meeting.status == MeetingStatus.RECORDING,
                func.coalesce(Meeting.last_segment_at, Meeting.started_at) < threshold,
            )
            .values(status=MeetingStatus.INTERRUPTED)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ------------------------------------------------------ processing phase

    async def claim_stopped(self, meeting_id: UUID, *, worker_id: str, lease_ttl_s: int) -> bool:
        """``stopped → processing`` with a lease. True iff this worker won the claim."""
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.STOPPED)
            .values(
                status=MeetingStatus.PROCESSING,
                stage=MeetingStage.NORMALIZING,
                lease_expires_at=_lease_from_now(lease_ttl_s),
                heartbeat_at=func.now(),
                attempts=Meeting.attempts + 1,
                worker_id=worker_id,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def heartbeat(
        self, meeting_id: UUID, *, worker_id: str, lease_ttl_s: int, stage: MeetingStage
    ) -> bool:
        """Renew the lease and publish the stage if this worker still holds the job."""
        stmt = (
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.worker_id == worker_id,
                Meeting.status == MeetingStatus.PROCESSING,
            )
            .values(
                lease_expires_at=_lease_from_now(lease_ttl_s),
                heartbeat_at=func.now(),
                stage=stage,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def release_unprocessed(self, meeting_id: UUID, *, code: str, message: str) -> None:
        """``processing → stopped`` WITHOUT consuming an attempt.

        For refusals that are not failures of the pipeline (usage limit reached,
        no engine available): the meeting waits with a reason the user can act
        on, and a later retry starts with the same retry budget.
        """
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.PROCESSING)
            .values(
                status=MeetingStatus.STOPPED,
                stage=None,
                attempts=func.greatest(Meeting.attempts - 1, 0),
                lease_expires_at=None,
                worker_id=None,
                last_error_code=code,
                last_error_message=message,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def fail_or_retry(
        self, meeting_id: UUID, *, code: str, message: str, max_attempts: int
    ) -> MeetingStatus:
        """``processing → stopped`` (bounded retry) or ``→ failed`` (dead-letter).

        ``attempts`` was incremented by the claim, so a meeting claimed
        ``max_attempts`` times is dead-lettered.
        """
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.PROCESSING)
            .values(
                status=case(
                    (Meeting.attempts >= max_attempts, MeetingStatus.FAILED),
                    else_=MeetingStatus.STOPPED,
                ),
                stage=None,
                lease_expires_at=None,
                worker_id=None,
                last_error_code=code,
                last_error_message=message,
            )
            .returning(Meeting.status)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        await self.db.commit()
        return MeetingStatus(row[0]) if row else MeetingStatus.FAILED

    async def fail_permanently(self, meeting_id: UUID, *, code: str, message: str) -> None:
        """``processing → failed`` for causes a retry cannot fix (no speech, too long)."""
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.PROCESSING)
            .values(
                status=MeetingStatus.FAILED,
                stage=None,
                lease_expires_at=None,
                worker_id=None,
                last_error_code=code,
                last_error_message=message,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def complete(self, meeting_id: UUID, *, worker_id: str, values: dict[str, Any]) -> bool:
        """``processing → ready`` with the results, atomically, if this worker holds the job.

        ``values`` carries the transcript, minutes, engine facts and index state;
        the lease is cleared and the retry budget reset in the same statement.
        """
        stmt = (
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.status == MeetingStatus.PROCESSING,
                Meeting.worker_id == worker_id,
            )
            .values(
                status=MeetingStatus.READY,
                stage=None,
                attempts=0,
                lease_expires_at=None,
                worker_id=None,
                heartbeat_at=None,
                last_error_code=None,
                last_error_message=None,
                **values,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def requeue_expired_leases(self) -> int:
        """``processing → stopped`` for jobs whose worker stopped heartbeating."""
        stmt = (
            update(Meeting)
            .where(
                Meeting.status == MeetingStatus.PROCESSING,
                (Meeting.lease_expires_at.is_(None)) | (Meeting.lease_expires_at < func.now()),
            )
            .values(status=MeetingStatus.STOPPED, stage=None, lease_expires_at=None, worker_id=None)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def fetch_stopped_orphans(self, grace_seconds: int, limit: int) -> list[UUID]:
        """Stopped meetings nobody is processing after ``grace_seconds`` — re-drive them.

        ``FOR UPDATE SKIP LOCKED`` keeps several reaper instances from re-driving
        the same rows.
        """
        threshold = func.now() - text(":g * interval '1 second'").bindparams(g=grace_seconds)
        result = await self.db.execute(
            select(Meeting.id)
            .where(
                Meeting.status == MeetingStatus.STOPPED,
                func.coalesce(Meeting.heartbeat_at, Meeting.stopped_at, Meeting.updated_at)
                < threshold,
            )
            .order_by(Meeting.stopped_at.asc().nullsfirst())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [row[0] for row in result.all()]

    async def requeue_for_retry(
        self, meeting_id: UUID, *, from_statuses: tuple[MeetingStatus, ...]
    ) -> bool:
        """``failed|stopped → stopped`` with a fresh retry budget (user-triggered)."""
        stmt = (
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status.in_(from_statuses))
            .values(
                status=MeetingStatus.STOPPED,
                stage=None,
                attempts=0,
                lease_expires_at=None,
                worker_id=None,
                last_error_code=None,
                last_error_message=None,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    # ------------------------------------------------------------- minutes

    async def set_report_current(
        self,
        meeting_id: UUID,
        *,
        report: dict[str, Any] | None,
        edited_at: datetime,
        location_label: str | None,
        touch_location: bool,
    ) -> None:
        """Replace the user-visible minutes (and optionally the location label)."""
        values: dict[str, Any] = {"report_current": report, "report_edited_at": edited_at}
        if touch_location:
            values["location_label"] = location_label
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def set_index_state(
        self,
        meeting_id: UUID,
        *,
        state: MeetingIndexState,
        rag_document_id: UUID | None,
        indexed_at: datetime | None,
    ) -> None:
        """Record where the minutes stand in the knowledge space."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(index_state=state, rag_document_id=rag_document_id, indexed_at=indexed_at)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def set_email_sent(self, meeting_id: UUID, *, sent_at: datetime) -> None:
        """Remember that the minutes were emailed."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(email_sent_at=sent_at)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def delete_transcript(self, meeting_id: UUID, *, deleted_at: datetime) -> None:
        """Purge the transcript, keep the minutes."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(transcript_encrypted=None, transcript_deleted_at=deleted_at)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    # ---------------------------------------------------------- regenerate

    async def begin_regenerate(self, meeting_id: UUID) -> bool:
        """``ready`` (idle) → ``ready`` + ``stage=synthesizing``. True iff this call did it.

        The status stays READY so the minutes remain readable while the new
        ones are computed; the stage is the progress the page shows.
        """
        stmt = (
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.status == MeetingStatus.READY,
                Meeting.stage.is_(None),
            )
            .values(stage=MeetingStage.SYNTHESIZING, last_error_code=None, last_error_message=None)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def finish_regenerate(
        self,
        meeting_id: UUID,
        *,
        values: dict[str, Any],
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_cache: int = 0,
        cost_eur: float | None = None,
    ) -> None:
        """Publish regenerated minutes, clear the stage and ADD the pass to the meeting's spend.

        Every rebuild is paid; the row keeps the sum of every pass (the initial
        synthesis included) so the page states what the minutes cost in total.
        """
        spend: dict[str, Any] = {
            "synthesis_tokens_in": Meeting.synthesis_tokens_in + tokens_in,
            "synthesis_tokens_out": Meeting.synthesis_tokens_out + tokens_out,
            "synthesis_tokens_cache": Meeting.synthesis_tokens_cache + tokens_cache,
        }
        if cost_eur is not None:
            spend["synthesis_cost_eur"] = func.coalesce(Meeting.synthesis_cost_eur, 0.0) + cost_eur
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.READY)
            .values(stage=None, **values, **spend)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def fail_regenerate(self, meeting_id: UUID, *, code: str, message: str) -> None:
        """Clear the stage and record why the regeneration failed; the old minutes stay."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(stage=None, last_error_code=code, last_error_message=message)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    # --------------------------------------------------------- audio purge

    async def fetch_audio_to_purge(self, limit: int) -> list[Meeting]:
        """Terminal meetings whose audio outlived its retention."""
        result = await self.db.execute(
            select(Meeting)
            .where(
                Meeting.status.in_((MeetingStatus.READY, MeetingStatus.FAILED)),
                Meeting.audio_path.is_not(None),
                Meeting.audio_purged_at.is_(None),
                (Meeting.keep_audio_until.is_(None)) | (Meeting.keep_audio_until < func.now()),
            )
            .order_by(Meeting.stopped_at.asc().nullsfirst())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def mark_audio_purged(self, meeting_id: UUID, *, purged_at: datetime) -> None:
        """The audio files are gone."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(audio_path=None, audio_purged_at=purged_at)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()


class MeetingTemplateRepository(BaseRepository[MeetingTemplate]):
    """The user's default minutes template (one row at most in v1)."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, MeetingTemplate)

    async def get_default_for_user(self, user_id: UUID) -> MeetingTemplate | None:
        result = await self.db.execute(
            select(MeetingTemplate).where(
                MeetingTemplate.user_id == user_id, MeetingTemplate.is_default.is_(True)
            )
        )
        return result.scalar_one_or_none()


class MeetingPreferenceRepository(BaseRepository[MeetingPreference]):
    """Per-user preferences (one row, created on first write)."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, MeetingPreference)

    async def get_for_user(self, user_id: UUID) -> MeetingPreference | None:
        result = await self.db.execute(
            select(MeetingPreference).where(MeetingPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()
