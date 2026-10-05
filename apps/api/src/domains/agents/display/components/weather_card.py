"""
WeatherCard Component - Modern Weather Display v3.0.

Renders weather data with:
- Wrapper for assistant comment + suggested actions
- Visual weather icons (complete mapping)
- Current conditions, forecasts, and hourly
- Collapsible extended details (UV, pressure, visibility)
- Animated background effects
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from functools import partial
from typing import Any

from src.core.geo_utils import WIND_CARDINAL_CODES, wind_deg_to_cardinal
from src.core.i18n import resolve_language
from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_WEATHER
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_full_date,
    render_collapsible,
    render_d_item,
    wrap_with_response,
)
from src.domains.agents.display.components.environment_row import (
    air_quality_text,
    pollen_text,
)
from src.domains.agents.display.components.source_attribution import weather_attribution
from src.domains.agents.display.components.weather_collection import prepare_weather_items
from src.domains.agents.display.components.weather_details import (
    weather_extra_rows,
    weather_sun_rows,
)
from src.domains.agents.display.components.weather_series import render_weather_series
from src.domains.agents.display.icons import Icons, icon
from src.domains.agents.display.values import first_present, nonnegative_number, scalar_text


def _add_labelled_row(
    rows: list[str], separator: str, icon_name: str, label: str, value: str
) -> None:
    """One detail row: a label joined to its value by the reader's punctuation."""
    rows.append(render_d_item(icon_name, f"{label}{separator}{value}"))


