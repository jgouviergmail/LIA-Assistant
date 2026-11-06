"""How a card draws an event: created, changed, deleted, answered (ADR-369, lot 5).

Moved out of ``preview_renderer`` (at its size cap) with everything that only an event
reads: its times, and what the options say. One renderer per ``DraftType``, as there.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.calendar.event_options import NO_REMINDER, readable_options
from src.domains.agents.drafts.card_spec import PreviewLine
from src.domains.agents.drafts.dates import shown_end
from src.domains.agents.drafts.preview_rows import FormatDt as _FormatDt
from src.domains.agents.drafts.preview_rows import block as _block
from src.domains.agents.drafts.preview_rows import row as _row
from src.domains.agents.drafts.preview_rows import updated_datetime_row as _updated_datetime_row
from src.domains.agents.drafts.preview_rows import updated_row as _updated_row

#: What marks a row the change writes, after its value.
_CHANGED = " ✏️"


def render_event(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[PreviewLine]:
    """Render an event creation preview (summary, times, place, attendees)."""
    summary = content.get("summary", "")
    location = content.get("location", "")
    description = content.get("description", "")
    attendees = content.get("attendees", [])

    # An event with no times is a draft the model left incomplete; « Début: »
    # over nothing states less than saying nothing at all.
    lines: list[PreviewLine] = [_row(lbl, "event", summary)]
    lines += _event_time_rows(content, lbl, format_dt)
    if location:
        lines.append(_row(lbl, "location", location))
    if attendees:
        lines.append(_row(lbl, "attendees", ", ".join(attendees)))
    if content.get("add_conference"):
        lines.append(_row(lbl, "video_conference", lbl["video_conference_included"]))
    if recurrence_text := content.get("recurrence_text"):
        lines.append(_row(lbl, "repeat", recurrence_text))
    lines += _option_rows(content, lbl)
    if description:
        lines.append(_block(lbl, "body", description))
    return lines


def _option_rows(content: dict[str, Any], lbl: dict[str, str], mark: str = "") -> list[PreviewLine]:
    """What the event is asked to say beyond its time: only what is said."""
    options = readable_options(content)
    lines: list[PreviewLine] = []
    if "reminder_minutes" in options:
        text = _reminder_text(options["reminder_minutes"], lbl)
        lines.append(_row(lbl, "reminder", f"{text}{mark}"))
    if "busy" in options:
        text = lbl["shows_busy" if options["busy"] else "shows_free"]
        lines.append(_row(lbl, "availability", f"{text}{mark}"))
    if "private" in options:
        text = lbl["is_private" if options["private"] else "is_default"]
        lines.append(_row(lbl, "visibility", f"{text}{mark}"))
    return lines


def _reminder_text(minutes: int, lbl: dict[str, str]) -> str:
    """A reminder in words."""
    if minutes == NO_REMINDER:
        return lbl["reminder_none"]
    return lbl["reminder_before"].format(minutes=minutes) if minutes else lbl["reminder_at_start"]


def _event_time_rows(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[PreviewLine]:
    """A new event's start and end rows — its days, the LAST one shown, when all-day."""
    all_day = bool(content.get("all_day"))
    start_raw = content.get("start_datetime") or ""
    end_raw = shown_end(content.get("end_datetime") or "")
    rows: list[PreviewLine] = []
    start = format_dt(start_raw)
    if start:
        rows.append(_row(lbl, "start", f"{start} ({lbl['all_day']})" if all_day else start))
    end = format_dt(end_raw)
    if end and end_raw != start_raw:
        rows.append(_row(lbl, "end", end))
    return rows


def _updated_time_rows(
    content: dict[str, Any],
    current: dict[str, Any],
    lbl: dict[str, str],
    format_dt: _FormatDt,
) -> list[PreviewLine]:
    """An update's start and end rows: new values marked, an all-day end as its last day."""
    current_start = current.get("start", {}).get(
        "dateTime", current.get("start", {}).get("date", "")
    )
    current_end = current.get("end", {}).get("dateTime", current.get("end", {}).get("date", ""))
    new_end = content.get("end_datetime")
    rows = [
        _updated_datetime_row(
            lbl, "start", content.get("start_datetime"), current_start, format_dt
        ),
        _updated_datetime_row(
            lbl, "end", shown_end(new_end) if new_end else None, shown_end(current_end), format_dt
        ),
    ]
    return [row for row in rows if row]


def render_event_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[PreviewLine]:
    """Render an event update preview: resulting state, modified fields marked."""
    current = content.get("current_event", {})
    summary = content.get("summary") or current.get("summary", "?")
    lines: list[PreviewLine] = [_row(lbl, "event", summary)]
    lines += _scope_rows(content, lbl)

    lines += _updated_time_rows(content, current, lbl, format_dt)

    location_row = _updated_row(
        lbl, "location", content.get("location"), current.get("location", "")
    )
    if location_row:
        lines.append(location_row)

    new_attendees = content.get("attendees")
    if new_attendees:
        lines.append(_row(lbl, "attendees", f"{', '.join(new_attendees)} ✏️"))
    elif current.get("attendees"):
        current_attendees = [a.get("email", a.get("displayName", "")) for a in current["attendees"]]
        if current_attendees:
            lines.append(_row(lbl, "attendees", ", ".join(current_attendees)))
    lines += _option_rows(content, lbl, _CHANGED)
    if content.get("add_conference"):
        lines.append(_row(lbl, "video_conference", f"{lbl['video_conference_included']}{_CHANGED}"))
    return lines


def render_event_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[PreviewLine]:
    """Render an event delete preview (summary, start date)."""
    event = content.get("event", {})
    summary = event.get("summary", "?")
    start_raw = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    start = format_dt(start_raw) if start_raw else ""

    lines: list[PreviewLine] = [_row(lbl, "event", summary), *_scope_rows(content, lbl)]
    if start:
        lines.append(_row(lbl, "date", start))
    return lines


def _scope_rows(content: dict[str, Any], lbl: dict[str, str]) -> list[PreviewLine]:
    """A whole series, said before anyone confirms: it is every occurrence."""
    return [_row(lbl, "repeat", lbl["whole_series"])] if content.get("scope") == "series" else []


def render_event_answer(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[PreviewLine]:
    """Render an invitation's answer: the event, its date, the answer and who is told."""
    start_raw = content.get("start_datetime") or ""
    organizer = content.get("organizer")
    lines: list[PreviewLine] = [_row(lbl, "event", content.get("summary") or "?")]
    if start_raw:
        lines.append(_row(lbl, "date", format_dt(start_raw)))
    lines.append(_row(lbl, "answer", lbl.get(f"answer_{content.get('response')}", "?")))
    if organizer:
        lines.append(_row(lbl, "organizer", organizer))
    return lines


__all__ = ["render_event", "render_event_answer", "render_event_delete", "render_event_update"]
