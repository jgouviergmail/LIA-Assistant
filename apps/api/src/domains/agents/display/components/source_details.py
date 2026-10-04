"""Native provider facts supplement the stable tool aliases without new requests."""

from collections.abc import Mapping

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.core.time_utils import parse_provider_datetime
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    render_chip,
    render_d_item,
)
from src.domains.agents.display.components.card_content import render_availability_rows
from src.domains.agents.display.components.source_recurrence import render_source_recurrence
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, scalar_text

_TASK_STATES: dict[str, CardLabel] = {
    "inProgress": "in_progress",
    "waitingOnOthers": "waiting_others",
    "deferred": "deferred",
}
_EVENT_STATES: dict[str, CardLabel] = {
    "free": "available",
    "busy": "busy",
    "tentative": "tentative",
    "oof": "away",
    "workingElsewhere": "working_elsewhere",
    "unknown": "unavailable",
}


def task_native_chip(data: Mapping[str, object], ctx: RenderContext) -> str:
    native = data.get("native_task")
    if not isinstance(native, dict):
        return ""
    state = scalar_text(native.get("status"))
    return (
        render_chip(card_label(_TASK_STATES[state], ctx.language), "indigo", "hourglass_empty")
        if state in _TASK_STATES
        else ""
    )


def _date_row(value: object, label: str, ctx: RenderContext) -> str:
    if isinstance(value, dict):
        parsed = parse_provider_datetime(value)
        if parsed is None:
            text = scalar_text(value.get("dateTime"))
            zone = scalar_text(value.get("timeZone"))
            detail = f'{card_label("unavailable", ctx.language)} · {text} ({zone})' if text else ""
        else:
            detail = format_full_date(parsed, ctx.language, ctx.timezone, include_time=True)
    else:
        text = scalar_text(value)
        detail = (
            format_full_date(text, ctx.language, ctx.timezone, include_time=True) if text else ""
        )
    return (
        render_d_item(Icons.SCHEDULE, escape_html(label + label_separator(ctx.language) + detail))
        if detail
        else ""
    )


def task_native_details(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    native = data.get("native_task")
    if not isinstance(native, dict):
        return []
    rows = _lifecycle_dates(native, ctx)
    date_fields: tuple[tuple[str, CardLabel], ...] = (
        ("startDateTime", "start"),
        ("dueDateTime", "due"),
        ("reminderDateTime", "reminder"),
    )
    for key, label in date_fields:
        rows.append(_date_row(native.get(key), card_label(label, ctx.language), ctx))
    categories = [
        value for item in list_values(native.get("categories")) if (value := scalar_text(item))
    ]
    if categories:
        rows.append(render_d_item(Icons.LABEL, escape_html(", ".join(categories))))
    rows.append(_task_availability(native, ctx))
    rows.append(
        render_source_recurrence(
            native.get("recurrence"), native.get("startDateTime") or native.get("dueDateTime"), ctx
        )
    )
    return [row for row in rows if row]


def _task_availability(native: Mapping[str, object], ctx: RenderContext) -> str:
    availability: list[tuple[str, bool]] = []
    for key, label in (
        ("isReminderOn", card_label("reminder", ctx.language)),
        ("hasAttachments", V3Messages.get_attachments(ctx.language)),
    ):
        value = native.get(key)
        if isinstance(value, bool):
            availability.append((label, value))
    return render_availability_rows(availability, ctx.language)


def _lifecycle_dates(native: Mapping[str, object], ctx: RenderContext) -> list[str]:
    return [
        _date_row(native.get(key), label, ctx)
        for key, label in (
            ("createdDateTime", V3Messages.get_created(ctx.language)),
            ("lastModifiedDateTime", V3Messages.get_modified(ctx.language)),
        )
    ]


def event_native_details(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows = _unknown_event_times(data, ctx)
    native = data.get("native_event")
    if isinstance(native, dict):
        state = scalar_text(native.get("showAs"))
        if state in _EVENT_STATES:
            rows.append(
                render_d_item(
                    Icons.CALENDAR, escape_html(card_label(_EVENT_STATES[state], ctx.language))
                )
            )
        rows.extend(_lifecycle_dates(native, ctx))
    for key, choices in (
        ("transparency", {"transparent": "available", "opaque": "busy"}),
        (
            "visibility",
            {
                "public": "public",
                "private": "private",
                "confidential": "confidential",
                "default": "default_visibility",
            },
        ),
    ):
        if key == "transparency" and isinstance(native, dict):
            continue
        value = scalar_text(data.get(key))
        label = choices.get(value)
        if label:
            rows.append(
                render_d_item(
                    Icons.CALENDAR, escape_html(card_label_for_event(label, ctx.language))
                )
            )
    return [row for row in rows if row]


def _unknown_event_times(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows: list[str] = []
    fields: tuple[tuple[str, CardLabel], ...] = (("start", "start"), ("end", "end"))
    for key, label in fields:
        value = data.get(key)
        if isinstance(value, dict) and "dateTime" in value and "date" not in value:
            if parse_provider_datetime(value) is None:
                rows.append(_date_row(value, card_label(label, ctx.language), ctx))
    return rows


def card_label_for_event(value: str, language: str) -> str:
    labels: dict[str, CardLabel] = {
        "available": "available",
        "busy": "busy",
        "public": "public",
        "private": "private",
        "confidential": "confidential",
        "default_visibility": "default_visibility",
    }
    return card_label(labels[value], language)
