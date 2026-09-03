"""ONE serializer for the minutes: Markdown, sectioned document (PDF), HTML (ADR-258).

The three outputs read the same ``MeetingReport`` and the same
:class:`MinutesHeader`, so the knowledge-space document, the PDF and the email
can never disagree on content. The header (date, time, duration, location,
participants) is fixed and localized through ``core.i18n_meetings``; the body is
the template's sections in the template's order, rendered by kind.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.i18n_meetings import get_header_label
from src.core.time_utils import format_datetime_for_display
from src.domains.document_generation.sanitize import sanitize_filename_stem
from src.domains.document_generation.schemas import SectionBlock, SectionedContent
from src.domains.meetings.models import Meeting
from src.domains.meetings.schemas import (
    ActionItem,
    MeetingReport,
    Participant,
    ReportSection,
    SectionKind,
    TranscriptLine,
)

#: Language-neutral separator between an action's fields.
_FIELD_SEPARATOR = " · "


@dataclass(frozen=True)
class MinutesHeader:
    """The fixed, localized head of the minutes."""

    minutes_label: str
    date_label: str
    date: str
    time_label: str
    time_range: str | None
    duration_label: str
    duration: str | None
    location_label: str
    location: str | None
    participants_label: str
    participants: list[str] = field(default_factory=list)
    generated_by: str = ""
    notices: list[str] = field(default_factory=list)


def format_duration(seconds: float | None) -> str | None:
    """``H:MM:SS`` — readable in every supported language."""
    if seconds is None or seconds <= 0:
        return None
    total = int(round(seconds))
    return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _local_time(moment: datetime, timezone: str) -> str:
    return moment.astimezone(ZoneInfo(timezone)).strftime("%H:%M")


def participant_display(participant: Participant) -> str:
    """``Name (role)`` when known, else the speaker label."""
    base = participant.name or participant.label
    return f"{base} ({participant.role})" if participant.role else base


def build_header(
    meeting: Meeting, report: MeetingReport, *, language: str, gaps: int = 0
) -> MinutesHeader:
    """Header facts from the meeting row and the report, localized."""
    timezone = meeting.client_timezone
    time_range = None
    if meeting.stopped_at is not None:
        time_range = (
            f"{_local_time(meeting.started_at, timezone)} – "
            f"{_local_time(meeting.stopped_at, timezone)}"
        )
    notices: list[str] = []
    if gaps > 0:
        notices.append(get_header_label("gap_notice", language))
    if report.participants and all(p.name is None for p in report.participants):
        notices.append(get_header_label("no_speaker_names", language))
    return MinutesHeader(
        minutes_label=get_header_label("minutes", language),
        date_label=get_header_label("date", language),
        date=format_datetime_for_display(
            meeting.started_at, timezone, language, include_time=False
        ),
        time_label=get_header_label("time", language),
        time_range=time_range,
        duration_label=get_header_label("duration", language),
        duration=format_duration(meeting.audio_duration_seconds),
        location_label=get_header_label("location", language),
        location=meeting.location_label,
        participants_label=get_header_label("participants", language),
        participants=[participant_display(p) for p in report.participants],
        generated_by=get_header_label("generated_by", language),
        notices=notices,
    )


def _header_rows(header: MinutesHeader) -> list[tuple[str, str]]:
    rows = [(header.date_label, header.date)]
    if header.time_range:
        rows.append((header.time_label, header.time_range))
    if header.duration:
        rows.append((header.duration_label, header.duration))
    if header.location:
        rows.append((header.location_label, header.location))
    if header.participants:
        rows.append((header.participants_label, ", ".join(header.participants)))
    return rows


def action_display(action: ActionItem) -> str:
    """``description · owner · due`` with only the known fields."""
    parts = [action.description]
    if action.owner:
        parts.append(action.owner)
    if action.due_date:
        parts.append(action.due_date)
    return _FIELD_SEPARATOR.join(parts)


def _elapsed(seconds: float) -> str:
    """``m:ss`` / ``h:mm:ss`` — the timestamp of a transcript line."""
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    return f"{total // 60}:{total % 60:02d}"


def transcript_line_label(line: TranscriptLine) -> str:
    """``S1 [1:05]`` — who spoke and when, before the rewritten text."""
    return f"{line.speaker} [{_elapsed(line.start)}]"


def minutes_filename_stem(meeting: Meeting, report: MeetingReport) -> str:
    """``YYYY-MM-DD <title>`` made safe for a filename."""
    local_date = meeting.started_at.astimezone(ZoneInfo(meeting.client_timezone))
    return sanitize_filename_stem(f"{local_date:%Y-%m-%d} {report.title}", fallback="meeting")


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------


def _md_section(section: ReportSection) -> list[str]:
    lines = [f"## {section.label}", ""]
    if section.is_empty():
        return lines
    match section.kind:
        case SectionKind.PARAGRAPH:
            lines.append(section.paragraph or "")
        case SectionKind.BULLETS:
            lines.extend(f"- {item}" for item in section.bullets if item.strip())
        case SectionKind.TOPICS:
            for topic in section.topics:
                lines.extend([f"### {topic.title}", "", topic.summary, ""])
        case SectionKind.ACTION_ITEMS:
            lines.extend(f"- {action_display(action)}" for action in section.action_items)
        case SectionKind.TRANSCRIPT:
            lines.extend(
                f"**{transcript_line_label(line)}** {line.text}" for line in section.transcript
            )
    lines.append("")
    return lines


def render_markdown(report: MeetingReport, header: MinutesHeader) -> str:
    """Markdown — what the knowledge space indexes."""
    lines = [f"# {report.title}", "", f"*{header.minutes_label}*", ""]
    lines.extend(f"- **{label}** : {value}" for label, value in _header_rows(header))
    lines.append("")
    for notice in header.notices:
        lines.extend([f"> {notice}", ""])
    for section in report.sections:
        lines.extend(_md_section(section))
    lines.extend(["---", "", f"_{header.generated_by}_", ""])
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Sectioned document (PDF / DOCX through document_generation)
# ----------------------------------------------------------------------------


def _blocks_for_section(section: ReportSection) -> list[SectionBlock]:
    blocks = [SectionBlock(kind="heading", level=2, text=section.label)]
    if section.is_empty():
        return blocks
    match section.kind:
        case SectionKind.PARAGRAPH:
            blocks.append(SectionBlock(kind="paragraph", text=section.paragraph or ""))
        case SectionKind.BULLETS:
            blocks.append(SectionBlock(kind="bullets", items=[b for b in section.bullets if b]))
        case SectionKind.TOPICS:
            for topic in section.topics:
                blocks.append(SectionBlock(kind="heading", level=3, text=topic.title))
                blocks.append(SectionBlock(kind="paragraph", text=topic.summary))
        case SectionKind.ACTION_ITEMS:
            blocks.append(
                SectionBlock(
                    kind="bullets", items=[action_display(a) for a in section.action_items]
                )
            )
        case SectionKind.TRANSCRIPT:
            blocks.extend(
                SectionBlock(kind="paragraph", text=f"{transcript_line_label(line)} — {line.text}")
                for line in section.transcript
            )
    return blocks


def render_sectioned(
    report: MeetingReport, header: MinutesHeader, *, filename_stem: str
) -> SectionedContent:
    """The document_generation content model — one ``render_document`` away from a PDF."""
    blocks: list[SectionBlock] = [SectionBlock(kind="paragraph", text=header.minutes_label)]
    blocks.append(
        SectionBlock(
            kind="bullets", items=[f"{label} : {value}" for label, value in _header_rows(header)]
        )
    )
    blocks.extend(SectionBlock(kind="paragraph", text=notice) for notice in header.notices)
    for section in report.sections:
        blocks.extend(_blocks_for_section(section))
    blocks.append(SectionBlock(kind="paragraph", text=header.generated_by))
    return SectionedContent(filename_stem=filename_stem, title=report.title, blocks=blocks)


# ----------------------------------------------------------------------------
# HTML (email body)
# ----------------------------------------------------------------------------


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _html_section(section: ReportSection) -> str:
    parts = [f"<h2>{_e(section.label)}</h2>"]
    if section.is_empty():
        return "".join(parts)
    match section.kind:
        case SectionKind.PARAGRAPH:
            parts.append(f"<p>{_e(section.paragraph or '')}</p>")
        case SectionKind.BULLETS:
            parts.append(
                "<ul>" + "".join(f"<li>{_e(b)}</li>" for b in section.bullets if b) + "</ul>"
            )
        case SectionKind.TOPICS:
            for topic in section.topics:
                parts.append(f"<h3>{_e(topic.title)}</h3><p>{_e(topic.summary)}</p>")
        case SectionKind.ACTION_ITEMS:
            parts.append(
                "<ul>"
                + "".join(f"<li>{_e(action_display(a))}</li>" for a in section.action_items)
                + "</ul>"
            )
        case SectionKind.TRANSCRIPT:
            parts.extend(
                f"<p><strong>{_e(transcript_line_label(line))}</strong> {_e(line.text)}</p>"
                for line in section.transcript
            )
    return "".join(parts)


def render_html(report: MeetingReport, header: MinutesHeader) -> str:
    """Self-contained HTML body for the email (inline styles, everything escaped)."""
    rows = "".join(
        f"<tr><th align='left' style='padding:2px 12px 2px 0;color:#555'>{_e(label)}</th>"
        f"<td style='padding:2px 0'>{_e(value)}</td></tr>"
        for label, value in _header_rows(header)
    )
    notices = "".join(
        f"<p style='color:#8a6d3b;background:#fcf8e3;padding:8px;border-radius:4px'>{_e(n)}</p>"
        for n in header.notices
    )
    body = "".join(_html_section(section) for section in report.sections)
    return (
        "<div style='font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "line-height:1.5;color:#222;max-width:720px'>"
        f"<h1 style='font-size:1.4em'>{_e(report.title)}</h1>"
        f"<p style='color:#555'>{_e(header.minutes_label)}</p>"
        f"<table style='border-collapse:collapse;margin-bottom:12px'>{rows}</table>"
        f"{notices}{body}"
        f"<hr style='border:0;border-top:1px solid #ddd;margin-top:24px'>"
        f"<p style='color:#888;font-size:0.9em'>{_e(header.generated_by)}</p>"
        "</div>"
    )


def render_all(
    meeting: Meeting, report: MeetingReport, *, language: str, gaps: int = 0
) -> tuple[MinutesHeader, str]:
    """Header plus Markdown in one call (the processing job's need)."""
    header = build_header(meeting, report, language=language, gaps=gaps)
    return header, render_markdown(report, header)


__all__ = [
    "MinutesHeader",
    "action_display",
    "build_header",
    "format_duration",
    "minutes_filename_stem",
    "participant_display",
    "render_all",
    "render_html",
    "render_markdown",
    "render_sectioned",
    "transcript_line_label",
]
