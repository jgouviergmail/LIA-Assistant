"""The processing job of a stopped meeting (ADR-258).

``stopped → processing → ready | failed``, driven by ONE coroutine per meeting
launched fire-and-forget by the stop endpoint, the retry endpoint and the
reaper. The meeting row is the durable job (ADR-129): the claim is an atomic
conditional UPDATE, the lease is renewed by heartbeats that also publish the
stage, and a heartbeat that finds the lease gone aborts every later effect.

Stages, each timed in ``meeting_processing_stage_duration_seconds``:

1. **normalizing** — segments → one Opus file (ffmpeg), gaps counted, segments purged;
2. **transcribing** — the resolved engine (remote file call or local windows);
3. **synthesizing** — calendar/place enrichment, then the structured minutes;
4. **indexing** — the minutes reach the « Réunions » space (after ``ready``).

Refusals that are not pipeline failures (usage limit, no engine) release the
job WITHOUT consuming an attempt; transient failures go back to ``stopped`` for
the reaper to re-drive within the attempt budget; permanent ones dead-letter.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import MEETINGS_PROACTIVE_TASK_TYPE, MEETINGS_WORKER_ID_PREFIX
from src.core.i18n_meetings import get_notification_title
from src.core.security.utils import encrypt_data
from src.domains.meetings.audio_store import (
    AudioStorageError,
    MeetingAudioStore,
    normalized_mime_type,
    pcm_duration_seconds,
)
from src.domains.meetings.engine import ResolvedEngine, resolve_engine
from src.domains.meetings.enrichment import CalendarMatch, match_calendar_event, place_label
from src.domains.meetings.models import (
    Meeting,
    MeetingAudioFormat,
    MeetingIndexState,
    MeetingPreference,
    MeetingStage,
    MeetingStatus,
    MeetingSttEnginePreference,
)
from src.domains.meetings.repository import MeetingPreferenceRepository, MeetingRepository
from src.domains.meetings.schemas import MeetingReport, SectionKind, TemplateSection
from src.domains.meetings.synthesis import (
    SynthesisContext,
    SynthesisResult,
    SynthesisUsage,
    synthesize_minutes,
)
from src.domains.meetings.template_resolution import TemplateDecision, decide_template
from src.domains.meetings.templates import sections_to_json
from src.domains.meetings.transcription import (
    TranscriptionError,
    TranscriptionOutcome,
    transcribe_with_fallback,
)
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.structured_output import StructuredOutputError
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.observability.metrics_meetings import (
    meeting_failures_total,
    meeting_processing_stage_duration_seconds,
    meeting_recording_duration_seconds,
    meeting_stt_audio_seconds_total,
    meetings_total,
)

logger = structlog.get_logger(__name__)

#: Error codes stored on the row (``last_error_code``) — the frontend maps them.
ERROR_USAGE_LIMIT = "usage_limit"
ERROR_NO_ENGINE = "no_engine_available"
ERROR_NORMALIZE = "audio_normalize_failed"
ERROR_SYNTHESIS = "synthesis_failed"
ERROR_UNEXPECTED = "unexpected"


class LeaseLostError(RuntimeError):
    """Another worker owns the job now; nothing further may be written."""


def _worker_id() -> str:
    return f"{MEETINGS_WORKER_ID_PREFIX}-{os.getpid()}"


def launch_processing(meeting_id: UUID) -> None:
    """Drive a stopped meeting through processing, in the background."""
    safe_fire_and_forget(process_meeting(meeting_id), name=f"meeting_process_{meeting_id}")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


#: A transcript head is a teaser, not the minutes: bounded like a chat preview.
_SUMMARY_MAX_CHARS = 300


def _summary_text(report: MeetingReport) -> str:
    """The first paragraph-shaped content of the minutes, for the notification."""
    for section in report.sections:
        if section.kind is SectionKind.PARAGRAPH and section.paragraph:
            return section.paragraph
    for section in report.sections:
        if section.kind is SectionKind.BULLETS and section.bullets:
            return "\n".join(f"- {item}" for item in section.bullets)
    for section in report.sections:
        if section.kind is SectionKind.TRANSCRIPT and section.transcript:
            head = " ".join(f"{line.speaker} : {line.text}" for line in section.transcript[:3])
            return head if len(head) <= _SUMMARY_MAX_CHARS else head[: _SUMMARY_MAX_CHARS - 1] + "…"
    return ""


def _keep_audio_until(preference: MeetingPreference | None, now: datetime) -> datetime | None:
    hours = preference.keep_audio_hours if preference else 0
    hours = min(hours, settings.meetings_audio_retention_hours_max)
    return now + timedelta(hours=hours) if hours > 0 else None


def synthesis_cost_eur(usage: SynthesisUsage) -> float | None:
    """EUR cost of one synthesis pass from the administered price, or None.

    The pricing cache answers (0, 0) for a model it does not know: with tokens
    actually spent that is an unknown price, never a free one (ADR-185). A pass
    that spent no token costs an exact 0.0.
    """
    spent = usage.tokens_in + usage.tokens_out
    if spent == 0:
        return 0.0
    _usd, eur = get_cached_cost_usd_eur(
        model=usage.model_name,
        prompt_tokens=usage.tokens_in,
        completion_tokens=usage.tokens_out,
        cached_tokens=usage.tokens_cache,
    )
    return eur if eur > 0 else None


def _language_hint(preference: MeetingPreference | None, meeting: Meeting) -> str | None:
    hint = meeting.stt_language_hint or (preference.language if preference else None)
    return None if not hint or hint == "auto" else hint


class _Job:
    """State of one processing run — one instance per coroutine, never shared."""

    def __init__(self, meeting_id: UUID) -> None:
        self.meeting_id = meeting_id
        self.worker_id = _worker_id()
        self.store = MeetingAudioStore(settings.meetings_storage_path)
        self.stage_started = time.monotonic()
        self.stage: MeetingStage = MeetingStage.NORMALIZING

    async def heartbeat(self, repo: MeetingRepository) -> None:
        alive = await repo.heartbeat(
            self.meeting_id,
            worker_id=self.worker_id,
            lease_ttl_s=settings.meetings_job_lease_ttl_seconds,
            stage=self.stage,
        )
        if not alive:
            raise LeaseLostError(f"lease lost on meeting {self.meeting_id}")

    async def enter_stage(self, repo: MeetingRepository, stage: MeetingStage) -> None:
        elapsed = time.monotonic() - self.stage_started
        meeting_processing_stage_duration_seconds.labels(stage=self.stage.value).observe(elapsed)
        self.stage = stage
        self.stage_started = time.monotonic()
        await self.heartbeat(repo)

    def close_stage(self) -> None:
        elapsed = time.monotonic() - self.stage_started
        meeting_processing_stage_duration_seconds.labels(stage=self.stage.value).observe(elapsed)


# ----------------------------------------------------------------------------
# Stages
# ----------------------------------------------------------------------------


async def _normalize(job: _Job, meeting: Meeting) -> tuple[str, float, int]:
    """Segments → one Opus file. Returns ``(relative_path, duration, gaps)``."""
    present = await job.store.list_sequences(meeting.user_id, meeting.id)
    gaps = len(job.store.missing_sequences(present, meeting.segment_count))
    hint = (
        pcm_duration_seconds(await job.store.total_segment_bytes(meeting.user_id, meeting.id))
        if meeting.audio_format is MeetingAudioFormat.PCM_S16LE_16
        else None
    )
    path, duration = await job.store.normalize(
        meeting.user_id,
        meeting.id,
        audio_format=meeting.audio_format,
        duration_hint_seconds=hint,
    )
    try:
        await job.store.purge_segments(meeting.user_id, meeting.id)
    except AudioStorageError as exc:
        logger.warning("meeting_segments_purge_failed", meeting_id=str(meeting.id), error=str(exc))
    return job.store.relative(path), duration, gaps


async def _enrich(
    db: Any, meeting: Meeting, *, stopped_at: datetime, language: str
) -> tuple[CalendarMatch | None, str | None]:
    calendar = await match_calendar_event(
        db, user_id=meeting.user_id, started_at=meeting.started_at, stopped_at=stopped_at
    )
    label = meeting.location_label
    if label is None and meeting.location_lat is not None and meeting.location_lon is not None:
        label = await place_label(meeting.location_lat, meeting.location_lon, language=language)
    if label is None and calendar is not None and calendar.location:
        label = calendar.location
    return calendar, label


async def _synthesize(
    meeting: Meeting,
    outcome: TranscriptionOutcome,
    *,
    template: list[TemplateSection],
    language: str,
    stopped_at: datetime,
    location_label: str | None,
    calendar: CalendarMatch | None,
    gaps: int,
    capture: TokenCaptureHandler | None = None,
) -> SynthesisResult:
    context = SynthesisContext(
        language=language,
        timezone=meeting.client_timezone,
        started_at=meeting.started_at,
        stopped_at=stopped_at,
        duration_seconds=outcome.audio_duration_seconds,
        location_label=location_label,
        calendar_title=calendar.title if calendar else None,
        calendar_attendees=calendar.attendees if calendar else [],
        gaps=gaps,
        diarized=outcome.diarized,
    )
    return await synthesize_minutes(outcome.turns, template, context, capture=capture)


def _completion_values(
    *,
    meeting: Meeting,
    audio_path: str,
    duration: float,
    outcome: TranscriptionOutcome,
    synthesis: SynthesisResult,
    decision: TemplateDecision,
    calendar: CalendarMatch | None,
    location_label: str | None,
    keep_audio_until: datetime | None,
    gaps: int,
) -> dict[str, Any]:
    report = synthesis.report.model_dump(mode="json")
    return {
        "audio_path": audio_path,
        "audio_duration_seconds": duration,
        "audio_gaps": gaps,
        "keep_audio_until": keep_audio_until,
        "stt_provider": outcome.provider,
        "stt_model": outcome.model,
        "stt_detected_language": outcome.language_code,
        "stt_diarized": outcome.diarized,
        "stt_audio_seconds": outcome.audio_duration_seconds,
        "stt_cost_eur": outcome.cost_eur,
        "transcript_encrypted": encrypt_data(
            json.dumps([turn.model_dump() for turn in outcome.turns])
        ),
        "transcript_deleted_at": None,
        "calendar_event_id": calendar.event_id if calendar else meeting.calendar_event_id,
        "calendar_provider": calendar.provider if calendar else meeting.calendar_provider,
        "location_label": location_label,
        "template_snapshot": sections_to_json(decision.sections),
        "template_ref": str(decision.ref),
        "template_name": decision.name,
        "template_selection": decision.selection.value,
        "template_selection_reason": decision.reason,
        "synthesis_model": synthesis.usage.model_name,
        "synthesis_tokens_in": synthesis.usage.tokens_in,
        "synthesis_tokens_out": synthesis.usage.tokens_out,
        "synthesis_tokens_cache": synthesis.usage.tokens_cache,
        "synthesis_cost_eur": synthesis_cost_eur(synthesis.usage),
        "report_generated": report,
        "report_current": report,
        "report_edited_at": None,
        "index_state": (
            MeetingIndexState.PENDING if settings.rag_spaces_enabled else MeetingIndexState.DISABLED
        ),
    }


# ----------------------------------------------------------------------------
# After READY: index, notify, email, purge — each best effort, each logged
# ----------------------------------------------------------------------------


async def _notify_ready(
    db: Any,
    *,
    meeting: Meeting,
    user: Any,
    synthesis: SynthesisResult,
    outcome: TranscriptionOutcome,
    language: str,
    gaps: int,
) -> None:
    """Account the synthesis tokens and dispatch the « minutes ready » notification.

    Same contract as the proactive runner: the archived message carries the
    ``run_id`` that links it to ``token_usage_logs`` and the token/cost fields
    the chat bubble displays. Here the paid units are TWO — the transcription
    (audio, already recorded by the engine) and the minutes (tokens) — so the
    metadata states both and ``cost_eur`` is their sum: what this exchange cost.
    """
    from src.infrastructure.proactive.notification import NotificationDispatcher
    from src.infrastructure.proactive.tracking import (
        generate_proactive_run_id,
        track_proactive_tokens,
    )

    report, usage = synthesis.report, synthesis.usage
    run_id = generate_proactive_run_id(MEETINGS_PROACTIVE_TASK_TYPE, str(meeting.id))
    if usage.tokens_in or usage.tokens_out:
        await track_proactive_tokens(
            user_id=meeting.user_id,
            task_type=MEETINGS_PROACTIVE_TASK_TYPE,
            target_id=str(meeting.id),
            conversation_id=None,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache=usage.tokens_cache,
            model_name=usage.model_name,
            db=db,
            run_id=run_id,
        )
    await NotificationDispatcher().dispatch(
        user,
        content=f"**{report.title}**\n\n{_summary_text(report)}".strip(),
        task_type=MEETINGS_PROACTIVE_TASK_TYPE,
        target_id=str(meeting.id),
        metadata={
            "meeting_id": str(meeting.id),
            "title": report.title,
            "duration_seconds": outcome.audio_duration_seconds,
            "participants_count": len(report.participants),
            "action_items_count": sum(len(s.action_items) for s in report.sections),
            "template_name": meeting.template_name,
            "index_state": meeting.index_state.value if meeting.index_state else None,
            "stt_provider": outcome.provider.value,
            "gaps": gaps,
            **_cost_metadata(meeting, outcome, usage),
        },
        db=db,
        title=get_notification_title(language),
        run_id=run_id,
    )


def _cost_metadata(
    meeting: Meeting, outcome: TranscriptionOutcome, usage: SynthesisUsage
) -> dict[str, Any]:
    """The paid units of the exchange, in the shape the chat bubble reads.

    ``tokens_*``, ``model_name`` and ``cost_eur`` are the runner's standard keys
    (``cost_eur`` = everything this exchange cost); the ``stt_*`` and
    ``llm_cost_eur`` keys give the card its breakdown. An unknown price stays
    None rather than counting as zero.
    """
    llm_cost = meeting.synthesis_cost_eur
    priced = [c for c in (outcome.cost_eur, llm_cost) if c is not None]
    return {
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "tokens_cache": usage.tokens_cache,
        "model_name": usage.model_name,
        "llm_cost_eur": llm_cost,
        "stt_cost_eur": outcome.cost_eur,
        "stt_audio_duration_seconds": outcome.audio_duration_seconds,
        "stt_model": outcome.model,
        "cost_eur": round(sum(priced), 6) if priced else None,
    }


async def _auto_email(
    db: Any,
    *,
    meeting: Meeting,
    recipient: str,
    report: MeetingReport,
    language: str,
    gaps: int,
) -> None:
    """Email the minutes when the user opted in; a refused relay is logged, not raised."""
    from src.domains.meetings.delivery import MinutesDeliveryError, send_minutes_email

    try:
        await send_minutes_email(
            db,
            user_id=meeting.user_id,
            recipient=recipient,
            meeting=meeting,
            report=report,
            language=language,
            gaps=gaps,
        )
    except MinutesDeliveryError as exc:
        logger.warning("meeting_auto_email_skipped", meeting_id=str(meeting.id), code=exc.code)


async def _purge_unkept_audio(repo: MeetingRepository, meeting: Meeting) -> None:
    """Delete the audio right away when the user keeps none."""
    if meeting.keep_audio_until is not None or not meeting.audio_path:
        return
    await MeetingAudioStore(settings.meetings_storage_path).purge_meeting(
        meeting.user_id, meeting.id
    )
    await repo.mark_audio_purged(meeting.id, purged_at=datetime.now(UTC))


async def _after_ready(
    meeting_id: UUID,
    *,
    synthesis: SynthesisResult,
    outcome: TranscriptionOutcome,
    preference: MeetingPreference | None,
    language: str,
    gaps: int,
) -> None:
    """Notify, email, index and purge — each best effort, each logged.

    The notification goes out FIRST: the minutes are readable the moment the
    row is ``ready``, and embedding them can take a while on a long meeting.
    """
    from src.domains.meetings.indexing import index_minutes
    from src.domains.users.repository import UserRepository

    async with get_db_context() as db:
        repo = MeetingRepository(db)
        meeting = await repo.get_by_id(meeting_id)
        user = await UserRepository(db).get_by_id(meeting.user_id) if meeting else None
        if meeting is None or user is None:
            return
        await _notify_ready(
            db,
            meeting=meeting,
            user=user,
            synthesis=synthesis,
            outcome=outcome,
            language=language,
            gaps=gaps,
        )
        if preference is not None and preference.auto_email:
            await _auto_email(
                db,
                meeting=meeting,
                recipient=str(user.email),
                report=synthesis.report,
                language=language,
                gaps=gaps,
            )
        await _purge_unkept_audio(repo, meeting)

    if settings.rag_spaces_enabled:
        await index_minutes(meeting_id)


# ----------------------------------------------------------------------------
# The job
# ----------------------------------------------------------------------------


async def _fail(
    repo: MeetingRepository, job: _Job, *, code: str, message: str, transient: bool
) -> None:
    meeting_failures_total.labels(reason=code).inc()
    if transient:
        status = await repo.fail_or_retry(
            job.meeting_id,
            code=code,
            message=message[:1000],
            max_attempts=settings.meetings_job_max_attempts,
        )
    else:
        await repo.fail_permanently(job.meeting_id, code=code, message=message[:1000])
        status = MeetingStatus.FAILED
    if status is MeetingStatus.FAILED:
        meetings_total.labels(status="failed").inc()
    logger.warning(
        "meeting_processing_failed",
        meeting_id=str(job.meeting_id),
        code=code,
        transient=transient,
        status=status.value,
    )


async def _run(job: _Job, repo: MeetingRepository, db: Any, meeting: Meeting) -> None:
    """The claimed job, start to ``ready``. Raises for the caller to classify."""
    from src.domains.usage_limits.service import UsageLimitService
    from src.domains.users.repository import UserRepository

    user = await UserRepository(db).get_by_id(meeting.user_id)
    if user is None:
        await repo.fail_permanently(job.meeting_id, code="user_missing", message="owner deleted")
        return
    language = str(user.language or settings.default_language)
    preference = await MeetingPreferenceRepository(db).get_for_user(meeting.user_id)

    check = await UsageLimitService.check_user_allowed(meeting.user_id)
    if not check.allowed:
        await repo.release_unprocessed(
            job.meeting_id, code=ERROR_USAGE_LIMIT, message=check.blocked_reason or ""
        )
        return
    engine_preference = preference.stt_engine if preference else MeetingSttEnginePreference.AUTO
    engine: ResolvedEngine | None = resolve_engine(engine_preference)
    if engine is None:
        await repo.release_unprocessed(job.meeting_id, code=ERROR_NO_ENGINE, message="")
        return

    stopped_at = meeting.stopped_at or datetime.now(UTC)
    # One capture for the whole meeting: the template choice (ADR-259), the
    # condense passes and the synthesis add up to what the minutes cost.
    capture = TokenCaptureHandler()

    # 1. normalizing
    audio_path, duration, gaps = await _normalize(job, meeting)
    await job.heartbeat(repo)

    # 2. transcribing
    await job.enter_stage(repo, MeetingStage.TRANSCRIBING)

    async def _pulse() -> None:
        await job.heartbeat(repo)

    # The chain is walked at PROCESSING time: a provider whose key is refused
    # hands over to the next engine instead of dead-lettering the meeting.
    outcome = await transcribe_with_fallback(
        engine_preference,
        audio_path=job.store.absolute(audio_path),
        mime_type=normalized_mime_type(meeting.audio_format),
        duration_seconds=duration,
        language_hint=_language_hint(preference, meeting),
        user_id=meeting.user_id,
        heartbeat=_pulse,
    )
    meeting_stt_audio_seconds_total.labels(provider=outcome.provider.value).inc(
        outcome.audio_duration_seconds
    )

    # 3. synthesizing (enrichment first — both are hints for the same call)
    await job.enter_stage(repo, MeetingStage.SYNTHESIZING)
    calendar, location_label = await _enrich(db, meeting, stopped_at=stopped_at, language=language)
    decision = await decide_template(
        db,
        meeting=meeting,
        preference=preference,
        turns=outcome.turns,
        calendar_title=calendar.title if calendar else None,
        language=language,
        capture=capture,
    )
    synthesis = await _synthesize(
        meeting,
        outcome,
        template=decision.sections,
        language=language,
        stopped_at=stopped_at,
        location_label=location_label,
        calendar=calendar,
        gaps=gaps,
        capture=capture,
    )
    await job.heartbeat(repo)
    job.close_stage()

    completed = await repo.complete(
        job.meeting_id,
        worker_id=job.worker_id,
        values=_completion_values(
            meeting=meeting,
            audio_path=audio_path,
            duration=duration,
            outcome=outcome,
            synthesis=synthesis,
            decision=decision,
            calendar=calendar,
            location_label=location_label,
            keep_audio_until=_keep_audio_until(preference, datetime.now(UTC)),
            gaps=gaps,
        ),
    )
    if not completed:
        raise LeaseLostError(f"completion refused for meeting {job.meeting_id}")
    meetings_total.labels(status="ready").inc()
    meeting_recording_duration_seconds.observe(duration)
    logger.info(
        "meeting_processing_ready",
        meeting_id=str(job.meeting_id),
        provider=outcome.provider.value,
        duration_seconds=round(duration, 1),
        gaps=gaps,
        condensed=synthesis.condensed,
    )
    await _after_ready_guarded(
        job.meeting_id,
        synthesis=synthesis,
        outcome=outcome,
        preference=preference,
        language=language,
        gaps=gaps,
    )


async def _after_ready_guarded(meeting_id: UUID, **kwargs: Any) -> None:
    """Run the post-READY effects; nothing they raise may reach the job's classifier.

    The minutes ARE ready once ``complete`` returned: a notification or indexing
    failure is logged and counted, never turned into a failed meeting.
    """
    try:
        await _after_ready(meeting_id, **kwargs)
    except Exception:  # noqa: BLE001 — best-effort effects after the durable commit
        meeting_failures_total.labels(reason="after_ready").inc()
        logger.exception("meeting_after_ready_failed", meeting_id=str(meeting_id))


async def process_meeting(meeting_id: UUID) -> None:
    """Claim and process one stopped meeting; never raises."""
    job = _Job(meeting_id)
    async with get_db_context() as db:
        repo = MeetingRepository(db)
        claimed = await repo.claim_stopped(
            meeting_id,
            worker_id=job.worker_id,
            lease_ttl_s=settings.meetings_job_lease_ttl_seconds,
        )
        if not claimed:
            logger.debug("meeting_claim_lost", meeting_id=str(meeting_id))
            return
        meeting = await repo.get_by_id(meeting_id)
        if meeting is None:
            return
        logger.info(
            "meeting_processing_started",
            meeting_id=str(meeting_id),
            attempt=meeting.attempts,
            segments=meeting.segment_count,
        )
        try:
            await _run(job, repo, db, meeting)
        except LeaseLostError as exc:
            logger.warning("meeting_lease_lost", meeting_id=str(meeting_id), error=str(exc))
        except AudioStorageError as exc:
            await _fail(repo, job, code=ERROR_NORMALIZE, message=str(exc), transient=True)
        except TranscriptionError as exc:
            await _fail(repo, job, code=exc.code, message=exc.message, transient=exc.transient)
        except StructuredOutputError as exc:
            await _fail(repo, job, code=ERROR_SYNTHESIS, message=str(exc), transient=True)
        except Exception as exc:  # noqa: BLE001 — a PROCESSING row must never be left hanging
            logger.exception("meeting_processing_unexpected", meeting_id=str(meeting_id))
            await _fail(repo, job, code=ERROR_UNEXPECTED, message=str(exc), transient=True)
