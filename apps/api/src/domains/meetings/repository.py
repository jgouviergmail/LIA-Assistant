"""Repositories of the meetings bounded context (ADR-258).

Every lifecycle transition is ONE conditional ``UPDATE ... WHERE status = …``:
the database decides who wins a race (two workers, a stop racing a segment,
a duplicate upload), never a SELECT followed by a check in Python. The lease
clock is the database clock (``now()``) on both sides of every comparison.
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from src.domains.meetings.schemas import TemplateSelection

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

    async def begin_regenerate(
        self, meeting_id: UUID, *, values: dict[str, Any] | None = None
    ) -> bool:
        """``ready`` (idle) → ``ready`` + ``stage=synthesizing``. True iff this call did it.

        The status stays READY so the minutes remain readable while the new
        ones are computed; the stage is the progress the page shows. ``values``
        (ADR-259: the template the rebuild must use) ride on the same UPDATE,
        so the job never reads a ref the claim did not write.
        """
        stmt = (
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.status == MeetingStatus.READY,
                Meeting.stage.is_(None),
            )
            .values(
                stage=MeetingStage.SYNTHESIZING,
                last_error_code=None,
                last_error_message=None,
                **(values or {}),
            )
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

    async def clear_stale_regenerations(self, older_than_seconds: int) -> int:
        """``ready`` + ``stage`` older than the lease TTL → stage cleared, error recorded (ADR-259).

        A regeneration is a fire-and-forget without a lease: a hard kill leaves
        the stage set and every later attempt refused (``regeneration_in_progress``).
        """
        threshold = func.now() - text(":s * interval '1 second'").bindparams(s=older_than_seconds)
        stmt = (
            update(Meeting)
            .where(
                Meeting.status == MeetingStatus.READY,
                Meeting.stage.is_not(None),
                Meeting.updated_at < threshold,
            )
            .values(stage=None, last_error_code="regeneration_interrupted", last_error_message="")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def set_template(self, meeting_id: UUID, *, ref: str, name: str) -> None:
        """Remember the template chosen for a meeting before its minutes exist (ADR-259)."""
        await self.db.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(template_ref=ref, template_name=name)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def count_derived(self, meeting_id: UUID) -> int:
        """How many minutes were produced from this meeting's transcript (reformat 'new')."""
        total = await self.db.scalar(
            select(func.count()).select_from(Meeting).where(Meeting.source_meeting_id == meeting_id)
        )
        return int(total or 0)

    async def create_from_transcript(
        self, source: Meeting, *, values: dict[str, Any], rag_enabled: bool
    ) -> Meeting:
        """A new meeting row derived from ``source``'s transcript (reformat 'new', ADR-259)."""
        return await self.create(
            derived_meeting_values(source, template_values=values, rag_enabled=rag_enabled)
        )

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


#: What a derived meeting copies from its source: the facts of the recording and
#: of the transcription — never the audio, never the transcription price.
_DERIVED_COPIED_COLUMNS: tuple[str, ...] = (
    "user_id",
    "audio_format",
    "segment_count",
    "audio_bytes",
    "audio_duration_seconds",
    "audio_gaps",
    "started_at",
    "stopped_at",
    "client_timezone",
    "location_lat",
    "location_lon",
    "location_accuracy_m",
    "location_label",
    "calendar_event_id",
    "calendar_provider",
    "stt_provider",
    "stt_model",
    "stt_language_hint",
    "stt_detected_language",
    "stt_diarized",
    "stt_audio_seconds",
    "transcript_encrypted",
)


def derived_meeting_values(
    source: Any, *, template_values: dict[str, Any], rag_enabled: bool
) -> dict[str, Any]:
    """The column values of new minutes derived from ``source``'s transcript (ADR-259).

    READY with the synthesizing stage and no report: the page shows « writing »
    until the regeneration publishes the minutes. No audio (``audio_path`` NULL,
    purged now), no STT price (paid once, by the source), its own knowledge-space
    document (``index_state`` pending), and the template values the caller decided.
    """
    values: dict[str, Any] = {column: getattr(source, column) for column in _DERIVED_COPIED_COLUMNS}
    values.update(
        {
            "source_meeting_id": source.id,
            "status": MeetingStatus.READY,
            "stage": MeetingStage.SYNTHESIZING,
            "audio_path": None,
            "audio_purged_at": datetime.now(UTC),
            "keep_audio_until": None,
            "stt_cost_eur": None,
            "transcript_deleted_at": None,
            "template_snapshot": None,
            "report_generated": None,
            "report_current": None,
            "report_edited_at": None,
            "index_state": MeetingIndexState.PENDING if rag_enabled else MeetingIndexState.DISABLED,
            "template_selection": TemplateSelection.USER.value,
            "template_selection_reason": None,
        }
    )
    values.update(template_values)
    return values


class MeetingTemplateRepository(BaseRepository[MeetingTemplate]):
    """The user's own minutes templates (ADR-259: several per user, by name)."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, MeetingTemplate)

    async def list_for_user(self, user_id: UUID) -> list[MeetingTemplate]:
        """Every template the user owns, by name."""
        result = await self.db.execute(
            select(MeetingTemplate)
            .where(MeetingTemplate.user_id == user_id)
            .order_by(MeetingTemplate.name.asc(), MeetingTemplate.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, template_id: UUID, user_id: UUID) -> MeetingTemplate | None:
        """One template, only when it belongs to ``user_id``."""
        result = await self.db.execute(
            select(MeetingTemplate).where(
                MeetingTemplate.id == template_id, MeetingTemplate.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def count_for_user(self, user_id: UUID) -> int:
        """How many templates the user keeps (the cap's oracle)."""
        total = await self.db.scalar(
            select(func.count())
            .select_from(MeetingTemplate)
            .where(MeetingTemplate.user_id == user_id)
        )
        return int(total or 0)


class MeetingPreferenceRepository(BaseRepository[MeetingPreference]):
    """Per-user preferences (one row, created on first write)."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, MeetingPreference)

    async def clear_default_template_if(self, user_id: UUID, ref: str) -> bool:
        """Back to automatic when the default template pointed at ``ref`` (no commit here).

        Returns:
            True when a preference was reset — the caller tells the user.
        """
        result = await self.db.execute(
            update(MeetingPreference)
            .where(
                MeetingPreference.user_id == user_id,
                MeetingPreference.default_template_ref == ref,
            )
            .values(default_template_ref=None)
            .execution_options(synchronize_session=False)
        )
        return bool(getattr(result, "rowcount", 0) or 0)

    async def get_for_user(self, user_id: UUID) -> MeetingPreference | None:
        result = await self.db.execute(
            select(MeetingPreference).where(MeetingPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()
