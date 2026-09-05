"""Meeting lifecycle service (ADR-258): recording, minutes edition, preferences.

Every access is scoped by owner (private resource: absence and foreign
ownership both read as 404). Refusals carry a stable ``code`` in a structured
``detail`` so the client can explain them; nothing here fakes a success.
The processing pipeline itself lives in ``processing.py`` (stop hands over).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, NoReturn

import structlog
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.security.utils import decrypt_data
from src.domains.meetings.audio_store import (
    AudioStorageError,
    MeetingAudioStore,
    pcm_duration_seconds,
)
from src.domains.meetings.delivery import (
    MinutesDeliveryError,
    pdf_filename,
    render_pdf,
    send_minutes_email,
)
from src.domains.meetings.engine import ResolvedEngine, resolve_engine
from src.domains.meetings.models import (
    Meeting,
    MeetingAudioFormat,
    MeetingPreference,
    MeetingStatus,
    MeetingSttEnginePreference,
)
from src.domains.meetings.repository import (
    LIVE_STATUSES,
    MeetingPreferenceRepository,
    MeetingRepository,
)
from src.domains.meetings.schemas import (
    EngineInfo,
    MeetingDetailResponse,
    MeetingLimits,
    MeetingPatchRequest,
    MeetingPreferencesResponse,
    MeetingPreferencesUpdate,
    MeetingReport,
    MeetingSegmentAck,
    MeetingStartRequest,
    MeetingStartResponse,
    MeetingStopRequest,
    MeetingSummary,
    TemplateSelection,
    TranscriptTurn,
)
from src.domains.meetings.template_service import MeetingTemplateService, ResolvedTemplate
from src.domains.meetings.templates import parse_sections
from src.domains.usage_limits.service import UsageLimitService
from src.infrastructure.observability.metrics_meetings import (
    meeting_segments_received_total,
    meetings_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


# ============================================================================
# Exception helpers (pattern: core/exceptions.py raise_* functions)
# ============================================================================


def raise_meeting_not_found(meeting_id: uuid.UUID) -> NoReturn:
    """404 — a foreign or missing meeting reads the same (hide_existence)."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "meeting_not_found"},
        log_event="meeting_not_found",
        meeting_id=str(meeting_id),
    )


def worker_stale(meeting: Meeting) -> bool:
    """A ``processing`` row nobody is working on: its lease is absent or past.

    The reaper applies the same predicate on the database clock; this reading
    serves the page and the delete pre-check, where a few seconds of skew move
    a button, never a transition (the transition itself is conditional in SQL).
    """
    if meeting.status is not MeetingStatus.PROCESSING:
        return False
    lease = meeting.lease_expires_at
    return lease is None or lease < datetime.now(UTC)


