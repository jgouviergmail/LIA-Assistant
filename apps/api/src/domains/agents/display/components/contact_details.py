"""Multiple identities and organizations supplied by native contact connectors."""

from collections.abc import Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.domains.agents.display.components.base import RenderContext, escape_html, render_d_row
from src.domains.agents.display.components.contact_facts import (
    organization_facts,
    pronunciation_rows,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import list_values, scalar_text


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
            name = scalar_text(item.get("displayName")) or " ".join(
                value
                for key in (
                    "honorificPrefix",
                    "givenName",
                    "middleName",
                    "familyName",
                    "honorificSuffix",
                )
                if (value := scalar_text(item.get(key)))
            )
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
