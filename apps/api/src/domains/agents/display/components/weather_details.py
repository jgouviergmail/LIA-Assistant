"""Supplementary supplied weather readings, independent of series layout."""

from collections.abc import Mapping

from src.core.i18n_cards import CardLabel, card_label
from src.core.time_utils import parse_rfc3339
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    format_full_date,
    format_time,
    render_d_item,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import scalar_text


def weather_extra_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    fields: list[tuple[str, CardLabel, str]] = [
        ("wind_gust", "weather_gust", Icons.WIND),
        ("rain_amount", "weather_rain", Icons.RAINY),
        ("snow_amount", "weather_snow", Icons.SNOWY),
        ("dew_point", "dew_point", Icons.HUMIDITY),
        ("heat_index", "heat_index", Icons.TEMPERATURE),
        ("wind_chill", "wind_chill", Icons.WIND),
    ]
    rows = [
        render_d_item(
            symbol, escape_html(card_label(label, ctx.language)) + " · " + escape_html(value)
        )
        for key, label, symbol in fields
        if (value := scalar_text(data.get(key)))
    ]
    if (observed := parse_rfc3339(data.get("observation_time"))) is not None:
        rows.append(
            render_d_item(
                "schedule",
                escape_html(
                    format_full_date(observed, ctx.language, ctx.timezone, include_time=True)
                ),
            )
        )
    return rows


def weather_sun_rows(data: Mapping[str, object], ctx: RenderContext) -> list[str]:
    """Render only known sun times, keeping each existing localized clock."""
    sunrise = scalar_text(data.get("sunrise"))
    sunset = scalar_text(data.get("sunset"))
    parts = []
    if sunrise:
        parts.append(escape_html(format_time(sunrise, ctx.language, ctx.timezone)))
    if sunset:
        symbol = f'<span class="material-symbols-outlined" style="font-size:15px;vertical-align:middle">{Icons.SUNSET}</span>'
        parts.append(f"{symbol} {escape_html(format_time(sunset, ctx.language, ctx.timezone))}")
    return [render_d_item(Icons.SUNRISE, " · ".join(parts))] if parts else []
