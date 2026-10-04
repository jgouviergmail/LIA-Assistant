"""Permission facts from the fetched Drive resource; never infer absent owners."""

from collections.abc import Mapping

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    render_d_item,
    safe_url,
)
from src.domains.agents.display.components.card_content import render_availability_rows
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, scalar_text

_ROLES: dict[str, CardLabel] = {
    "owner": "owner",
    "writer": "writer",
    "reader": "reader",
    "commenter": "commenter",
    "organizer": "organizer",
    "fileOrganizer": "fileOrganizer",
}
_TYPES: dict[str, CardLabel] = {
    "anyone": "anyone",
    "group": "group",
    "domain": "domain",
    "user": "person",
}


def person_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    name = scalar_text(value.get("displayName"))
    email = scalar_text(value.get("emailAddress"))
    return f"{name} ({email})" if name and email and name != email else name or email


def _permission(value: object, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return ""
    identity = person_label(value) or scalar_text(value.get("domain"))
    kind = scalar_text(value.get("type"))
    if not identity and kind in _TYPES:
        identity = card_label(_TYPES[kind], ctx.language)
    role = scalar_text(value.get("role"))
    role_label = card_label(_ROLES[role], ctx.language) if role in _ROLES else role
    parts = [text for text in (identity, role_label) if text]
    expires = scalar_text(value.get("expirationTime"))
    if expires:
        date = format_full_date(expires, ctx.language, ctx.timezone, include_time=True)
        if date:
            parts.append(card_label("expires", ctx.language) + label_separator(ctx.language) + date)
    return render_d_item(Icons.GROUP, escape_html(" · ".join(parts))) if parts else ""


def file_metadata_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows = [_permission(item, ctx) for item in list_values(data.get("permissions"))]
    facts: tuple[tuple[str, CardLabel, str], ...] = (
        ("sharingUser", "shared_by", Icons.PERSON),
        ("version", "version", Icons.FILE),
    )
    for key, label, symbol in facts:
        value = person_label(data.get(key)) if key == "sharingUser" else scalar_text(data.get(key))
        if value:
            translated = card_label(label, ctx.language)
            rows.append(
                render_d_item(
                    symbol, escape_html(translated + label_separator(ctx.language) + value)
                )
            )
    rows.extend(_file_access_rows(data, ctx))
    return [row for row in rows if row]


def _file_access_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    labels = {
        "shared": V3Messages.get_shared(ctx.language),
        "starred": V3Messages.get_favorite(ctx.language),
        "trashed": card_label("in_trash", ctx.language),
    }
    available: list[tuple[str, bool]] = []
    for key, label in labels.items():
        value = data.get(key)
        if isinstance(value, bool):
            available.append((label, value))
    rows = [render_availability_rows(available, ctx.language)] if available else []
    download = safe_url(scalar_text(data.get("webContentLink")))
    if download:
        link = f'<a href="{download}" target="_blank" rel="noopener noreferrer">{escape_html(card_label("download", ctx.language))}</a>'
        rows.append(render_d_item(Icons.FILE, link))
    return rows
