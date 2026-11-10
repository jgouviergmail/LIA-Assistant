"""Complete received event bounds, including civil inclusive all-day periods."""

from collections.abc import Mapping
from datetime import date, timedelta

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.core.time_utils import parse_provider_datetime
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    render_d_item,
)
from src.domains.agents.display.values import scalar_text


def _civil_day(value: object) -> date | None:
    if not isinstance(value, dict):
        return None
    try:
        return date.fromisoformat(scalar_text(value.get("date")))
    except ValueError:
        return None


def _timed_bound(value: object, ctx: RenderContext) -> str:
    instant = parse_provider_datetime(value) if isinstance(value, dict) else None
    return (
        format_full_date(instant, ctx.language, ctx.timezone, include_time=True)
        + f" ({ctx.timezone})"
        if instant
        else ""
    )


def _bounds(data: Mapping[str, object], ctx: RenderContext) -> tuple[str, str]:
    start, end = data.get("start"), data.get("end")
    if isinstance(start, dict) and start.get("date"):
        first, stop = _civil_day(start), _civil_day(end)
        start_text = format_full_date(first.isoformat(), ctx.language, "UTC") if first else ""
        if first and stop and stop > first:
            last = stop - timedelta(days=1)
            return start_text, format_full_date(last.isoformat(), ctx.language, "UTC")
        # An invalid or non-increasing source bound never invents a covered day.
        raw_end = scalar_text(end.get("date")) if isinstance(end, dict) else ""
        end_text = f'{card_label("unavailable", ctx.language)} · {raw_end}' if raw_end else ""
        return start_text, end_text
    return _timed_bound(start, ctx), _timed_bound(end, ctx)


def event_schedule_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    """Keep both complete bounds and source zones; opening details performs no read."""
    start, end = _bounds(data, ctx)
    rows: list[str] = []
    for label, text in (
        (card_label("start", ctx.language), start),
        (card_label("end", ctx.language), end),
    ):
        if text:
            rows.append(
                render_d_item("schedule", escape_html(label + label_separator(ctx.language) + text))
            )
    zones: list[str] = []
    for value in (
        data.get("ownZone"),
        *(
            bound.get("timeZone") if isinstance(bound, dict) else None
            for bound in (data.get("start"), data.get("end"))
        ),
    ):
        zone = scalar_text(value)
        if zone and zone not in zones:
            zones.append(zone)
    if zones:
        rows.append(
            render_d_item(
                "schedule",
                escape_html(
                    card_label("source_timezone", ctx.language)
                    + label_separator(ctx.language)
                    + " · ".join(zones)
                ),
            )
        )
    return rows