class WeatherCard(BaseComponent):
    """
    Modern weather card component v3.0.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Large temperature display with animated icon
    - Feels-like, humidity, wind in compact grid
    - Collapsible extended details (UV, pressure, visibility, sun times)
    - Multi-day forecast strip
    - Hourly forecast (desktop)
    """

    # Complete weather condition to icon/class mapping
    # icon_name is a Material Symbols icon name
    WEATHER_ICONS: dict[str, tuple[str, str]] = {
        # Clear/Sunny conditions (EN + FR + DE + ES + IT)
        "clear": (Icons.SUNNY, "sunny"),
        "sunny": (Icons.SUNNY, "sunny"),
        "clear sky": (Icons.SUNNY, "sunny"),
        "fine": (Icons.SUNNY, "sunny"),
        "fair": (Icons.SUNNY, "sunny"),
        "ciel dégagé": (Icons.SUNNY, "sunny"),
        "ciel clair": (Icons.SUNNY, "sunny"),
        "ensoleillé": (Icons.SUNNY, "sunny"),
        "dégagé": (Icons.SUNNY, "sunny"),
        # Partly cloudy (EN + FR)
        "partly cloudy": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "partly_cloudy": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "few clouds": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "scattered clouds": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "mostly sunny": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "mostly clear": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "partiellement nuageux": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "partiellement couvert": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "éclaircies": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        # Cloudy conditions (EN + FR)
        "clouds": (Icons.CLOUDY, "cloudy"),
        "cloudy": (Icons.CLOUDY, "cloudy"),
        "broken clouds": (Icons.CLOUDY, "cloudy"),
        "overcast": (Icons.CLOUDY, "overcast"),
        "overcast clouds": (Icons.CLOUDY, "overcast"),
        "mostly cloudy": (Icons.CLOUDY, "cloudy"),
        "nuageux": (Icons.CLOUDY, "cloudy"),
        "couvert": (Icons.CLOUDY, "overcast"),
        "très nuageux": (Icons.CLOUDY, "overcast"),
        # Rain conditions (EN + FR)
        "rain": (Icons.RAINY, "rainy"),
        "light rain": (Icons.RAINY, "light-rain"),
        "moderate rain": (Icons.RAINY, "rainy"),
        "heavy rain": (Icons.RAINY, "heavy-rain"),
        "shower rain": (Icons.RAINY, "rainy"),
        "showers": (Icons.RAINY, "rainy"),
        "drizzle": (Icons.RAINY, "drizzle"),
        "light drizzle": (Icons.RAINY, "drizzle"),
        "patchy rain": (Icons.RAINY, "light-rain"),
        "pluie": (Icons.RAINY, "rainy"),
        "pluie légère": (Icons.RAINY, "light-rain"),
        "pluie modérée": (Icons.RAINY, "rainy"),
        "pluie forte": (Icons.RAINY, "heavy-rain"),
        "bruine": (Icons.RAINY, "drizzle"),
        "averses": (Icons.RAINY, "rainy"),
        # Thunderstorm (EN + FR)
        "thunderstorm": (Icons.STORMY, "stormy"),
        "orage": (Icons.STORMY, "stormy"),
        "orageux": (Icons.STORMY, "stormy"),
        "thunder": (Icons.STORMY, "stormy"),
        "storm": (Icons.STORMY, "stormy"),
        "thundery": (Icons.STORMY, "stormy"),
        "lightning": (Icons.STORMY, "stormy"),
        # Snow conditions (EN + FR)
        "snow": (Icons.SNOWY, "snowy"),
        "neige": (Icons.SNOWY, "snowy"),
        "neige légère": (Icons.SNOWY, "light-snow"),
        "neige forte": (Icons.SNOWY, "heavy-snow"),
        "light snow": (Icons.SNOWY, "light-snow"),
        "heavy snow": (Icons.SNOWY, "heavy-snow"),
        "sleet": (Icons.SNOWY, "sleet"),
        "freezing rain": (Icons.SNOWY, "sleet"),
        "blizzard": (Icons.SNOWY, "blizzard"),
        "flurries": (Icons.SNOWY, "light-snow"),
        # Fog/Mist conditions (EN + FR)
        "mist": (Icons.FOGGY, "misty"),
        "brouillard": (Icons.FOGGY, "foggy"),
        "brume": (Icons.FOGGY, "misty"),
        "fog": (Icons.FOGGY, "foggy"),
        "haze": (Icons.FOGGY, "hazy"),
        "smoke": (Icons.FOGGY, "smoky"),
        "dust": (Icons.FOGGY, "dusty"),
        "sand": (Icons.FOGGY, "dusty"),
        # Wind conditions
        "windy": (Icons.WIND, "windy"),
        "breezy": (Icons.WIND, "breezy"),
        "gust": (Icons.WIND, "gusty"),
        # Night conditions (for future night mode support)
        "clear night": ("dark_mode", "clear-night"),
        "night": ("dark_mode", "night"),
        # Extreme conditions
        "tornado": (Icons.STORMY, "tornado"),
        "hurricane": (Icons.STORMY, "hurricane"),
        "tropical storm": (Icons.STORMY, "tropical-storm"),
    }

    # Both providers expose the OWM code contract, independent of localized prose.
    # https://openweathermap.org/api/weather-conditions
    PROVIDER_ICONS: dict[str, tuple[str, str]] = {
        "01": (Icons.SUNNY, "sunny"),
        "02": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "03": (Icons.CLOUDY, "cloudy"),
        "04": (Icons.CLOUDY, "overcast"),
        "09": (Icons.RAINY, "rainy"),
        "10": (Icons.RAINY, "rainy"),
        "11": (Icons.STORMY, "stormy"),
        "13": (Icons.SNOWY, "snowy"),
        "50": (Icons.FOGGY, "foggy"),
    }

    def prepare_items(self, items: Sequence[object], ctx: RenderContext) -> list[object]:
        return prepare_weather_items(items)

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """
        Render weather as modern card with wrapper.

        Args:
            data: Weather data from API
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            is_first_item: If True, add top separator (for list rendering)
            is_last_item: If True, add bottom separator (for list rendering)
            with_wrapper: Whether to wrap with response zones

        Returns:
            HTML string for the weather card
        """
        weather_type = data.get("type", "current")

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(data, ctx)

        # Render based on type
        if weather_type == "forecast" and "forecasts" in data:
            # Multi-day forecast (consolidated list)
            card_html = self._render_forecast(data, ctx)
        elif weather_type == "hourly" and "hourly" in data:
            card_html = self._render_hourly(data, ctx)
        else:
            card_html = self._render_current(data, ctx)

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_WEATHER,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self, data: dict[str, Any], ctx: RenderContext
    ) -> list[dict[str, str]]:
        """Build default action buttons for weather."""
        actions = []
        location = self._get_location(data)

        # Always show forecast button - use location if available, else generic search
        if location:
            weather_url = f"https://www.google.com/search?q=weather+{escape_html(location)}"
        else:
            weather_url = "https://www.google.com/search?q=weather"

        actions.append(
            {
                "icon": Icons.DATE_RANGE,
                "label": V3Messages.get_forecast(ctx.language),
                "url": weather_url,
            }
        )

        return actions

    def _render_current(
        self, data: dict[str, Any], ctx: RenderContext, *, panel: bool = False
    ) -> str:
        """Render current weather with all details."""
        location = self._get_location(data)
        # Support both current weather (temperature/temp) and forecast items (temp_day/temp_max)
        temp = self._format_temperature(
            first_present(data, "temperature", "temp", "temp_day", "temp_max")
        )
        feels_like = self._format_temperature(data.get("feels_like", ""))
        description = scalar_text(data.get("description"))
        humidity = scalar_text(data.get("humidity"))
        wind = scalar_text(data.get("wind_speed"))
        wind_dir = self._format_wind_direction(data.get("wind_direction", ""), ctx.language)

        # Extract and format date
        date_str = self._get_date(data, ctx)

        icon_name, weather_class = self._visual_for_reading(data)
        nested_class = self._nested_class(ctx)

        # Detect forecast vs current weather for stat display
        is_forecast = data.get("type") == "forecast"

        # i18n labels
        humidity_label = V3Messages.get_humidity(ctx.language)
        wind_label = V3Messages.get_wind(ctx.language)

        # First stat: feels_like for current weather, temp range for forecast
        if is_forecast:
            first_stat_label = V3Messages.get_temp_range(ctx.language)
            temp_min = self._format_temperature(data.get("temp_min", ""))
            temp_max = self._format_temperature(data.get("temp_max", ""))
            first_stat_value = f"{temp_min} / {temp_max}" if temp_min and temp_max else "-"
            first_stat_icon = Icons.TEMPERATURE
        else:
            first_stat_label = V3Messages.get_feels_like(ctx.language)
            first_stat_value = escape_html(feels_like) if feels_like else "-"
            first_stat_icon = Icons.TEMPERATURE

        # Collapsible extended details for all viewports
        collapsible_html = self._render_extended_details(data, ctx)

        # Unified layout for ALL viewports - CSS handles responsive differences
        # Date and location for the right section
        date_html = (
            f'<div class="lia-weather__date">{escape_html(date_str)}</div>' if date_str else ""
        )
        location_html = (
            f'<div class="lia-weather__city">{escape_html(location)}</div>' if location else ""
        )

        # Wind text (value only, label handled by CSS)
        wind_text = (
            f"{escape_html(wind)} {escape_html(wind_dir)}" if wind_dir else escape_html(wind)
        )

        card_class = "lia-weather-reading" if panel else "lia-card"
        return f"""<div class="{card_class} lia-weather lia-weather--{weather_class} {nested_class}">
<div class="lia-weather__layout">
<div class="lia-weather__left">
<span class="lia-weather__icon">{icon(icon_name)}</span>
<span class="lia-weather__temp">{escape_html(temp)}</span>
<div class="lia-weather__desc">{escape_html(description)}</div>
</div>
<div class="lia-weather__right">
{date_html}
{location_html}
</div>
</div>
<div class="lia-weather__stats">
<div class="lia-weather__stat">
<span class="lia-weather__stat-icon">{icon(first_stat_icon)}</span>
<span class="lia-weather__stat-label">{escape_html(first_stat_label)}</span>
<span class="lia-weather__stat-value">{first_stat_value}</span>
</div>
<div class="lia-weather__stat">
<span class="lia-weather__stat-icon">{icon(Icons.HUMIDITY)}</span>
<span class="lia-weather__stat-label">{escape_html(humidity_label)}</span>
<span class="lia-weather__stat-value">{escape_html(humidity) if humidity else '-'}</span>
</div>
<div class="lia-weather__stat">
<span class="lia-weather__stat-icon">{icon(Icons.WIND)}</span>
<span class="lia-weather__stat-label">{escape_html(wind_label)}</span>
<span class="lia-weather__stat-value">{wind_text if wind else '-'}</span>
</div>
</div>
{collapsible_html}
{weather_attribution(data)}
</div>"""

    def _render_extended_details(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render collapsible section with extended weather details using v4 d-item."""
        detail_sections: list[str] = weather_extra_rows(data, ctx)

        # i18n labels
        uv_index_label = V3Messages.get_uv_index(ctx.language)
        pressure_label = V3Messages.get_pressure(ctx.language)
        visibility_label = V3Messages.get_visibility(ctx.language)
        cloud_cover_label = V3Messages.get_cloud_cover(ctx.language)
        air_quality_label = V3Messages.get_air_quality(ctx.language)
        precipitation_label = V3Messages.get_precipitation(ctx.language)
        labelled = partial(_add_labelled_row, detail_sections, label_separator(ctx.language))

        # Temperature min/max (for current weather — forecast already shows it in main stats)
        is_forecast = data.get("type") == "forecast"
        if not is_forecast:
            temp_min = self._format_temperature(data.get("temp_min", ""))
            temp_max = self._format_temperature(data.get("temp_max", ""))
            if temp_min and temp_max:
                temp_range = f"{escape_html(temp_min)} / {escape_html(temp_max)}"
                labelled(Icons.TEMPERATURE, V3Messages.get_temp_range(ctx.language), temp_range)

        # UV Index
        uv_index = scalar_text(first_present(data, "uv_index", "uv"))
        if uv_index != "" and (uv_level_label := self._get_uv_label(uv_index, ctx.language)):
            labelled(
                Icons.SUNNY, uv_index_label, f"{escape_html(str(uv_index))} ({uv_level_label})"
            )

        # Pressure, visibility, cloud cover
        pressure = scalar_text(data.get("pressure"))
        if pressure:
            labelled(Icons.PRESSURE, pressure_label, escape_html(str(pressure)))
        visibility = scalar_text(data.get("visibility"))
        if visibility:
            labelled(Icons.VISIBILITY, visibility_label, escape_html(str(visibility)))
        clouds = scalar_text(first_present(data, "clouds", "cloud_cover"))
        if clouds != "":
            labelled(Icons.CLOUD_COVER, cloud_cover_label, f"{escape_html(str(clouds))}%")

        detail_sections.extend(weather_sun_rows(data, ctx))

        # Air quality. Two shapes coexist:
        #  - environment enrichment (2026-08): the API's own localized
        #    category WINS — Google's universal index is inverted vs EPA
        #    (100 = excellent), so a label is never re-derived from a number.
        #    The national index often ships a category with NO number at all
        #    (measured in prod), hence rendering on the category, not the value;
        #  - legacy numeric payloads: EPA table, unchanged.
        aqi_row = self._air_quality_row(data, air_quality_label, ctx.language)
        if aqi_row:
            detail_sections.append(render_d_item(Icons.WIND, aqi_row))

        # In-season pollen (environment enrichment): one line per active type,
        # the API's localized category verbatim — an honest, verifiable signal.
        pollen_row = self._pollen_row(data, ctx.language)
        if pollen_row:
            detail_sections.append(render_d_item("allergy", pollen_row))

        # Precipitation probability
        precip = scalar_text(first_present(data, "precipitation_probability", "pop"))
        if precip != "":
            labelled(Icons.RAINY, precipitation_label, f"{escape_html(str(precip))}%")

        # Wrap in collapsible using v4 component
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=content_html,
                initially_open=False,
                with_separator=True,
            )

        return ""

    def _render_forecast(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render every supplied slot with local details and comparison."""
        return render_weather_series(
            data,
            ctx,
            hourly=False,
            location=self._get_location(data),
            nested_class=self._nested_class(ctx),
            format_temperature=self._format_temperature,
            visual=self._visual_for_reading,
            render_detail=partial(self._render_current, panel=True),
            environment_html=self._environment_strip(data, ctx),
        )

    def _render_hourly(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render every supplied slot with local details and comparison."""
        return render_weather_series(
            data,
            ctx,
            hourly=True,
            location=self._get_location(data),
            nested_class=self._nested_class(ctx),
            format_temperature=self._format_temperature,
            visual=self._visual_for_reading,
            render_detail=partial(self._render_current, panel=True),
        )

    # Generic location names to filter out (not useful to display)
    GENERIC_LOCATIONS: frozenset[str] = frozenset(
        {
            "current location",
            "position actuelle",
            "ma position",
            "your location",
            "votre position",
            "ta position",
            "ubicación actual",
            "aktuelle position",
            "posizione attuale",
        }
    )

    def _get_location(self, data: Mapping[str, object]) -> str:
        """Extract location name from weather data, filtering generic names."""
        loc = data.get("location", {})
        if isinstance(loc, dict):
            # Prefer city/name
            city = scalar_text(first_present(loc, "city", "name", "locality"))
            if city and city.lower() not in self.GENERIC_LOCATIONS:
                return city
            # Fall back to address components
            region = scalar_text(first_present(loc, "region", "country"))
            if region and region.lower() not in self.GENERIC_LOCATIONS:
                return region
            return ""
        # Handle string location
        if isinstance(loc, str) and loc.lower() not in self.GENERIC_LOCATIONS:
            return loc
        return ""

    def _get_date(self, data: dict, ctx: RenderContext) -> str:
        """Extract and format date from weather data, defaults to today."""
        # Try various date fields - prefer parseable formats over pre-formatted
        date_raw = (
            data.get("datetime")
            or data.get("date")
            or data.get("observation_time")
            or data.get("timestamp")
            or data.get("date_formatted")
            or ""
        )

        # Default to "Aujourd'hui" / "Today" if no date provided
        if not date_raw:
            return V3Messages.get_today(ctx.language)

        # Always format using user's locale settings
        return format_full_date(date_raw, ctx.language, ctx.timezone)

    def _format_temperature(self, temp: Any) -> str:
        """Format temperature as rounded integer."""
        if isinstance(temp, dict):
            return self._format_temperature_dict(temp)
        temp_str = scalar_text(temp)
        if not temp_str:
            return ""
        # Extract numeric part and round
        with suppress(ValueError, TypeError):
            # Remove unit suffix if present (e.g., "12.5°C" -> "12.5")
            import re

            match = re.match(r"(-?\d+\.?\d*)", temp_str.replace(",", "."))
            if match:
                value = float(match.group(1))
                rounded = round(value)
                # Preserve unit if present
                unit = temp_str[len(match.group(0)) :].strip()
                return f"{rounded}{unit}" if unit else f"{rounded}°C"
        return temp_str

    def _format_temperature_dict(self, temp: dict[str, Any]) -> str:
        """Resolve a temperature range independently of scalar rounding."""
        if "avg" in temp:
            return self._format_temperature(temp["avg"])
        if "min" in temp and "max" in temp:
            low = self._extract_numeric_temp(temp["min"])
            high = self._extract_numeric_temp(temp["max"])
            if low is not None and high is not None:
                low_unit = "°F" if scalar_text(temp["min"]).endswith("°F") else "°C"
                high_unit = "°F" if scalar_text(temp["max"]).endswith("°F") else "°C"
                if low_unit == high_unit:
                    return f"{round((low + high) / 2)}{low_unit}"
        return self._format_temperature(first_present(temp, "max", "min"))

    def _extract_numeric_temp(self, temp_str: str) -> float | None:
        """Extract numeric value from temperature string."""
        if not temp_str:
            return None
        with suppress(ValueError, TypeError):
            import re

            match = re.match(r"(-?\d+\.?\d*)", str(temp_str).replace(",", "."))
            if match:
                return float(match.group(1))
        return None

    def _format_wind_direction(self, direction: Any, language: str | None = None) -> str:
        """Format a provider wind direction as a localized compass point.

        The provider field is built as ``f"{wind.get('deg', 'N/A')}°"``
        (``agents/tools/weather_formatting.py``), so a missing bearing arrives
        as the literal ``"N/A°"``. Letter extraction used to read the leading
        "N" out of it and print North — a fabricated bearing on a card the user
        reads as fact. Anything that is not a bearing or a known compass code
        now renders blank.

        Args:
            direction: Raw provider value (degrees string, or a compass code).
            language: User language for the localized abbreviation.

        Returns:
            Localized compass abbreviation, or ``""`` when unreadable.
        """
        language = resolve_language(language)
        if not scalar_text(direction):
            return ""
        dir_str = str(direction).strip()

        # Bearing in degrees, with or without the degree sign.
        match = re.match(r"^(\d+\.?\d*)°?$", dir_str)
        if match:
            return self._angle_to_cardinal(float(match.group(1)), language)

        # Already a canonical compass code (what the briefing ships).
        code = dir_str.upper()
        if code in WIND_CARDINAL_CODES:
            return V3Messages.get_wind_cardinal(code, language)

        return ""

    def _angle_to_cardinal(self, angle: float, language: str | None = None) -> str:
        """Convert a bearing in degrees to its localized compass abbreviation."""
        code = wind_deg_to_cardinal(angle)
        return V3Messages.get_wind_cardinal(code, resolve_language(language)) if code else ""

    def _visual_for_reading(self, data: Mapping[str, object]) -> tuple[str, str]:
        """Use stable provider conditions, including its own day/night observation."""
        main = scalar_text(data.get("weather_main")).casefold()
        # OWM groups squalls and tornadoes under 50; Google WINDY also maps to
        # 50. The canonical main condition distinguishes them from fog/haze.
        if main == "squall":
            return Icons.WIND, "windy"
        if main == "tornado":
            return Icons.STORMY, "tornado"
        code = scalar_text(data.get("icon")).strip().lower()
        if re.fullmatch(r"\d{2}[dn]", code) and code[:2] in self.PROVIDER_ICONS:
            if code == "01n":
                return Icons.CLEAR_NIGHT, "clear-night"
            if code == "02n":
                return Icons.PARTLY_CLOUDY_NIGHT, "partly-cloudy-night"
            return self.PROVIDER_ICONS[code[:2]]
        if main in self.WEATHER_ICONS:
            return self.WEATHER_ICONS[main]
        return self._get_weather_visual(scalar_text(data.get("description")))

    def _get_weather_visual(self, description: str) -> tuple[str, str]:
        """Get icon name and CSS class for weather description."""
        if not description:
            return Icons.CLOUDY, "default"

        desc_lower = description.lower()

        # First try exact match
        if desc_lower in self.WEATHER_ICONS:
            return self.WEATHER_ICONS[desc_lower]

        # A compound legacy condition must keep its storm/snow signal even
        # when it also mentions rain. Provider-backed data uses codes above.
        if any(
            word in desc_lower for word in ("thunder", "orage", "lightning", "tornado", "hurricane")
        ):
            return Icons.STORMY, "stormy"
        if any(
            word in desc_lower
            for word in ("snow", "neige", "sleet", "freezing rain", "blizzard", "flurries")
        ):
            return Icons.SNOWY, "snowy"
        # Prefer a qualified condition (e.g. mostly cloudy) over a generic word.
        for key in sorted(self.WEATHER_ICONS, key=len, reverse=True):
            if key in desc_lower:
                return self.WEATHER_ICONS[key]

        # Default
        return Icons.CLOUDY, "default"

    def _get_uv_label(self, uv_index: Any, language: str) -> str:
        """Get human-readable UV index label."""
        if nonnegative_number(uv_index) is None:
            return ""
        try:
            uv = float(uv_index)
            if uv <= 2:
                return {
                    "fr": "Faible",
                    "en": "Low",
                    "es": "Bajo",
                    "de": "Niedrig",
                    "it": "Basso",
                    "zh-CN": "低",
                }.get(language, "Low")
            elif uv <= 5:
                return {
                    "fr": "Modéré",
                    "en": "Moderate",
                    "es": "Moderado",
                    "de": "Mäßig",
                    "it": "Moderato",
                    "zh-CN": "中等",
                }.get(language, "Moderate")
            elif uv <= 7:
                return {
                    "fr": "Élevé",
                    "en": "High",
                    "es": "Alto",
                    "de": "Hoch",
                    "it": "Alto",
                    "zh-CN": "高",
                }.get(language, "High")
            elif uv <= 10:
                return {
                    "fr": "Très élevé",
                    "en": "Very High",
                    "es": "Muy alto",
                    "de": "Sehr hoch",
                    "it": "Molto alto",
                    "zh-CN": "很高",
                }.get(language, "Very High")
            else:
                return {
                    "fr": "Extrême",
                    "en": "Extreme",
                    "es": "Extremo",
                    "de": "Extrem",
                    "it": "Estremo",
                    "zh-CN": "极端",
                }.get(language, "Extreme")
        except ValueError, TypeError:
            return ""

    def _pollen_row(self, data: dict[str, Any], language: str) -> str:
        """In-season pollen line (shared renderer)."""
        return pollen_text(data, language)

    def _environment_strip(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Compact air-quality/pollen strip for cards without a details section.

        The forecast and hourly layouts have no collapsible block, but the
        signal that decides an outdoor plan ("can I run tomorrow?") belongs
        there too — rendered inline, and only when the enrichment produced
        something.
        """
        rows = [
            self._air_quality_row(data, V3Messages.get_air_quality(ctx.language), ctx.language),
            self._pollen_row(data, ctx.language),
        ]
        items = "\n".join(render_d_item(Icons.WIND, row) for row in rows if row)
        if not items:
            return ""
        return f'<div class="lia-weather__environment">{items}</div>'

    def _air_quality_row(self, data: dict[str, Any], label: str, language: str) -> str:
        """Air-quality detail line (shared renderer + the legacy EPA table).

        ``_get_aqi_label`` stays the fallback for LEGACY numeric payloads that
        carry no provider category — the enrichment always ships one.
        """
        return air_quality_text(data, language, fallback_label=self._get_aqi_label)

    def _get_aqi_label(self, aqi: Any, language: str) -> str:
        """Get human-readable Air Quality Index label."""
        try:
            value = int(aqi)
            if value <= 50:
                return {
                    "fr": "Bon",
                    "en": "Good",
                    "es": "Bueno",
                    "de": "Gut",
                    "it": "Buono",
                    "zh-CN": "良好",
                }.get(language, "Good")
            elif value <= 100:
                return {
                    "fr": "Modéré",
                    "en": "Moderate",
                    "es": "Moderado",
                    "de": "Mäßig",
                    "it": "Moderato",
                    "zh-CN": "中等",
                }.get(language, "Moderate")
            elif value <= 150:
                return {
                    "fr": "Mauvais pour sensibles",
                    "en": "Unhealthy for Sensitive",
                    "es": "No saludable para sensibles",
                    "de": "Ungesund für Empfindliche",
                    "it": "Non salutare per sensibili",
                    "zh-CN": "对敏感人群不健康",
                }.get(language, "Unhealthy for Sensitive")
            elif value <= 200:
                return {
                    "fr": "Mauvais",
                    "en": "Unhealthy",
                    "es": "No saludable",
                    "de": "Ungesund",
                    "it": "Non salutare",
                    "zh-CN": "不健康",
                }.get(language, "Unhealthy")
            elif value <= 300:
                return {
                    "fr": "Très mauvais",
                    "en": "Very Unhealthy",
                    "es": "Muy no saludable",
                    "de": "Sehr ungesund",
                    "it": "Molto non salutare",
                    "zh-CN": "非常不健康",
                }.get(language, "Very Unhealthy")
            else:
                return {
                    "fr": "Dangereux",
                    "en": "Hazardous",
                    "es": "Peligroso",
                    "de": "Gefährlich",
                    "it": "Pericoloso",
                    "zh-CN": "危险",
                }.get(language, "Hazardous")
        except ValueError, TypeError:
            return ""
