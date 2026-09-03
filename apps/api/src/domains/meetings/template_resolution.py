"""Which template writes a meeting's minutes (ADR-259) — one precedence, one place.

1. the template the user chose for THIS meeting (start body or banner select);
2. else the user's default template (preference);
3. else, when the instance allows it, one small structured call picks the best
   candidate from a BOUNDED transcript excerpt; a hesitant, wrong or unavailable
   model falls back to the built-in default — the meeting is never failed by
   its template choice.

Regeneration reads the meeting's OWN template (its current content, so an
improved user template applies) and falls back to the snapshot the meeting
kept when that template no longer exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY,
    MEETINGS_LLM_TYPE,
    MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS,
)
from src.core.exceptions import BaseAPIException
from src.core.i18n_meeting_templates import get_template_name
from src.core.i18n_meetings import get_selection_fallback_reason
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.meetings.models import Meeting, MeetingPreference
from src.domains.meetings.prompts import build_messages, load_meeting_prompt
from src.domains.meetings.schemas import TemplateSection, TemplateSelection, TranscriptTurn
from src.domains.meetings.synthesis import render_transcript
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.template_service import MeetingTemplateService, ResolvedTemplate
from src.domains.meetings.templates import parse_sections
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    get_structured_output_with_retry,
)
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.observability.metrics_meetings import meeting_template_selection_total

logger = structlog.get_logger(__name__)

#: Slices sampled after the head so the excerpt reaches the end of the exchange.
_EXCERPT_SLICES = 4
_EXCERPT_SEPARATOR = "\n[…]\n"
#: The reason column is 300 chars wide (models.py).
_REASON_MAX = 300


class TemplateChoice(BaseModel):
    """The model's answer to « which template fits this exchange? »."""

    template_ref: str = Field(description="One ref copied from CANDIDATES.")
    confidence: float = Field(ge=0, le=1, description="0 to 1.")
    reason: str = Field(description="One short sentence, in the user's language.")


@dataclass(frozen=True)
class TemplateDecision:
    """What the pipeline fills, and how that was decided."""

    sections: list[TemplateSection]
    ref: TemplateRef
    name: str
    selection: TemplateSelection
    reason: str | None


# ----------------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------------


def transcript_excerpt(text: str, max_chars: int) -> str:
    """The head of ``text`` plus evenly spaced slices of the rest, within ``max_chars``.

    The choice needs the SUBJECT of the exchange, not every sentence: 40 % of
    the budget shows how it starts, the rest samples how it goes on and ends.
    """
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(_EXCERPT_SEPARATOR) * _EXCERPT_SLICES
    head_len = budget * 2 // 5
    slice_len = (budget - head_len) // _EXCERPT_SLICES
    parts = [text[:head_len]]
    rest_start = head_len
    step = (len(text) - head_len) // _EXCERPT_SLICES
    for index in range(_EXCERPT_SLICES):
        # The END of each window, so the last slice touches the end of the exchange.
        start = rest_start + index * step + max(0, step - slice_len)
        parts.append(text[start : start + slice_len])
    return _EXCERPT_SEPARATOR.join(parts)[:max_chars]


def render_candidates(candidates: Sequence[ResolvedTemplate]) -> str:
    """The CANDIDATES block: ``- ref | category | name: description`` per line."""
    lines = []
    for candidate in candidates:
        line = f"- {candidate.ref} | {candidate.category.value} | {candidate.name}"
        if candidate.description:
            line += f": {candidate.description}"
        lines.append(line)
    return "\n".join(lines)


def _decision(
    resolved: ResolvedTemplate,
    selection: TemplateSelection,
    reason: str | None,
    *,
    outcome: str,
) -> TemplateDecision:
    meeting_template_selection_total.labels(outcome=outcome).inc()
    return TemplateDecision(
        sections=resolved.sections,
        ref=resolved.ref,
        name=resolved.name,
        selection=selection,
        reason=reason[:_REASON_MAX] if reason else None,
    )


async def _try_resolve(
    service: MeetingTemplateService, user_id: object, ref: str, language: str
) -> ResolvedTemplate | None:
    """A reference, or ``None`` when it no longer resolves (deleted row, unknown key)."""
    try:
        return await service.resolve(user_id, ref, language)  # type: ignore[arg-type]
    except BaseAPIException:
        logger.warning("meeting_template_ref_dangling", ref=ref)
        return None


# ----------------------------------------------------------------------------
# Decisions
# ----------------------------------------------------------------------------


