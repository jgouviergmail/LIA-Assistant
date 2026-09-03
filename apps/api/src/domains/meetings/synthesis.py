"""Structured minutes from a transcript (ADR-258).

One structured-output call on the ``meeting_synthesis`` slot fills the user's
template. The model answers in a permissive shape (``SynthesizedMinutes``:
every payload optional per section) and :func:`repair_report` folds it into
the strict ``MeetingReport`` the API serves — sections the model skipped come
back empty, sections it invented are dropped, a payload given in the wrong
shape for the section's kind is converted rather than rejected. The template
is the contract; the model is not trusted to honour it byte for byte.

When the transcript cannot fit the slot's context window, it is condensed part
by part (``meeting_condense_prompt``) before the structured call — a
128k-window model still produces faithful minutes for a three-hour meeting.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import (
    MEETINGS_CHARS_PER_TOKEN_ESTIMATE,
    MEETINGS_CONDENSE_PART_CHARS,
    MEETINGS_LLM_TYPE,
    MEETINGS_SYNTHESIS_RESERVE_TOKENS,
)
from src.core.i18n_meetings import get_header_label
from src.core.llm_config_helper import get_effective_context_window, get_llm_config_for_agent
from src.domains.meetings.prompts import load_meeting_prompt
from src.domains.meetings.render import format_duration
from src.domains.meetings.schemas import (
    ActionItem,
    MeetingReport,
    Participant,
    ReportSection,
    SectionKind,
    TemplateSection,
    TopicItem,
    TranscriptTurn,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.llm.token_capture import TokenCaptureHandler

logger = structlog.get_logger(__name__)


# ----------------------------------------------------------------------------
# Model-facing shapes (permissive) — the strict ones live in schemas.py
# ----------------------------------------------------------------------------


class SynthesizedParticipant(BaseModel):
    """One participant as the model saw them."""

    label: str = Field(description="Speaker label from the transcript (S1, S2, …).")
    name: str | None = Field(
        default=None, description="Name only when the transcript establishes it."
    )
    role: str | None = Field(default=None, description="Role only when stated.")


class SynthesizedTopic(BaseModel):
    """One discussed topic."""

    title: str = Field(description="Topic title.")
    summary: str = Field(description="What was said about it.")


class SynthesizedAction(BaseModel):
    """One action item."""

    description: str = Field(description="What must be done.")
    owner: str | None = Field(default=None, description="Speaker label or established name.")
    due_date: str | None = Field(default=None, description="Absolute date YYYY-MM-DD, or null.")


class SynthesizedSection(BaseModel):
    """One template section, filled in the shape its kind asks for."""

    key: str = Field(description="The template section key, echoed back.")
    paragraph: str | None = Field(default=None, description="For 'paragraph' sections.")
    bullets: list[str] = Field(default_factory=list, description="For 'bullets' sections.")
    topics: list[SynthesizedTopic] = Field(default_factory=list, description="For 'topics'.")
    action_items: list[SynthesizedAction] = Field(
        default_factory=list, description="For 'action_items'."
    )


class SynthesizedMinutes(BaseModel):
    """The model's answer: header fields + one entry per template section."""

    title: str = Field(description="Short, specific meeting title.")
    participants: list[SynthesizedParticipant] = Field(default_factory=list)
    sections: list[SynthesizedSection] = Field(default_factory=list)


class CondensedNotes(BaseModel):
    """The condense pass answer for one transcript part."""

    notes: str = Field(description="Detailed working notes for this part of the transcript.")


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class SynthesisContext:
    """Facts about the recording the model must know (never PII beyond the meeting's own)."""

    language: str
    timezone: str
    started_at: datetime
    stopped_at: datetime | None
    duration_seconds: float | None
    location_label: str | None
    calendar_title: str | None
    calendar_attendees: Sequence[str]
    gaps: int
    diarized: bool


@dataclass(frozen=True)
class SynthesisUsage:
    """Token usage of the whole synthesis (condense passes included)."""

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    model_name: str


@dataclass(frozen=True)
class SynthesisResult:
    """Minutes plus what they cost."""

    report: MeetingReport
    usage: SynthesisUsage
    condensed: bool


# ----------------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------------


def _fmt_time(moment: datetime, timezone: str) -> str:
    return moment.astimezone(ZoneInfo(timezone)).strftime("%H:%M")


