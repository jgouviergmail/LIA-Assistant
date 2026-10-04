"""Progressively enhanced native weather selectors and textual comparison."""

from collections.abc import Callable, Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    render_collapsible,
)
from src.domains.agents.display.components.source_attribution import weather_attribution
from src.domains.agents.display.icons import icon
from src.domains.agents.display.values import first_present, list_values, scalar_text


def slot_time(data: Mapping[str, object], ctx: RenderContext, hourly: bool) -> str:
    value = scalar_text(first_present(data, "datetime_text", "date", "time"))
    if not value:
        return card_label("unavailable", ctx.language)
    if not hourly:
        return format_full_date(value, ctx.language, ctx.timezone)
    date, _, time = value.partition(" ")
    return f"{format_full_date(date, ctx.language, ctx.timezone)} · {time[:5]}" if time else value


def slot_temperature(
    data: Mapping[str, object], format_temperature: Callable[[object], str], hourly: bool
) -> str:
    if hourly:
        return format_temperature(first_present(data, "temp", "temperature"))
    raw = data.get("temp")
    temps = raw if isinstance(raw, dict) else data
    low = format_temperature(first_present(temps, "min", "temp_min", "temperature_min"))
    high = format_temperature(first_present(temps, "max", "temp_max", "temperature_max"))
    return " / ".join(value for value in (low, high) if value)


def render_weather_series(
    data: Mapping[str, object],
    ctx: RenderContext,
    *,
    hourly: bool,
    location: str,
    nested_class: str,
    format_temperature: Callable[[object], str],
    visual: Callable[[Mapping[str, object]], tuple[str, str]],
    render_detail: Callable[[dict[str, object], RenderContext], str],
    environment_html: str = "",
) -> str:
    slots = [
        slot
        for slot in list_values(data.get("hourly" if hourly else "forecasts"))
        if isinstance(slot, dict)
    ]
    if not slots:
        return ""
    content = []
    for index, slot in enumerate(slots):
        description = scalar_text(slot.get("description"))
        symbol, variant = visual(slot)
        title = slot_time(slot, ctx, hourly)
        temp = slot_temperature(slot, format_temperature, hourly)
        detail_data = {**slot, "type": "hourly" if hourly else "forecast", "location": ""}
        opened = " open" if index == 0 else ""
        content.append(
            f'<details class="lia-weather-slot lia-weather--{variant}"{opened}><summary><span class="lia-weather-slot__time">{escape_html(title)}</span><span class="lia-weather-slot__icon" aria-hidden="true">{icon(symbol)}</span><span class="lia-weather-slot__temp">{escape_html(temp)}</span><span class="lia-weather-slot__description">{escape_html(description)}</span></summary><div class="lia-weather-slot__detail">{render_detail(detail_data, ctx)}</div></details>'
        )
    interval = scalar_text(data.get("interval"))
    if interval == "3 hours":
        interval = "3 h"
    timezone = scalar_text(data.get("timezone")) or ctx.timezone
    cadence = f' · {card_label("weather_step", ctx.language)} {interval}' if interval else ""
    header = f'<div class="lia-weather__header-row"><span class="lia-weather__city">{escape_html(location)}</span><p class="lia-card__meta">{escape_html(timezone + cadence)}</p></div>'
    table = render_comparison(slots, ctx, hourly, format_temperature)
    return f'<div class="lia-card lia-weather lia-weather--{"hourly" if hourly else "forecast"} {nested_class}">{header}<div class="lia-weather-series">{"".join(content)}</div>{table}{environment_html}{weather_attribution(data)}</div>'


def render_comparison(
    slots: list[dict[str, object]],
    ctx: RenderContext,
    hourly: bool,
    format_temperature: Callable[[object], str],
) -> str:
    headings = [
        card_label("weather_time", ctx.language),
        V3Messages.get_temp_range(ctx.language),
        V3Messages.get_humidity(ctx.language),
        V3Messages.get_wind(ctx.language),
        V3Messages.get_precipitation(ctx.language),
    ]
    rows = []
    for slot in slots:
        cells = [
            slot_temperature(slot, format_temperature, hourly),
            scalar_text(slot.get("humidity")),
            scalar_text(slot.get("wind_speed")),
            scalar_text(slot.get("precipitation_probability")),
        ]
        if cells[-1]:
            cells[-1] += "%"
        row = f'<th scope="row">{escape_html(slot_time(slot, ctx, hourly))}</th>' + "".join(
            f'<td>{escape_html(value) if value else "—"}</td>' for value in cells
        )
        rows.append(f"<tr>{row}</tr>")
    caption = card_label("weather_compare", ctx.language)
    table = f'<div class="lia-weather-comparison" tabindex="0" role="region" aria-label="{escape_html(caption)}"><table><caption>{escape_html(caption)}</caption><thead><tr>{"".join(f"<th scope=\"col\">{escape_html(value)}</th>" for value in headings)}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    return render_collapsible(caption, table, with_separator=False)