def raise_meeting_conflict(code: str, **extra: Any) -> NoReturn:
    """409 with a stable code the client explains (already recording, not live, gaps…)."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, **extra},
        log_event=f"meeting_{code}",
        **{k: v for k, v in extra.items() if k != "missing"},
    )


def raise_meeting_too_large(code: str, **extra: Any) -> NoReturn:
    """413 — segment over the byte cap or recording over the duration cap."""
    raise BaseAPIException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={"code": code, **extra},
        log_event=f"meeting_{code}",
        **extra,
    )


def raise_meeting_refused(
    code: str, status_code: int = status.HTTP_429_TOO_MANY_REQUESTS
) -> NoReturn:
    """429 — usage limit or start rate limit; the user acts, the API explains."""
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code},
        log_event=f"meeting_{code}",
    )


def raise_meeting_storage_unavailable() -> NoReturn:
    """507 — the disk refused the segment; the client backs off and keeps its queue."""
    raise BaseAPIException(
        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        detail={"code": "storage_unavailable"},
        log_level="error",
        log_event="meeting_storage_unavailable",
    )


def raise_meeting_delivery_failed(code: str) -> NoReturn:
    """502: the SMTP relay refused the minutes (``code`` is the frontend key)."""
    raise BaseAPIException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": code},
        log_event="meeting_delivery_failed",
        code=code,
    )


def _selection_or_none(value: str | None) -> TemplateSelection | None:
    """The stored selection as its enum; an unknown historical value reads as absent."""
    try:
        return TemplateSelection(value) if value else None
    except ValueError:
        return None


def total_cost_eur(meeting: Meeting) -> float | None:
    """Transcription + minutes, or None while nothing priced was spent.

    A None on one side is an unknown price, not a zero: it neither hides the
    other side nor turns into a free claim (ADR-185, a count is exact or absent).
    """
    parts = [c for c in (meeting.stt_cost_eur, meeting.synthesis_cost_eur) if c is not None]
    return round(sum(parts), 6) if parts else None


# ============================================================================
# Service
# ============================================================================


class MeetingService:
    """Recording lifecycle + minutes edition + preferences (templates: template_service).

    Class-based service (``AttachmentService`` pattern): receives the session,
    owns its repositories and the audio store.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = MeetingRepository(db)
        self.preference_repo = MeetingPreferenceRepository(db)
        self.store = MeetingAudioStore(settings.meetings_storage_path)

    # ------------------------------------------------------------------ limits

    def limits(self) -> MeetingLimits:
        """Every bound the server enforces, published to the client (ADR-184)."""
        return MeetingLimits(
            segment_seconds=settings.meetings_segment_seconds,
            segment_max_seconds=settings.meetings_segment_max_seconds,
            segment_max_bytes=settings.meetings_segment_max_bytes,
            max_duration_minutes=settings.meetings_max_duration_minutes,
            silence_prompt_minutes=settings.meetings_silence_prompt_minutes,
        )

    @staticmethod
    def engine_info(engine: ResolvedEngine) -> EngineInfo:
        """The client-facing view of an engine (never the key)."""
        return EngineInfo(
            provider=engine.provider,
            model=engine.model,
            diarized=engine.diarized,
            cost_per_hour_eur=engine.cost_per_hour_eur,
            local_rtf_estimate=engine.local_rtf_estimate,
        )

    # ------------------------------------------------------------------- start

    async def start(self, user: Any, request: MeetingStartRequest) -> MeetingStartResponse:
        """Open a recording after every refusal the user should hear BEFORE speaking.

        Order: usage limits (synthesis is paid whatever the engine), start rate
        limit, engine availability, then the database — whose partial unique
        index is the only authority on "already recording".
        """
        user_id: uuid.UUID = user.id
        limit_check = await UsageLimitService.check_user_allowed(user_id)
        if not limit_check.allowed:
            raise_meeting_refused("usage_limit")

        await self._acquire_start_slot(user_id)

        preferences = await self.preference_repo.get_for_user(user_id)
        preference = preferences.stt_engine if preferences else MeetingSttEnginePreference.AUTO
        engine = resolve_engine(preference)
        if engine is None:
            raise_meeting_conflict("no_engine_available", preference=preference.value)

        language = request.language
        if language == "auto" and preferences and preferences.language != "auto":
            language = preferences.language
        template = await self._resolved_template(user_id, request.template_ref, user.language)
        now = datetime.now(UTC)
        try:
            meeting = await self.repo.create(
                {
                    "user_id": user_id,
                    "status": MeetingStatus.RECORDING,
                    "audio_format": request.audio_format,
                    "started_at": now,
                    "last_segment_at": now,
                    "client_timezone": request.timezone,
                    "location_lat": request.geolocation.lat if request.geolocation else None,
                    "location_lon": request.geolocation.lon if request.geolocation else None,
                    "location_accuracy_m": (
                        request.geolocation.accuracy_m if request.geolocation else None
                    ),
                    "stt_provider": engine.provider,
                    "stt_model": engine.model,
                    "stt_language_hint": None if language == "auto" else language,
                    "stt_diarized": engine.diarized,
                    # ADR-259: the template chosen for THIS meeting, if any.
                    "template_ref": str(template.ref) if template else None,
                    "template_name": template.name if template else None,
                    # Retention is decided at COMPLETION from the preference in force
                    # then (processing.py) — one authority, never two.
                }
            )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise_meeting_conflict("meeting_already_recording")

        logger.info(
            "meeting_started",
            meeting_id=str(meeting.id),
            user_id=str(user_id),
            audio_format=request.audio_format.value,
            provider=engine.provider.value,
        )
        return MeetingStartResponse(
            id=meeting.id,
            status=meeting.status,
            started_at=meeting.started_at,
            engine=self.engine_info(engine),
            limits=self.limits(),
        )

    async def _acquire_start_slot(self, user_id: uuid.UUID) -> None:
        """Sliding-window start limit; fails OPEN on Redis trouble (availability first)."""
        try:
            limiter = await get_rate_limiter()
            allowed = await limiter.acquire(
                key=f"meetings:start:{user_id}",
                max_calls=settings.meetings_rate_limit_starts,
                window_seconds=settings.meetings_rate_limit_window_seconds,
            )
        except Exception as exc:
            logger.warning("meeting_rate_limit_unavailable", user_id=str(user_id), error=str(exc))
            return
        if not allowed:
            raise_meeting_refused("rate_limited")

    # ---------------------------------------------------------------- segments

    async def accept_segment(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, *, sequence: int, body: bytes
    ) -> MeetingSegmentAck:
        """Store one segment; every bound is checked before a byte touches the disk."""
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status not in LIVE_STATUSES:
            raise_meeting_conflict("meeting_not_recording", status=meeting.status.value)
        if not body:
            raise_meeting_conflict("segment_empty", sequence=sequence)
        max_bytes = settings.meetings_segment_max_bytes
        if len(body) > max_bytes:
            raise_meeting_too_large("segment_too_large", max_bytes=max_bytes)
        if meeting.audio_format is MeetingAudioFormat.PCM_S16LE_16 and len(body) % 2:
            raise_meeting_conflict("segment_malformed", sequence=sequence)

        # Duration cap: the sequence number bounds what the client may still send.
        max_segments = (
            settings.meetings_max_duration_minutes * 60 // settings.meetings_segment_seconds
        )
        if sequence >= max_segments:
            raise_meeting_too_large(
                "duration_cap_reached", max_duration_minutes=settings.meetings_max_duration_minutes
            )

        try:
            added, replaced = await self.store.write_segment(user_id, meeting_id, sequence, body)
        except AudioStorageError as exc:
            logger.error("meeting_segment_write_failed", meeting_id=str(meeting_id), error=str(exc))
            raise_meeting_storage_unavailable()

        recorded = await self.repo.record_segment(meeting_id, sequence=sequence, added_bytes=added)
        if recorded is None:
            # Lost the race against a stop: the file is harmless, the client stops.
            raise_meeting_conflict("meeting_not_recording", status=MeetingStatus.STOPPED.value)
        if not replaced:
            meeting_segments_received_total.labels(format=meeting.audio_format.value).inc()
        new_status, segment_count, audio_bytes = recorded
        return MeetingSegmentAck(
            sequence=sequence,
            segment_count=segment_count,
            audio_bytes=audio_bytes,
            status=new_status,
        )

    # -------------------------------------------------------------------- stop

    async def stop(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, request: MeetingStopRequest
    ) -> Meeting:
        """``recording|interrupted → stopped`` once every expected segment is on disk.

        Missing segments are refused with their list so the client retries;
        ``allow_gaps`` finalizes anyway — the gap is a fact the minutes state.
        """
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status not in LIVE_STATUSES:
            raise_meeting_conflict("meeting_not_recording", status=meeting.status.value)
        expected = max(request.segment_count, meeting.segment_count)
        present = await self.store.list_sequences(user_id, meeting_id)
        if not present:
            raise_meeting_conflict("no_audio")
        missing = self.store.missing_sequences(present, expected)
        if missing and not request.allow_gaps:
            raise_meeting_conflict("segments_missing", missing=missing)

        stopped_at = datetime.now(UTC)
        if not await self.repo.stop(meeting_id, stopped_at=stopped_at, segment_count=expected):
            raise_meeting_conflict("meeting_not_recording", status=meeting.status.value)
        logger.info(
            "meeting_stopped",
            meeting_id=str(meeting_id),
            segments=len(present),
            gaps=len(missing),
            audio_bytes=meeting.audio_bytes,
        )
        return await self._fresh(meeting_id, user_id)

    async def resume(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """``interrupted → recording`` on the user's explicit request."""
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status is not MeetingStatus.INTERRUPTED:
            raise_meeting_conflict("meeting_not_interrupted", status=meeting.status.value)
        if not await self.repo.resume(meeting_id):
            raise_meeting_conflict("meeting_not_interrupted", status=meeting.status.value)
        return await self._fresh(meeting_id, user_id)

    async def retry(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """Requeue a stopped or failed meeting whose audio still exists."""
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status not in (MeetingStatus.STOPPED, MeetingStatus.FAILED):
            raise_meeting_conflict("meeting_not_retryable", status=meeting.status.value)
        if meeting.audio_purged_at is not None or not (
            meeting.audio_path or await self.store.list_sequences(user_id, meeting_id)
        ):
            raise_meeting_conflict("audio_unavailable")
        await self.repo.requeue_for_retry(
            meeting_id, from_statuses=(MeetingStatus.STOPPED, MeetingStatus.FAILED)
        )
        return await self._fresh(meeting_id, user_id)

    async def regenerate(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """Rebuild the minutes from the stored transcript with the CURRENT template."""
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status is not MeetingStatus.READY:
            raise_meeting_conflict("report_not_ready", status=meeting.status.value)
        if not meeting.transcript_encrypted:
            raise_meeting_conflict("transcript_unavailable")
        if not await self.repo.begin_regenerate(meeting_id):
            raise_meeting_conflict("regeneration_in_progress")
        return await self._fresh(meeting_id, user_id)

    # ----------------------------------------------------------------- reads

    async def get_live(self, user_id: uuid.UUID) -> Meeting | None:
        """The user's recording or interrupted meeting, if any."""
        return await self.repo.get_live_for_user(user_id)

    async def list_meetings(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Meeting], int]:
        """A page of meetings with the exact total."""
        return await self.repo.list_for_user(user_id, limit=limit, offset=offset)

    async def get(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """One owned meeting or 404."""
        return await self._owned(meeting_id, user_id)

    def to_summary(self, meeting: Meeting) -> MeetingSummary:
        """List projection with counts derived from the current minutes."""
        report = self._report_or_none(meeting.report_current)
        return MeetingSummary(
            id=meeting.id,
            status=meeting.status,
            stage=meeting.stage,
            title=report.title if report else None,
            started_at=meeting.started_at,
            stopped_at=meeting.stopped_at,
            audio_duration_seconds=meeting.audio_duration_seconds,
            participants_count=len(report.participants) if report else 0,
            action_items_count=(
                sum(len(section.action_items) for section in report.sections) if report else 0
            ),
            index_state=meeting.index_state,
            stt_provider=meeting.stt_provider,
            total_cost_eur=total_cost_eur(meeting),
            last_error_code=meeting.last_error_code,
            template_ref=meeting.template_ref,
            template_name=meeting.template_name,
            template_selection=_selection_or_none(meeting.template_selection),
            source_meeting_id=meeting.source_meeting_id,
        )

    def to_detail(
        self, meeting: Meeting, *, include_transcript: bool, derived_count: int = 0
    ) -> MeetingDetailResponse:
        """Page projection; the transcript is decrypted only on request."""
        report = self._report_or_none(meeting.report_current)
        transcript: list[TranscriptTurn] | None = None
        if include_transcript and meeting.transcript_encrypted:
            transcript = self.decrypt_transcript(meeting.transcript_encrypted)
        snapshot = parse_sections(meeting.template_snapshot) if meeting.template_snapshot else None
        return MeetingDetailResponse(
            id=meeting.id,
            status=meeting.status,
            stage=meeting.stage,
            started_at=meeting.started_at,
            stopped_at=meeting.stopped_at,
            last_segment_at=meeting.last_segment_at,
            client_timezone=meeting.client_timezone,
            audio_format=meeting.audio_format,
            segment_count=meeting.segment_count,
            audio_duration_seconds=meeting.audio_duration_seconds
            or (
                pcm_duration_seconds(meeting.audio_bytes)
                if meeting.audio_format is MeetingAudioFormat.PCM_S16LE_16
                else None
            ),
            audio_gaps=meeting.audio_gaps,
            keep_audio_until=meeting.keep_audio_until,
            audio_purged_at=meeting.audio_purged_at,
            location_lat=meeting.location_lat,
            location_lon=meeting.location_lon,
            location_label=meeting.location_label,
            calendar_event_id=meeting.calendar_event_id,
            stt_provider=meeting.stt_provider,
            stt_model=meeting.stt_model,
            stt_detected_language=meeting.stt_detected_language,
            stt_diarized=meeting.stt_diarized,
            stt_cost_eur=meeting.stt_cost_eur,
            synthesis_model=meeting.synthesis_model,
            synthesis_tokens_in=meeting.synthesis_tokens_in,
            synthesis_tokens_out=meeting.synthesis_tokens_out,
            synthesis_tokens_cache=meeting.synthesis_tokens_cache,
            synthesis_cost_eur=meeting.synthesis_cost_eur,
            total_cost_eur=total_cost_eur(meeting),
            has_transcript=bool(meeting.transcript_encrypted),
            report=report,
            report_is_edited=(
                meeting.report_generated is not None
                and meeting.report_current != meeting.report_generated
            ),
            report_edited_at=meeting.report_edited_at,
            template_snapshot=snapshot,
            index_state=meeting.index_state,
            indexed_at=meeting.indexed_at,
            email_sent_at=meeting.email_sent_at,
            last_error_code=meeting.last_error_code,
            last_error_message=meeting.last_error_message,
            attempts=meeting.attempts,
            max_attempts=settings.meetings_job_max_attempts,
            worker_stale=worker_stale(meeting),
            template_ref=meeting.template_ref,
            template_name=meeting.template_name,
            template_selection=_selection_or_none(meeting.template_selection),
            template_selection_reason=meeting.template_selection_reason,
            source_meeting_id=meeting.source_meeting_id,
            derived_count=derived_count,
            transcript=transcript,
        )

    @staticmethod
    def decrypt_transcript(encrypted: str) -> list[TranscriptTurn]:
        """Fernet → JSON turns → validated models."""
        raw = json.loads(decrypt_data(encrypted))
        return [TranscriptTurn.model_validate(turn) for turn in raw]

    @staticmethod
    def _report_or_none(raw: dict[str, Any] | None) -> MeetingReport | None:
        return MeetingReport.model_validate(raw) if raw else None

    # ---------------------------------------------------------------- minutes

    async def patch_report(
        self,
        user_id: uuid.UUID,
        meeting_id: uuid.UUID,
        request: MeetingPatchRequest,
        language: str | None = None,
    ) -> Meeting:
        """Edit the minutes (structured). Re-indexing is the caller's follow-up.

        ``template_ref`` (ADR-259) is accepted only while the meeting is live or
        queued: once processing started the template is the job's, and a READY
        meeting changes format through ``reformat``.
        """
        meeting = await self._owned(meeting_id, user_id)
        if request.template_ref is not None:
            await self._apply_template_choice(meeting, request.template_ref, language)
            if not request.touches_report:
                return await self._fresh(meeting_id, user_id)
        report = self._report_or_none(meeting.report_current)
        if report is None and (request.title or request.participants or request.sections):
            raise_meeting_conflict("report_not_ready", status=meeting.status.value)
        if report is not None:
            updated = report.model_copy(
                update={
                    key: value
                    for key, value in (
                        ("title", request.title),
                        ("participants", request.participants),
                        ("sections", request.sections),
                    )
                    if value is not None
                }
            )
            MeetingReport.model_validate(updated.model_dump())
            report = updated
        await self.repo.set_report_current(
            meeting_id,
            report=report.model_dump(mode="json") if report else meeting.report_current,
            edited_at=datetime.now(UTC),
            location_label=request.location_label,
            touch_location=request.location_label is not None,
        )
        return await self._fresh(meeting_id, user_id)

    async def reset_report(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """``report_current ← report_generated`` (the model's version is immutable)."""
        meeting = await self._owned(meeting_id, user_id)
        if not meeting.report_generated:
            raise_meeting_conflict("report_not_ready", status=meeting.status.value)
        await self.repo.set_report_current(
            meeting_id,
            report=meeting.report_generated,
            edited_at=datetime.now(UTC),
            location_label=None,
            touch_location=False,
        )
        return await self._fresh(meeting_id, user_id)

    async def delete_transcript(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Meeting:
        """Purge the transcript, keep the minutes."""
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status in LIVE_STATUSES or meeting.status is MeetingStatus.PROCESSING:
            raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
        await self.repo.delete_transcript(meeting_id, deleted_at=datetime.now(UTC))
        return await self._fresh(meeting_id, user_id)

    # ----------------------------------------------------------------- delete

    async def delete(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> None:
        """Everything: the knowledge-space projection first, then the row, then the files.

        The RAG document is a projection of the minutes, never a copy that may
        outlive them: it goes (chunks, row, file) before the meeting row does,
        so a failure there leaves the meeting in place for a retry rather than
        an orphaned transcript-derived document in the user's space (the third
        runtime proof found three such orphans behind three deleted meetings).
        """
        meeting = await self._owned(meeting_id, user_id)
        if meeting.status is MeetingStatus.PROCESSING and not worker_stale(meeting):
            raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
        was_live = meeting.status in LIVE_STATUSES
        await self._delete_projection(meeting)
        # The database decides with its own clock: a claim that raced this
        # delete keeps the row (a processing row never has a projection yet).
        if not await self.repo.delete_unless_leased(meeting_id):
            raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
        await self.db.commit()
        await self.store.purge_meeting(user_id, meeting_id)
        meetings_total.labels(status="discarded" if was_live else "deleted").inc()
        logger.info("meeting_deleted", meeting_id=str(meeting_id), user_id=str(user_id))

    async def _delete_projection(self, meeting: Meeting) -> None:
        """Remove the meeting's RAG document with its chunks and file, if it has one."""
        if meeting.rag_document_id is None:
            return
        from src.domains.rag_spaces.repository import RAGDocumentRepository
        from src.domains.rag_spaces.service import RAGSpaceService

        document = await RAGDocumentRepository(self.db).get_by_id(meeting.rag_document_id)
        if document is None:
            return  # already gone (deleted from the space by hand): nothing to project away
        await RAGSpaceService(self.db).delete_document(
            document.space_id, document.id, meeting.user_id
        )
        logger.info(
            "meeting_projection_deleted",
            meeting_id=str(meeting.id),
            document_id=str(document.id),
        )

    # ------------------------------------------------------------ preferences

    async def get_preferences(self, user_id: uuid.UUID) -> MeetingPreferencesResponse:
        row = await self.preference_repo.get_for_user(user_id)
        return self._preferences_response(row)

    async def put_preferences(
        self, user_id: uuid.UUID, request: MeetingPreferencesUpdate, language: str | None = None
    ) -> MeetingPreferencesResponse:
        """Replace the preferences; the retention is clamped, the default template resolved.

        A ``default_template_ref`` reaches the row only once resolved (built-in
        key or owned row): a bad reference never becomes a stored default.
        """
        keep_hours = min(request.keep_audio_hours, settings.meetings_audio_retention_hours_max)
        if request.default_template_ref is not None:
            await MeetingTemplateService(self.db).resolve(
                user_id, request.default_template_ref, language
            )
        payload = {
            "stt_engine": request.stt_engine,
            "language": request.language,
            "auto_email": request.auto_email,
            "keep_audio_hours": keep_hours,
            "default_template_ref": request.default_template_ref,
        }
        row = await self.preference_repo.get_for_user(user_id)
        if row is None:
            row = await self.preference_repo.create({"user_id": user_id, **payload})
        else:
            row = await self.preference_repo.update(row, payload)
        await self.db.commit()
        return self._preferences_response(row)

    @staticmethod
    def _preferences_response(row: MeetingPreference | None) -> MeetingPreferencesResponse:
        return MeetingPreferencesResponse(
            stt_engine=row.stt_engine if row else MeetingSttEnginePreference.AUTO,
            language=row.language if row else "auto",
            auto_email=row.auto_email if row else False,
            keep_audio_hours=row.keep_audio_hours if row else 0,
            default_template_ref=row.default_template_ref if row else None,
            keep_audio_hours_max=settings.meetings_audio_retention_hours_max,
        )

    # ---------------------------------------------------------------- delivery

    async def _ready_with_report(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> tuple[Meeting, MeetingReport]:
        meeting = await self._owned(meeting_id, user_id)
        report = self._report_or_none(meeting.report_current)
        if meeting.status is not MeetingStatus.READY or report is None:
            raise_meeting_conflict("report_not_ready", status=meeting.status.value)
        return meeting, report

    async def pdf(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, *, language: str | None
    ) -> tuple[bytes, str]:
        """The current minutes as PDF bytes plus their download filename."""
        meeting, report = await self._ready_with_report(user_id, meeting_id)
        return (
            render_pdf(meeting, report, language=language or "", gaps=meeting.audio_gaps),
            pdf_filename(meeting, report),
        )

    async def email(self, user: Any, meeting_id: uuid.UUID) -> Meeting:
        """Email the current minutes to the user's own address from the platform sender."""
        meeting, report = await self._ready_with_report(user.id, meeting_id)
        try:
            await send_minutes_email(
                self.db,
                user_id=user.id,
                recipient=str(user.email),
                meeting=meeting,
                report=report,
                language=str(user.language or ""),
                gaps=meeting.audio_gaps,
            )
        except MinutesDeliveryError as exc:
            raise_meeting_delivery_failed(exc.code)
        return await self._fresh(meeting_id, user.id)

    # ----------------------------------------------------------------- helpers

    async def _apply_template_choice(
        self, meeting: Meeting, ref: str, language: str | None
    ) -> None:
        """Remember the template for a meeting that has not been processed yet (ADR-259)."""
        if meeting.status not in (*LIVE_STATUSES, MeetingStatus.STOPPED):
            raise_meeting_conflict("template_locked", status=meeting.status.value)
        template = await self._resolved_template(meeting.user_id, ref, language)
        assert template is not None  # ref is not None here
        await self.repo.set_template(meeting.id, ref=str(template.ref), name=template.name)

    async def _resolved_template(
        self, user_id: uuid.UUID, ref: str | None, language: str | None
    ) -> ResolvedTemplate | None:
        """A template reference the user may use, or ``None`` when none was given."""
        if ref is None:
            return None
        return await MeetingTemplateService(self.db).resolve(user_id, ref, language)

    async def detail(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, *, include_transcript: bool
    ) -> MeetingDetailResponse:
        """The page projection, with the exact count of minutes derived from it."""
        meeting = await self._owned(meeting_id, user_id)
        derived = await self.repo.count_derived(meeting_id)
        return self.to_detail(meeting, include_transcript=include_transcript, derived_count=derived)

    async def _owned(self, meeting_id: uuid.UUID, user_id: uuid.UUID) -> Meeting:
        meeting = await self.repo.get_for_user(meeting_id, user_id)
        if meeting is None:
            raise_meeting_not_found(meeting_id)
        return meeting

    async def _fresh(self, meeting_id: uuid.UUID, user_id: uuid.UUID) -> Meeting:
        """Re-read AFTER a bulk UPDATE.

        The repository's transitions run as ``UPDATE … WHERE`` statements with
        ``synchronize_session=False``: the row already loaded in this session's
        identity map is NOT touched, so a plain re-select would hand back the
        pre-transition values (measured 2026-09-03: a stop answered
        ``status: recording``). Expiring the map first makes the re-select real.
        """
        self.db.expire_all()
        return await self._owned(meeting_id, user_id)