def render_transcript(turns: Sequence[TranscriptTurn]) -> str:
    """Speaker-labelled, timestamped lines — the shape both prompts describe."""
    lines: list[str] = []
    for turn in turns:
        minutes, seconds = divmod(int(turn.start), 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {turn.speaker}: {turn.text}")
    return "\n".join(lines)


def render_context(context: SynthesisContext) -> str:
    """The CONTEXT block of the synthesis prompt."""
    local_start = context.started_at.astimezone(ZoneInfo(context.timezone))
    lines = [
        f"LANGUAGE: {context.language}",
        f"DATE: {local_start.strftime('%Y-%m-%d')} ({local_start.strftime('%A')})",
        f"TIMEZONE: {context.timezone}",
        f"START: {_fmt_time(context.started_at, context.timezone)}",
        f"END: {_fmt_time(context.stopped_at, context.timezone) if context.stopped_at else 'unknown'}",
        f"DURATION: {format_duration(context.duration_seconds) or 'unknown'}",
        f"LOCATION: {context.location_label or 'unknown'}",
        f"CALENDAR EVENT: {context.calendar_title or 'none found'}",
        f"CALENDAR ATTENDEES (hints): {', '.join(context.calendar_attendees) or 'none'}",
        f"GAPS: {context.gaps}",
        f"SPEAKERS SEPARATED: {'yes' if context.diarized else 'no'}",
    ]
    return "\n".join(lines)


def render_template(sections: Sequence[TemplateSection]) -> str:
    """The TEMPLATE block: one line per section, every field the model needs."""
    return "\n".join(
        f"- key={section.key} | kind={section.kind.value} | label={section.label}\n"
        f"  instruction: {section.instruction}"
        for section in sections
    )


def estimate_tokens(text: str) -> int:
    """Conservative token estimate (see ``MEETINGS_CHARS_PER_TOKEN_ESTIMATE``)."""
    return max(1, len(text) // MEETINGS_CHARS_PER_TOKEN_ESTIMATE)


def transcript_budget_tokens(model: str) -> int:
    """Tokens the transcript may occupy in ``model``'s window."""
    return max(0, get_effective_context_window(model) - MEETINGS_SYNTHESIS_RESERVE_TOKENS)


def split_transcript(text: str, *, part_chars: int | None = None) -> list[str]:
    """Cut a rendered transcript into parts at line boundaries.

    ``part_chars`` defaults to the constant AT CALL TIME (a default argument
    would freeze the module constant at import).
    """
    part_chars = part_chars or MEETINGS_CONDENSE_PART_CHARS
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        if current and size + len(line) + 1 > part_chars:
            parts.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append("\n".join(current))
    return parts


def _bullets_from_text(text: str | None) -> list[str]:
    return [line.strip(" -•*\t") for line in (text or "").splitlines() if line.strip(" -•*\t")]


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _optional(value: str | None, limit: int) -> str | None:
    cleaned = (value or "").strip()
    return _clip(cleaned, limit) if cleaned else None


def _clean_list(items: Sequence[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


def _fallback_lines(raw: SynthesizedSection) -> list[str]:
    """Text lines from whatever the model filled, when the kind's own payload is empty."""
    lines = _clean_list(raw.bullets) or _bullets_from_text(raw.paragraph)
    if not lines and raw.action_items:
        lines = _clean_list([action.description for action in raw.action_items])
    if not lines and raw.topics:
        lines = [
            f"{topic.title.strip()}: {topic.summary.strip()}"
            for topic in raw.topics
            if topic.title.strip()
        ]
    return lines


def _repair_paragraph(section: ReportSection, raw: SynthesizedSection) -> None:
    text = (raw.paragraph or "").strip() or " ".join(_fallback_lines(raw))
    section.paragraph = _clip(text, 8000) or None


def _repair_bullets(section: ReportSection, raw: SynthesizedSection) -> None:
    section.bullets = [_clip(item, 1000) for item in _fallback_lines(raw)]


def _repair_topics(section: ReportSection, raw: SynthesizedSection) -> None:
    topics = [
        TopicItem(title=_clip(t.title.strip(), 200), summary=_clip(t.summary.strip(), 4000))
        for t in raw.topics
        if t.title.strip() and t.summary.strip()
    ]
    section.topics = topics or [
        TopicItem(title=_clip(line, 200), summary=_clip(line, 4000))
        for line in _fallback_lines(raw)
    ]


def _repair_actions(section: ReportSection, raw: SynthesizedSection) -> None:
    actions = [
        ActionItem(
            description=_clip(a.description.strip(), 1000),
            owner=_optional(a.owner, 120),
            due_date=_optional(a.due_date, 40),
        )
        for a in raw.action_items
        if a.description.strip()
    ]
    section.action_items = actions or [
        ActionItem(description=_clip(line, 1000)) for line in _fallback_lines(raw)
    ]


_REPAIRERS: dict[SectionKind, Callable[[ReportSection, SynthesizedSection], None]] = {
    SectionKind.PARAGRAPH: _repair_paragraph,
    SectionKind.BULLETS: _repair_bullets,
    SectionKind.TOPICS: _repair_topics,
    SectionKind.ACTION_ITEMS: _repair_actions,
}
# Boot-time completeness (ADR-085): a new kind without a repairer refuses to import.
assert set(_REPAIRERS) == set(SectionKind), "_REPAIRERS must cover every SectionKind"


def _repair_section(template: TemplateSection, raw: SynthesizedSection | None) -> ReportSection:
    """One strict section from what the model gave for ``template``."""
    section = ReportSection(key=template.key, label=template.label, kind=template.kind)
    if raw is not None:
        _REPAIRERS[template.kind](section, raw)
    return section


def _repair_participants(
    raw_participants: Sequence[SynthesizedParticipant], known: Sequence[str]
) -> list[Participant]:
    """Participants restricted to labels that spoke; silent labels added unnamed."""
    participants: list[Participant] = []
    seen: set[str] = set()
    for raw in raw_participants:
        label = raw.label.strip()
        if not label or label in seen or (known and label not in known):
            continue
        seen.add(label)
        participants.append(
            Participant(
                label=_clip(label, 40), name=_optional(raw.name, 120), role=_optional(raw.role, 120)
            )
        )
    participants.extend(Participant(label=label) for label in known if label not in seen)
    order = list(known)
    participants.sort(key=lambda p: order.index(p.label) if p.label in order else len(order))
    return participants


def repair_report(
    minutes: SynthesizedMinutes,
    template: Sequence[TemplateSection],
    *,
    speaker_labels: Sequence[str],
    language: str,
) -> MeetingReport:
    """Fold the model's answer into the strict report, template first.

    Args:
        minutes: The model's answer.
        template: The sections the user asked for, in order.
        speaker_labels: Labels the transcript actually contains — a participant
            the model invented for a label that never spoke is dropped, and a
            label that spoke but the model forgot is added unnamed.
        language: Minutes language (the localized fallback title).

    Returns:
        A report with exactly the template's sections, in the template's order.
    """
    by_key = {section.key: section for section in minutes.sections}
    sections = [_repair_section(section, by_key.get(section.key)) for section in template]
    title = minutes.title.strip() or get_header_label("minutes", language)
    return MeetingReport(
        title=_clip(title, 200),
        participants=_repair_participants(minutes.participants, list(speaker_labels)),
        sections=sections,
    )


# ----------------------------------------------------------------------------
# LLM calls
# ----------------------------------------------------------------------------


def _messages(system: str, human: str) -> list[BaseMessage]:
    return [SystemMessage(content=system), HumanMessage(content=human)]


async def _condense(parts: Sequence[str], *, provider: str, capture: TokenCaptureHandler) -> str:
    """Condense every transcript part into notes, in order."""
    system = load_meeting_prompt("meeting_condense_prompt")
    llm = get_llm(MEETINGS_LLM_TYPE)
    notes: list[str] = []
    for index, part in enumerate(parts, start=1):
        human = f"TRANSCRIPT PART {index}/{len(parts)}:\n{part}"
        answer = await get_structured_output_with_retry(
            llm,
            _messages(system, human),
            CondensedNotes,
            provider=provider,
            node_name=f"{MEETINGS_LLM_TYPE}_condense",
            config=RunnableConfig(callbacks=[capture]),
        )
        notes.append(f"PART {index}/{len(parts)}\n{answer.notes.strip()}")
    return "\n\n".join(notes)


async def synthesize_minutes(
    turns: Sequence[TranscriptTurn],
    template: Sequence[TemplateSection],
    context: SynthesisContext,
) -> SynthesisResult:
    """Produce the minutes for ``turns`` following ``template``.

    Args:
        turns: The transcript.
        template: The user's sections (snapshotted by the caller).
        context: Facts about the recording.

    Returns:
        The strict report, the token usage and whether a condense pass ran.

    Raises:
        StructuredOutputError: When the model never produced a valid answer.
    """
    config = get_llm_config_for_agent(settings, MEETINGS_LLM_TYPE)
    provider, model = str(config.provider), str(config.model)
    capture = TokenCaptureHandler()

    transcript = render_transcript(turns)
    speaker_labels: list[str] = []
    for turn in turns:
        if turn.speaker not in speaker_labels:
            speaker_labels.append(turn.speaker)

    condensed = False
    if estimate_tokens(transcript) > transcript_budget_tokens(model):
        parts = split_transcript(transcript)
        logger.info(
            "meeting_synthesis_condensing",
            model=model,
            parts=len(parts),
            transcript_chars=len(transcript),
        )
        transcript = await _condense(parts, provider=provider, capture=capture)
        condensed = True

    human = (
        f"CONTEXT:\n{render_context(context)}\n\n"
        f"TEMPLATE:\n{render_template(template)}\n\n"
        f"{'CONDENSED NOTES (from the transcript)' if condensed else 'TRANSCRIPT'}:\n{transcript}"
    )
    minutes = await get_structured_output_with_retry(
        get_llm(MEETINGS_LLM_TYPE),
        _messages(load_meeting_prompt("meeting_synthesis_prompt"), human),
        SynthesizedMinutes,
        provider=provider,
        node_name=MEETINGS_LLM_TYPE,
        config=RunnableConfig(callbacks=[capture]),
    )
    report = repair_report(
        minutes, template, speaker_labels=speaker_labels, language=context.language
    )
    usage = SynthesisUsage(
        tokens_in=capture.tokens_in,
        tokens_out=capture.tokens_out,
        tokens_cache=capture.tokens_cache,
        model_name=model,
    )
    logger.info(
        "meeting_synthesis_done",
        model=model,
        sections=len(report.sections),
        participants=len(report.participants),
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        condensed=condensed,
    )
    return SynthesisResult(report=report, usage=usage, condensed=condensed)
