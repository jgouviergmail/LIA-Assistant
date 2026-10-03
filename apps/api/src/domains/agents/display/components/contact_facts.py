"""Phonetics and partial civil employment dates, without invented components."""

from collections.abc import Mapping
from datetime import date

from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_date,
    render_d_row,
)
from src.domains.agents.display.components.card_content import render_availability_rows
from src.domains.agents.display.values import (
    list_values,
    nonnegative_integer,
    nonnegative_number,
    scalar_text,
)


def _valid_date_parts(year: int, month: int, day: int) -> bool:
    if year > 9999 or month > 12 or day > 31 or (day and not month):
        return False
    if month and day:
        try:
            date(year or 2000, month, day)  # Validate an unknown year without emitting one.
        except ValueError:
            return False
    return True


def _partial_date(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    numbers = [nonnegative_integer(value.get(key, 0)) for key in ("year", "month", "day")]
    if any(number is None for number in numbers):
        return ""
    year, month, day = (int(number or 0) for number in numbers)
    if not _valid_date_parts(year, month, day):
        return ""
    parts = [f"{year:04d}" if year else "-"]
    parts.extend(f"{number:02d}" for number in (month, day) if number)
    return "-".join(parts) if year or month else ""


def organization_facts(value: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows: list[str] = []
    kind = scalar_text(value.get("formattedType")) or scalar_text(value.get("type"))
    if kind:
        rows.append(render_d_row("work", escape_html(V3Messages.get_data_type(ctx.language, kind))))
    keys: tuple[tuple[str, CardLabel], ...] = (("startDate", "start"), ("endDate", "end"))
    for key, label in keys:
        if iso := _partial_date(value.get(key)):
            text = (
                format_date(iso, ctx.language, "UTC")
                if len(iso) == 10 and not iso.startswith("-")
                else iso
            )
            content = (
                f'<time datetime="{iso}">{escape_html(text)}</time>'
                if len(iso) == 10 and not iso.startswith("-")
                else escape_html(text)
            )
            rows.append(
                render_d_row(
                    "calendar_month",
                    f"<span>{escape_html(card_label(label, ctx.language))}{label_separator(ctx.language)}{content}</span>",
                )
            )
    current = value.get("current")
    if isinstance(current, bool):
        rows.append(
            render_availability_rows(
                [(card_label("current_organization", ctx.language), current)], ctx.language
            )
        )
    for key in ("domain", "costCenter"):
        if text := scalar_text(value.get(key)):
            caption = (
                card_label("cost_center", ctx.language) + label_separator(ctx.language)
                if key == "costCenter"
                else ""
            )
            rows.append(render_d_row("work", escape_html(caption + text)))
    if (equivalent := nonnegative_number(value.get("fullTimeEquivalentMillipercent"))) is not None:
        rows.append(
            render_d_row(
                "work",
                escape_html(
                    f'{card_label("full_time_equivalent", ctx.language)}{label_separator(ctx.language)}{equivalent / 1000:g}%'
                ),
            )
        )
    return rows


def pronunciation_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    rows: list[str] = []
    for value in list_values(data.get("names")):
        if not isinstance(value, dict):
            continue
        text = scalar_text(value.get("phoneticFullName")) or " ".join(
            text
            for key in (
                "phoneticHonorificPrefix",
                "phoneticGivenName",
                "phoneticMiddleName",
                "phoneticFamilyName",
                "phoneticHonorificSuffix",
            )
            if (text := scalar_text(value.get(key)))
        )
        if text:
            rows.append(
                render_d_row(
                    "record_voice_over",
                    escape_html(
                        card_label("pronunciation", ctx.language)
                        + label_separator(ctx.language)
                        + text
                    ),
                )
            )
    return rows
