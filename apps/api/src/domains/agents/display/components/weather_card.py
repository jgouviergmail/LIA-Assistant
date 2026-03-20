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

from typing import Any

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_WEATHER
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_full_date,
    format_time,
    render_collapsible,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon


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
        # Clear/Sunny conditions
        "clear": (Icons.SUNNY, "sunny"),
        "sunny": (Icons.SUNNY, "sunny"),
        "clear sky": (Icons.SUNNY, "sunny"),
        "fine": (Icons.SUNNY, "sunny"),
        "fair": (Icons.SUNNY, "sunny"),
        # Partly cloudy
        "partly cloudy": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "partly_cloudy": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "few clouds": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "scattered clouds": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "mostly sunny": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        "mostly clear": (Icons.PARTLY_CLOUDY, "partly-cloudy"),
        # Cloudy conditions
        "clouds": (Icons.CLOUDY, "cloudy"),
        "cloudy": (Icons.CLOUDY, "cloudy"),
        "broken clouds": (Icons.CLOUDY, "cloudy"),
        "overcast": (Icons.CLOUDY, "overcast"),
        "overcast clouds": (Icons.CLOUDY, "overcast"),
        "mostly cloudy": (Icons.CLOUDY, "cloudy"),
        # Rain conditions
        "rain": (Icons.RAINY, "rainy"),
        "light rain": (Icons.RAINY, "light-rain"),
        "moderate rain": (Icons.RAINY, "rainy"),
        "heavy rain": (Icons.RAINY, "heavy-rain"),
        "shower rain": (Icons.RAINY, "rainy"),
        "showers": (Icons.RAINY, "rainy"),
        "drizzle": (Icons.RAINY, "drizzle"),
        "light drizzle": (Icons.RAINY, "drizzle"),
        "patchy rain": (Icons.RAINY, "light-rain"),
        # Thunderstorm
        "thunderstorm": (Icons.STORMY, "stormy"),
        "thunder": (Icons.STORMY, "stormy"),
        "storm": (Icons.STORMY, "stormy"),
        "thundery": (Icons.STORMY, "stormy"),
        "lightning": (Icons.STORMY, "stormy"),
        # Snow conditions
        "snow": (Icons.SNOWY, "snowy"),
        "light snow": (Icons.SNOWY, "light-snow"),
        "heavy snow": (Icons.SNOWY, "heavy-snow"),
        "sleet": (Icons.SNOWY, "sleet"),
        "freezing rain": (Icons.SNOWY, "sleet"),
        "blizzard": (Icons.SNOWY, "blizzard"),
        "flurries": (Icons.SNOWY, "light-snow"),
        # Fog/Mist conditions
        "mist": (Icons.CLOUDY, "misty"),
        "fog": (Icons.CLOUDY, "foggy"),
        "haze": (Icons.CLOUDY, "hazy"),
        "smoke": (Icons.CLOUDY, "smoky"),
        "dust": (Icons.CLOUDY, "dusty"),
        "sand": (Icons.CLOUDY, "dusty"),
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

    def _render_current(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render current weather with all details."""
        location = self._get_location(data)
        # Support both current weather (temperature/temp) and forecast items (temp_day/temp_max)
        temp = self._format_temperature(
            data.get("temperature")
            or data.get("temp")
            or data.get("temp_day")
            or data.get("temp_max", "")
        )
        feels_like = self._format_temperature(data.get("feels_like", ""))
        description = data.get("description", "")
        humidity = data.get("humidity", "")
        wind = data.get("wind_speed", "")
        wind_dir = self._format_wind_direction(data.get("wind_direction", ""))

        # Extract and format date
        date_str = self._get_date(data, ctx)

        icon_name, weather_class = self._get_weather_visual(description)
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

        return f"""<div class="lia-card lia-weather lia-weather--{weather_class} {nested_class}">
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
</div>"""

    def _render_extended_details(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render collapsible section with extended weather details."""
        detail_sections = []

        # i18n labels
        uv_index_label = V3Messages.get_uv_index(ctx.language)
        pressure_label = V3Messages.get_pressure(ctx.language)
        visibility_label = V3Messages.get_visibility(ctx.language)
        cloud_cover_label = V3Messages.get_cloud_cover(ctx.language)
        air_quality_label = V3Messages.get_air_quality(ctx.language)
        precipitation_label = V3Messages.get_precipitation(ctx.language)

        # UV Index
        uv_index = data.get("uv_index") or data.get("uv", "")
        if uv_index:
            uv_level_label = self._get_uv_label(uv_index, ctx.language)
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.SUNNY)}"
                f"<span>{uv_index_label}: {escape_html(str(uv_index))} ({uv_level_label})</span>"
                f"</div>"
            )

        # Pressure
        pressure = data.get("pressure", "")
        if pressure:
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.PRESSURE)}"
                f"<span>{pressure_label}: {escape_html(str(pressure))}</span>"
                f"</div>"
            )

        # Visibility
        visibility = data.get("visibility", "")
        if visibility:
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.VISIBILITY)}"
                f"<span>{visibility_label}: {escape_html(str(visibility))}</span>"
                f"</div>"
            )

        # Cloud cover
        clouds = data.get("clouds") or data.get("cloud_cover", "")
        if clouds:
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.CLOUD_COVER)}"
                f"<span>{cloud_cover_label}: {escape_html(str(clouds))}%</span>"
                f"</div>"
            )

        # Sunrise/Sunset (locale-aware time formatting)
        sunrise = data.get("sunrise", "")
        sunset = data.get("sunset", "")
        if sunrise or sunset:
            sun_info = []
            if sunrise:
                sunrise_fmt = format_time(sunrise, ctx.language, ctx.timezone)
                sun_info.append(f"{icon(Icons.SUNRISE)} {escape_html(sunrise_fmt)}")
            if sunset:
                sunset_fmt = format_time(sunset, ctx.language, ctx.timezone)
                sun_info.append(f"{icon(Icons.SUNSET)} {escape_html(sunset_fmt)}")
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f'<span>{" · ".join(sun_info)}</span>'
                f"</div>"
            )

        # Air quality (if available)
        aqi = data.get("aqi") or data.get("air_quality", "")
        if aqi:
            aqi_level_label = self._get_aqi_label(aqi, ctx.language)
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.WIND)}"
                f"<span>{air_quality_label}: {escape_html(str(aqi))} ({aqi_level_label})</span>"
                f"</div>"
            )

        # Precipitation probability
        precip = data.get("precipitation_probability") or data.get("pop", "")
        if precip:
            detail_sections.append(
                f'<div class="lia-weather__detail-item">'
                f"{icon(Icons.RAINY)}"
                f"<span>{precipitation_label}: {escape_html(str(precip))}%</span>"
                f"</div>"
            )

        # If we have details, wrap in collapsible
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=f'<div class="lia-weather__extended">{content_html}</div>',
                initially_open=False,
                language=ctx.language,
            )

        return ""

    def _render_forecast(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render multi-day forecast as consolidated card."""
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return ""

        nested_class = self._nested_class(ctx)
        # Get location from parent data, fallback to first forecast item
        location = self._get_location(data) or self._get_location(forecasts[0])
        # Get date from first forecast item
        first_date = self._get_date(forecasts[0], ctx) if forecasts else ""

        days_html = []
        # Limit days (configurable via WEATHER_FORECAST_MAX_DAYS env var)
        max_days = settings.weather_forecast_max_days
        for day in forecasts[:max_days]:
            date = day.get("date_formatted") or day.get("date", "")
            day_name = date.split(",")[0] if "," in str(date) else str(date)[:3]

            # Handle temp as dict or direct values
            temp = day.get("temp", {})
            if isinstance(temp, dict):
                temp_max = self._format_temperature(temp.get("max", ""))
                temp_min = self._format_temperature(temp.get("min", ""))
            else:
                # Direct temp value (could be string or number)
                temp_max = self._format_temperature(
                    day.get("temp_max") or day.get("temperature_max") or temp
                )
                temp_min = self._format_temperature(
                    day.get("temp_min") or day.get("temperature_min", "")
                )

            desc = day.get("description", "")
            icon_name, weather_class = self._get_weather_visual(desc)

            days_html.append(f"""<div class="lia-weather__day lia-weather--{weather_class}">
<span class="lia-weather__day-name">{escape_html(day_name)}</span>
<span class="lia-weather__day-icon lia-weather__day-icon--color">{icon(icon_name, size="lg")}</span>
<div class="lia-weather__day-temps">
<span class="lia-weather__day-temp">{escape_html(temp_max)}</span>
<span class="lia-weather__day-temp-min">{escape_html(temp_min)}</span>
</div>
</div>""")

        V3Messages.get_forecast(ctx.language)

        # Same layout as current weather: date left, city right
        # CSS flex with justify-content: space-between handles alignment
        date_html = (
            f'<span class="lia-weather__date">{escape_html(first_date)}</span>'
            if first_date
            else ""
        )
        location_html = (
            f'<span class="lia-weather__city">{escape_html(location)}</span>' if location else ""
        )

        return f"""<div class="lia-card lia-weather lia-weather--forecast {nested_class}">
<div class="lia-weather__header-row">
{date_html}
{location_html}
</div>
<div class="lia-weather__forecast-days">
{chr(10).join(days_html)}
</div>
</div>"""

    def _render_hourly(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render hourly forecast with colored icons and responsive design."""
        hourly = data.get("hourly", [])
        if not hourly:
            return ""

        location = self._get_location(data)
        date_str = self._get_date(data, ctx)
        nested_class = self._nested_class(ctx)

        hours_html = []
        # Show all hours, CSS handles layout (horizontal scroll on mobile, grid on desktop)

        for hour in hourly:
            time = hour.get("datetime_text", "")
            if " " in time:
                time = time.split(" ")[1][:5]
            temp = self._format_temperature(hour.get("temp", ""))
            desc = hour.get("description", "")
            icon_name, weather_class = self._get_weather_visual(desc)

            hours_html.append(f"""<div class="lia-weather__hour lia-weather--{weather_class}">
<span class="lia-weather__hour-time">{escape_html(time)}</span>
<span class="lia-weather__hour-icon lia-weather__hour-icon--color">{icon(icon_name)}</span>
<span class="lia-weather__hour-temp">{escape_html(temp)}</span>
</div>""")

        # Unified layout for ALL viewports: icon + date (left), city (right)
        # No "hourly" label, no separator
        date_html = (
            f'{icon(Icons.SCHEDULE)} <span class="lia-weather__date">{escape_html(date_str)}</span>'
            if date_str
            else f"{icon(Icons.SCHEDULE)}"
        )
        # City only (not full address) - location already returns city from _get_location
        city_html = (
            f'<span class="lia-weather__city">{escape_html(location)}</span>' if location else ""
        )

        return f"""<div class="lia-card lia-weather lia-weather--hourly {nested_class}">
<div class="lia-weather__header-row">
<div class="lia-weather__header-left">{date_html}</div>
{city_html}
</div>
<div class="lia-weather__hourly-strip">
{chr(10).join(hours_html)}
</div>
</div>"""

    # Generic location names to filter out (not useful to display)
    GENERIC_LOCATIONS: frozenset[str] = frozenset(
        {
            "current location",
            "position actuelle",
            "ma position",
            "your location",
            "votre position",
            "ubicación actual",
            "aktuelle position",
            "posizione attuale",
        }
    )

    def _get_location(self, data: dict) -> str:
        """Extract location name from weather data, filtering generic names."""
        loc = data.get("location", {})
        if isinstance(loc, dict):
            # Prefer city/name
            city = loc.get("city") or loc.get("name") or loc.get("locality", "")
            if city and city.lower() not in self.GENERIC_LOCATIONS:
                return city  # type: ignore[no-any-return]
            # Fall back to address components
            region = loc.get("region", "") or loc.get("country", "")
            if region and region.lower() not in self.GENERIC_LOCATIONS:
                return region  # type: ignore[no-any-return]
            return ""
        # Handle string location
        if loc and str(loc).lower() not in self.GENERIC_LOCATIONS:
            return str(loc)
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
        if not temp:
            return ""

        # Handle dict temperatures (e.g., {'min': '-0.7°C', 'max': '1.2°C', 'avg': '-0.2°C'})
        if isinstance(temp, dict):
            # Prefer avg, then compute from min/max
            if "avg" in temp:
                return self._format_temperature(temp["avg"])
            elif "min" in temp and "max" in temp:
                # Compute average from min/max
                min_val = self._extract_numeric_temp(temp["min"])
                max_val = self._extract_numeric_temp(temp["max"])
                if min_val is not None and max_val is not None:
                    avg = (min_val + max_val) / 2
                    return f"{round(avg)}°C"
                # Fallback to max
                return self._format_temperature(temp["max"])
            elif "max" in temp:
                return self._format_temperature(temp["max"])
            elif "min" in temp:
                return self._format_temperature(temp["min"])
            return ""

        temp_str = str(temp)
        # Extract numeric part and round
        try:
            # Remove unit suffix if present (e.g., "12.5°C" -> "12.5")
            import re

            match = re.match(r"(-?\d+\.?\d*)", temp_str.replace(",", "."))
            if match:
                value = float(match.group(1))
                rounded = round(value)
                # Preserve unit if present
                unit = temp_str[len(match.group(0)) :].strip()
                return f"{rounded}{unit}" if unit else f"{rounded}°C"
        except (ValueError, TypeError):
            pass
        return temp_str

    def _extract_numeric_temp(self, temp_str: str) -> float | None:
        """Extract numeric value from temperature string."""
        if not temp_str:
            return None
        try:
            import re

            match = re.match(r"(-?\d+\.?\d*)", str(temp_str).replace(",", "."))
            if match:
                return float(match.group(1))
        except (ValueError, TypeError):
            pass
        return None

    def _format_wind_direction(self, direction: Any) -> str:
        """Format wind direction with cardinality (no angles)."""
        if not direction:
            return ""
        dir_str = str(direction)
        # If it's just degrees, convert to cardinal
        try:
            import re

            # Match angle pattern like "180°" or "180"
            match = re.match(r"^(\d+\.?\d*)°?$", dir_str.strip())
            if match:
                angle = float(match.group(1))
                return self._angle_to_cardinal(angle)
        except (ValueError, TypeError):
            pass
        # Already cardinal or mixed - extract just the letters
        import re

        cardinal_match = re.search(r"([NESWO]+)", dir_str.upper())
        if cardinal_match:
            return cardinal_match.group(1)
        return dir_str

    def _angle_to_cardinal(self, angle: float) -> str:
        """Convert angle in degrees to cardinal direction."""
        directions = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
        # Normalize angle to 0-360
        angle = angle % 360
        # Each direction covers 45 degrees, offset by 22.5
        index = int((angle + 22.5) / 45) % 8
        return directions[index]

    def _get_weather_visual(self, description: str) -> tuple[str, str]:
        """Get icon name and CSS class for weather description."""
        if not description:
            return Icons.PARTLY_CLOUDY, "default"

        desc_lower = description.lower()

        # First try exact match
        if desc_lower in self.WEATHER_ICONS:
            return self.WEATHER_ICONS[desc_lower]

        # Then try partial match
        for key, (icon_name, css_class) in self.WEATHER_ICONS.items():
            if key in desc_lower:
                return icon_name, css_class

        # Default
        return Icons.PARTLY_CLOUDY, "default"

    def _get_uv_label(self, uv_index: Any, language: str) -> str:
        """Get human-readable UV index label."""
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
        except (ValueError, TypeError):
            return ""

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
        except (ValueError, TypeError):
            return ""
