"""Rewriting the minutes of a READY meeting from its stored transcript (ADR-258, ADR-259).

Two entry points share this job: « Rebuild » (the meeting's own template again)
and « Reformat » (another template, in place or as new minutes derived from the
same transcript — ``reformat.py``). The old minutes stay readable until the new
ones are published; the stage is the progress the page shows, and a failure
always clears it (a stage left at SYNTHESIZING answers ``regeneration_in_progress``
forever — the reaper is the safety net for a hard kill).
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import MEETINGS_PROACTIVE_TASK_TYPE
from src.domains.meetings.models import MeetingStage
from src.domains.meetings.processing import (
    ERROR_SYNTHESIS,
    ERROR_UNEXPECTED,
    synthesis_cost_eur,
)
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.synthesis import SynthesisContext, synthesize_minutes
from src.domains.meetings.template_resolution import template_for_regeneration
from src.domains.meetings.templates import sections_to_json
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.structured_output import StructuredOutputError
from src.infrastructure.observability.metrics_meetings import meeting_failures_total

logger = structlog.get_logger(__name__)


def launch_regenerate(meeting_id: UUID) -> None:
    """Rebuild the minutes of a READY meeting from its transcript, in the background."""
    safe_fire_and_forget(regenerate_minutes(meeting_id), name=f"meeting_regenerate_{meeting_id}")


async def regenerate_minutes(meeting_id: UUID) -> None:
    """Re-synthesize the minutes; the old ones stay until the new ones are published."""
    from src.domains.meetings.indexing import schedule_reindex
    from src.domains.meetings.service import MeetingService
    from src.domains.users.repository import UserRepository

    async with get_db_context() as db:
        repo = MeetingRepository(db)
        meeting = await repo.get_by_id(meeting_id)
        if meeting is None or meeting.stage is not MeetingStage.SYNTHESIZING:
            return
        if not meeting.transcript_encrypted:
            await repo.fail_regenerate(meeting_id, code="transcript_unavailable", message="")
            return
        user = await UserRepository(db).get_by_id(meeting.user_id)
        language = str(getattr(user, "language", None) or settings.default_language)
        decision = await template_for_regeneration(db, meeting=meeting, language=language)
        turns = MeetingService.decrypt_transcript(meeting.transcript_encrypted)
        context = SynthesisContext(
            language=language,
            timezone=meeting.client_timezone,
            started_at=meeting.started_at,
            stopped_at=meeting.stopped_at,
            duration_seconds=meeting.audio_duration_seconds,
            location_label=meeting.location_label,
            calendar_title=None,
            calendar_attendees=[],
            gaps=meeting.audio_gaps,
            diarized=meeting.stt_diarized,
        )
        try:
            synthesis = await synthesize_minutes(turns, decision.sections, context)
        except StructuredOutputError as exc:
            meeting_failures_total.labels(reason=ERROR_SYNTHESIS).inc()
            await repo.fail_regenerate(meeting_id, code=ERROR_SYNTHESIS, message=str(exc)[:1000])
            return
        except Exception as exc:  # noqa: BLE001 — a stage left at SYNTHESIZING blocks every retry
            logger.exception("meeting_regenerate_unexpected", meeting_id=str(meeting_id))
            meeting_failures_total.labels(reason=ERROR_UNEXPECTED).inc()
            await repo.fail_regenerate(meeting_id, code=ERROR_UNEXPECTED, message=str(exc)[:1000])
            return
        report = synthesis.report.model_dump(mode="json")
        usage = synthesis.usage
        # A rebuild is paid like the first pass: tracked for the platform, added
        # to the meeting's own total for the user.
        if usage.tokens_in or usage.tokens_out:
            from src.infrastructure.proactive.tracking import track_proactive_tokens

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
            )
        await repo.finish_regenerate(
            meeting_id,
            values={
                "template_snapshot": sections_to_json(decision.sections),
                "template_ref": str(decision.ref),
                "template_name": decision.name,
                "template_selection": decision.selection.value,
                "template_selection_reason": decision.reason,
                "synthesis_model": usage.model_name,
                "report_generated": report,
                "report_current": report,
                "report_edited_at": None,
            },
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache=usage.tokens_cache,
            cost_eur=synthesis_cost_eur(usage),
        )
        logger.info(
            "meeting_minutes_regenerated",
            meeting_id=str(meeting_id),
            template_ref=str(decision.ref),
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
        )
    schedule_reindex(meeting_id)


__all__ = ["launch_regenerate", "regenerate_minutes"]
