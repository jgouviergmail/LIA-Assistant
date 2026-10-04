"""Calendar defaults and event reminders share one supplied-value presentation."""

from collections.abc import Mapping
from copy import deepcopy

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext, escape_html, render_d_item
from src.domains.agents.display.components.calendar_facts import calendar_additional_rows
from src.domains.agents.display.components.card_content import (
    render_availability_rows,
    render_details,
)
from src.domains.agents.display.values import list_values, nonnegative_integer, scalar_text


def reminder_text(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    minutes = nonnegative_integer(value.get("minutes"))
    if minutes is None or minutes > 40320:
        return ""
    method = value.get("method")
    label = (
        card_label(
            "email_notification" if method == "email" else "popup_notification", ctx.language
        )
        if method in ("email", "popup")
        else scalar_text(method)
    )
    time = V3Messages.get_reminder_time(ctx.language, minutes)
    return f"{label} · {time}" if label else time


def _reminder_state(value: object, values: object, *, defaults: bool) -> str:
    if defaults:
        return "none_default" if values == [] else ""
    if not isinstance(value, dict):
        return ""
    if value.get("useDefault") is True:
        return "default"
    if value.get("useDefault") is False and ("overrides" not in value or values == []):
        return "none"
    return ""


def render_reminder_settings(value: object, ctx: RenderContext, *, defaults: bool = False) -> str:
    values = value if defaults else value.get("overrides") if isinstance(value, dict) else None
    entries = [text for item in list_values(values) if (text := reminder_text(item, ctx))]
    if entries:
        return render_d_item("notifications", escape_html("; ".join(entries)))
    if isinstance(values, list) and values:
        return render_d_item("notifications", escape_html(card_label("unavailable", ctx.language)))
    state = _reminder_state(value, values, defaults=defaults)
    if state == "default":
        return render_d_item(
            "notifications", escape_html(V3Messages.get_default_reminder(ctx.language))
        )
    if state in ("none", "none_default"):
        label = card_label(
            "no_reminders" if state == "none" else "no_default_reminders", ctx.language
        )
        return render_d_item("notifications_off", escape_html(label))
    return ""


def calendar_display_fields(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "original_summary": value.get("summary", ""),
        **{
            key: deepcopy(value[key])
            for key in (
                "selected",
                "hidden",
                "defaultReminders",
                "summaryOverride",
                "location",
                "dataOwner",
                "deleted",
                "autoAcceptInvitations",
                "notificationSettings",
            )
            if key in value
        },
    }


def render_calendar_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    rows: list[str] = []
    override = scalar_text(data.get("summaryOverride"))
    original = scalar_text(data.get("original_summary")) or scalar_text(data.get("summary"))
    if override and original and override != original:
        rows.append(
            render_d_item(
                "label",
                escape_html(
                    card_label("original_name", ctx.language)
                    + label_separator(ctx.language)
                    + original
                ),
            )
        )
    states: list[tuple[str, bool]] = []
    for key in ("selected", "hidden"):
        value = data.get(key)
        if isinstance(value, bool):
            states.append(
                (card_label("selected" if key == "selected" else "hidden", ctx.language), value)
            )
    rows.append(render_availability_rows(states, ctx.language))
    rows.append(render_reminder_settings(data.get("defaultReminders"), ctx, defaults=True))
    rows.extend(calendar_additional_rows(data, ctx))
    return render_details("".join(rows), ctx)