async def decide_template(
    db: AsyncSession,
    *,
    meeting: Meeting,
    preference: MeetingPreference | None,
    turns: Sequence[TranscriptTurn],
    calendar_title: str | None,
    language: str,
    capture: TokenCaptureHandler,
) -> TemplateDecision:
    """The template for a meeting being processed for the first time.

    Args:
        db: Session for the library reads.
        meeting: The meeting (its own ``template_ref`` wins).
        preference: The user's preferences (``default_template_ref`` comes next).
        turns: The transcript (an excerpt of it reaches the model).
        calendar_title: The overlapping calendar event, a hint for the model.
        language: The user's language (labels and the model's reason).
        capture: The synthesis token capture — the selection's tokens join it.

    Returns:
        The sections to fill and how they were chosen. Never raises for a
        model failure: the built-in default applies with the reason recorded.
    """
    service = MeetingTemplateService(db)
    if meeting.template_ref:
        resolved = await _try_resolve(service, meeting.user_id, meeting.template_ref, language)
        if resolved is not None:
            return _decision(resolved, TemplateSelection.USER, None, outcome="user")
    preferred = preference.default_template_ref if preference is not None else None
    if preferred:
        resolved = await _try_resolve(service, meeting.user_id, preferred, language)
        if resolved is not None:
            return _decision(resolved, TemplateSelection.PREFERENCE, None, outcome="preference")
    default = await service.resolve(
        meeting.user_id, str(TemplateRef.builtin(MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY)), language
    )
    if not settings.meetings_template_auto_select_enabled:
        return _decision(default, TemplateSelection.PREFERENCE, None, outcome="preference")
    return await _select_automatically(
        service,
        meeting=meeting,
        default=default,
        turns=turns,
        calendar_title=calendar_title,
        language=language,
        capture=capture,
    )


async def _select_automatically(
    service: MeetingTemplateService,
    *,
    meeting: Meeting,
    default: ResolvedTemplate,
    turns: Sequence[TranscriptTurn],
    calendar_title: str | None,
    language: str,
    capture: TokenCaptureHandler,
) -> TemplateDecision:
    candidates = await service.candidates(meeting.user_id, language)
    by_ref = {str(candidate.ref): candidate for candidate in candidates}
    excerpt = transcript_excerpt(render_transcript(turns), MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS)
    human = (
        f"LANGUAGE: {language}\n"
        f"CALENDAR EVENT: {calendar_title or 'none'}\n\n"
        f"CANDIDATES:\n{render_candidates(candidates)}\n\n"
        f"EXCERPT:\n{excerpt}"
    )
    config = get_llm_config_for_agent(settings, MEETINGS_LLM_TYPE)
    try:
        choice = await get_structured_output_with_retry(
            get_llm(MEETINGS_LLM_TYPE),
            build_messages(load_meeting_prompt("meeting_template_selection_prompt"), human),
            TemplateChoice,
            provider=str(config.provider),
            node_name=f"{MEETINGS_LLM_TYPE}_select",
            config=RunnableConfig(callbacks=[capture]),
        )
    except StructuredOutputError as exc:
        logger.warning("meeting_template_selection_unavailable", error=str(exc)[:200])
        reason = get_selection_fallback_reason("unavailable", language)
        return _decision(default, TemplateSelection.AUTO, reason, outcome="fallback")

    chosen = by_ref.get(choice.template_ref)
    minimum = settings.meetings_template_auto_min_confidence
    if chosen is None:
        logger.warning("meeting_template_selection_unknown", ref=choice.template_ref[:80])
        reason = get_selection_fallback_reason("unknown_choice", language)
        return _decision(default, TemplateSelection.AUTO, reason, outcome="fallback")
    if choice.confidence < minimum:
        logger.info(
            "meeting_template_selection_hesitant",
            ref=choice.template_ref,
            confidence=choice.confidence,
            minimum=minimum,
        )
        reason = get_selection_fallback_reason(
            "low_confidence", language, confidence=f"{choice.confidence:g}"
        )
        return _decision(default, TemplateSelection.AUTO, reason, outcome="fallback")
    logger.info(
        "meeting_template_selected",
        meeting_id=str(meeting.id),
        ref=choice.template_ref,
        confidence=choice.confidence,
    )
    return _decision(chosen, TemplateSelection.AUTO, choice.reason.strip(), outcome="auto")


async def template_for_regeneration(
    db: AsyncSession, *, meeting: Meeting, language: str
) -> TemplateDecision:
    """The meeting's own template — current content when it exists, its snapshot otherwise."""
    service = MeetingTemplateService(db)
    selection = (
        TemplateSelection(meeting.template_selection)
        if meeting.template_selection
        else TemplateSelection.PREFERENCE
    )
    reason = meeting.template_selection_reason
    if meeting.template_ref:
        resolved = await _try_resolve(service, meeting.user_id, meeting.template_ref, language)
        if resolved is not None:
            return TemplateDecision(
                sections=resolved.sections,
                ref=resolved.ref,
                name=resolved.name,
                selection=selection,
                reason=reason,
            )
    if meeting.template_snapshot:
        ref = (
            TemplateRef.parse(meeting.template_ref)
            if meeting.template_ref
            else TemplateRef.builtin(MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY)
        )
        name = meeting.template_name or get_template_name(
            MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY, language
        )
        return TemplateDecision(
            sections=parse_sections(meeting.template_snapshot),
            ref=ref,
            name=name,
            selection=selection,
            reason=reason,
        )
    default = await service.resolve(
        meeting.user_id, str(TemplateRef.builtin(MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY)), language
    )
    return TemplateDecision(
        sections=default.sections,
        ref=default.ref,
        name=default.name,
        selection=selection,
        reason=reason,
    )


__all__ = [
    "TemplateChoice",
    "TemplateDecision",
    "decide_template",
    "render_candidates",
    "template_for_regeneration",
    "transcript_excerpt",
]
