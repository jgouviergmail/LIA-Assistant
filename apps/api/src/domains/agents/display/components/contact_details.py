"""Multiple identities and organizations supplied by native contact connectors."""

from collections.abc import Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_d_item,
    render_d_row,
    safe_url,
)
from src.domains.agents.display.components.contact_facts import (
    organization_facts,
    pronunciation_rows,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, scalar_text


def contact_name(value: Mapping[str, object]) -> str:
    """Use the supplied formatted name, or all supplied human name components."""
    return scalar_text(value.get("displayName")) or " ".join(
        text
        for key in ("honorificPrefix", "givenName", "middleName", "familyName", "honorificSuffix")
        if (text := scalar_text(value.get(key)))
    )


def contact_address(value: object) -> str:
    """Keep an address even when the provider supplied only its structured parts."""
    if not isinstance(value, dict):
        return scalar_text(value)
    return scalar_text(value.get("formattedValue") or value.get("formatted")) or ", ".join(
        text
        for key in (
            "poBox",
            "extendedAddress",
            "streetAddress",
            "city",
            "region",
            "postalCode",
            "country",
        )
        if (text := scalar_text(value.get(key)))
    )


def typed_contact_row(
    icon_name: str, content_html: str, badge_html: str, icon_style: str = ""
) -> str:
    """Keep a received value and its qualifier in the same wrapping text flow."""
    return render_d_row(
        icon_name,
        f'<span class="lia-contact__value">{content_html} {badge_html}</span>',
        icon_style,
    )


def website_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    """Keep each received website and its label; unsafe schemes remain plain text."""
    rows: list[str] = []
    for item in list_values(data.get("urls")):
        value = scalar_text(item.get("value")) if isinstance(item, dict) else scalar_text(item)
        if not value:
            continue
        target = safe_url(value)
        text = (
            f'<a href="{target}" target="_blank" rel="noopener noreferrer">{escape_html(value)}</a>'
            if target
            else escape_html(value)
        )
        kind = (
            scalar_text(item.get("formattedType") or item.get("type"))
            if isinstance(item, dict)
            else ""
        )
        if kind:
            text += " · " + escape_html(V3Messages.get_data_type(ctx.language, kind))
        rows.append(render_d_item(Icons.LINK, text))
    return rows


def organization_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows: list[str] = []
    for index, item in enumerate(list_values(data.get("organizations"))):
        if not isinstance(item, dict):
            continue
        values = [scalar_text(item.get(key)) for key in ("name", "title", "department")]
        # The first name/title already identify the person above the details.
        text = " · ".join(value for value in (values if index else values[2:]) if value)
        if text:
            if index == 0:
                text = card_label("department", ctx.language) + label_separator(ctx.language) + text
            rows.append(render_d_row(Icons.WORK, escape_html(text)))
        for key in ("jobDescription", "location", "phoneticName", "symbol"):
            value = scalar_text(item.get(key))
            if value:
                rows.append(render_d_row(Icons.WORK, escape_html(value)))
        rows.extend(organization_facts(item, ctx))
    return rows


def alternate_name_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    values: list[str] = []
    for item in list_values(data.get("names"))[1:]:
        if isinstance(item, dict):
            name = contact_name(item)
            if name and name not in values:
                values.append(name)
    pronunciations = pronunciation_rows(data, ctx)
    if not values:
        return pronunciations
    text = (
        card_label("alternate_names", ctx.language)
        + label_separator(ctx.language)
        + ", ".join(values)
    )
    return [render_d_row(Icons.PERSON, escape_html(text)), *pronunciations]
