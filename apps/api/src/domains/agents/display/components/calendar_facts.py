"""Secondary calendar facts, never permission enforcement or a new API query."""

from collections.abc import Mapping

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.domains.agents.display.components.base import RenderContext, escape_html, render_d_item
from src.domains.agents.display.components.card_content import render_availability_rows
from src.domains.agents.display.values import list_values, scalar_text

_NOTIFICATION_LABELS: dict[str, CardLabel] = {
    "eventCreation": "event_creation",
    "eventChange": "event_change",
    "eventCancellation": "event_cancellation",
    "eventResponse": "event_response",
    "agenda": "daily_agenda",
}


def _notifications(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for item in list_values(value.get("notifications")):
        if not isinstance(item, dict):
            continue
        kind = scalar_text(item.get("type"))
        label = (
            card_label(_NOTIFICATION_LABELS[kind], ctx.language)
            if kind in _NOTIFICATION_LABELS
            else kind
        )
        method = scalar_text(item.get("method"))
        method = card_label("email_notification", ctx.language) if method == "email" else method
        if label:
            parts.append(
                render_d_item(
                    "notifications",
                    escape_html(" · ".join(part for part in (label, method) if part)),
                )
            )
    return "".join(parts)


def calendar_additional_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows: list[str] = []
    for key, symbol in (("location", "location_on"), ("dataOwner", "person")):
        if text := scalar_text(data.get(key)):
            label = (
                card_label("calendar_owner", ctx.language) + label_separator(ctx.language)
                if key == "dataOwner"
                else ""
            )
            rows.append(render_d_item(symbol, escape_html(label + text)))
    states: list[tuple[str, bool]] = []
    keys: tuple[tuple[str, CardLabel], ...] = (
        ("deleted", "calendar_deleted"),
        ("autoAcceptInvitations", "auto_accept_invitations"),
    )
    for key, label in keys:
        value = data.get(key)
        if isinstance(value, bool):
            states.append((card_label(label, ctx.language), value))
    rows.append(render_availability_rows(states, ctx.language))
    rows.append(_notifications(data.get("notificationSettings"), ctx))
    return rows
