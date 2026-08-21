"""
LangChain v1 tools for Weather operations (OpenWeatherMap).

LOT 10: Weather API integration with current weather and forecast.

Note: Weather uses API key authentication (not OAuth).
User-specific API keys are retrieved from the database via ConnectorService.

API Reference:
- OpenWeatherMap Free Tier uses:
  - /data/2.5/weather for current weather
  - /data/2.5/forecast for 5-day/3-hour forecast
  - /geo/1.0/direct for geocoding

Architecture:
- Uses APIKeyConnectorTool base class for user-specific API key retrieval
- API keys stored encrypted in database per user
- Falls back to error message if user hasn't configured connector
"""

import re
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import _
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import AGENT_QUERY, AGENT_WEATHER, CONTEXT_DOMAIN_WEATHER
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.base import APIKeyConnectorTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.weather_environment_enrichment import (
    attach_environment_extras,
    environment_payload_fields,
)
from src.domains.agents.tools.weather_formatting import (
    _entry_local_date,
    _extract_location_from_geocode,
    _format_current_weather_response,
    _format_forecast_response,
    _format_hourly_response,
)
from src.domains.connectors.clients.google_geocoding_helpers import forward_geocode
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# TEMPORAL REFERENCE PARSING
# ============================================================================


def _get_today_in_timezone(user_timezone: str) -> datetime:
    """
    Get current datetime in user's timezone.

    Args:
        user_timezone: User's IANA timezone (e.g., "Europe/Paris")

    Returns:
        Current datetime in user's timezone (timezone-aware)
    """
    try:
        tz = ZoneInfo(user_timezone)
    except KeyError, ValueError:
        tz = UTC
    return datetime.now(tz)


# Month name mappings for localized date parsing (FR, EN, DE, ES, IT)
_MONTH_NAMES: dict[str, int] = {
    # French
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    # English
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    # German
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "marz": 3,
    "juni": 6,
    "juli": 7,
    "oktober": 10,
    "dezember": 12,
    # Spanish
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # Italian
    "gennaio": 1,
    "febbraio": 2,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "settembre": 9,
    "ottobre": 10,
    "dicembre": 12,
}

# Pattern: optional day-of-week, then DD month YYYY (e.g., "jeudi 09 avril 2026", "9 avril 2026")
_LOCALIZED_DATE_PATTERN = re.compile(r"(?:\w+\s+)?(\d{1,2})\s+(\w+)\s+(\d{4})", re.IGNORECASE)


def _parse_localized_date(ref: str) -> date | None:
    """Parse localized date strings like 'jeudi 09 avril 2026' or '9 April 2026'.

    Supports French, English, German, Spanish, and Italian month names.

    Args:
        ref: Date string to parse.

    Returns:
        Parsed date or None if not recognized.
    """
    match = _LOCALIZED_DATE_PATTERN.match(ref.strip())
    if not match:
        return None

    day_str, month_str, year_str = match.groups()
    month = _MONTH_NAMES.get(month_str.lower())
    if month is None:
        return None

    try:
        return date(int(year_str), month, int(day_str))
    except ValueError:
        return None


def _calculate_target_date(
    date_ref: str | None,
    user_timezone: str,
) -> tuple[str, int, bool]:
    """
    Calculate target date from temporal reference in user's timezone.

    Calculate target date from temporal reference in user's timezone.

    Queries are translated to English by the semantic pivot before reaching the
    planner, so temporal references are expected in English. Localized date
    strings (e.g., "jeudi 09 avril 2026") from planner output are handled as
    a fallback via _parse_localized_date().

    Args:
        date_ref: Temporal reference (e.g., "tomorrow", "2026-01-27", "2026-01-27T11:30:00+01:00",
                  or localized like "jeudi 09 avril 2026")
        user_timezone: User's IANA timezone (e.g., "Europe/Paris")

    Returns:
        Tuple of:
        - target_date: Date string in YYYY-MM-DD format
        - offset: Number of days from today (for API request sizing)
        - is_specific_date: True if user asked for a specific date (not a range like "this week")
    """
    from src.core.time_utils import parse_datetime

    today_user = _get_today_in_timezone(user_timezone)
    today_date = today_user.date()

    if not date_ref:
        return today_date.isoformat(), 0, False

    ref = date_ref.strip()
    ref_lower = ref.lower()

    # Try parsing as ISO date/datetime using shared utility
    # Handles: "2026-01-22", "2026-01-22T14:00:00+01:00", "2026-01-22T14:00:00Z"
    parsed_dt = parse_datetime(ref)
    if parsed_dt is not None:
        # Convert to user's timezone to get correct date
        try:
            tz = ZoneInfo(user_timezone)
            parsed_local = parsed_dt.astimezone(tz)
        except KeyError, ValueError:
            parsed_local = parsed_dt.astimezone(UTC)

        target_date = parsed_local.date()
        offset = max(0, (target_date - today_date).days)
        # ISO date/datetime is always a specific date request
        return target_date.isoformat(), offset, True

    # Today references (English — queries are translated by semantic pivot)
    if ref_lower in ("today", "now"):
        return today_date.isoformat(), 0, True

    # Tomorrow references
    if ref_lower == "tomorrow":
        target = today_date + timedelta(days=1)
        return target.isoformat(), 1, True

    # Day after tomorrow references
    if ref_lower in ("after tomorrow", "day after tomorrow"):
        target = today_date + timedelta(days=2)
        return target.isoformat(), 2, True

    # "in X days" pattern
    days_match = re.search(r"in\s+(\d+)\s+days?", ref_lower)
    if days_match:
        days = int(days_match.group(1))
        target = today_date + timedelta(days=days)
        return target.isoformat(), days, True

    # Week references - return today, NOT specific (show full week)
    if any(w in ref_lower for w in ("week", "this week")):
        return today_date.isoformat(), 0, False

    # Localized date strings: "jeudi 09 avril 2026", "9 avril 2026", "April 9, 2026", etc.
    # The planner may output dates in the user's language instead of ISO format.
    parsed_localized = _parse_localized_date(ref)
    if parsed_localized is not None:
        offset = max(0, (parsed_localized - today_date).days)
        return parsed_localized.isoformat(), offset, True

    # Default: today, not specific
    return today_date.isoformat(), 0, False


# Legacy function for backward compatibility
def _parse_date_offset(
    date_ref: str | None, user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE
) -> int:
    """
    Parse temporal reference and return offset in days from today.

    DEPRECATED: Use _calculate_target_date() instead for proper timezone handling.

    Args:
        date_ref: Temporal reference or ISO date/datetime
        user_timezone: User's timezone for "today" calculation

    Returns:
        Number of days offset from today (0 = today, 1 = tomorrow, etc.)
    """
    _, offset, _ = _calculate_target_date(date_ref, user_timezone)
    return offset


async def _geocode_with_city_fallback(
    client: OpenWeatherMapClient,
    location: str,
) -> tuple[float, float, str, str] | None:
    """
    Geocode a location with Google Geocoding API fallback.

    First attempts geocoding with OpenWeatherMap (free, included in API).
    If that fails, falls back to Google Geocoding API which handles
    all international address formats reliably.

    This handles cases where calendar events contain full addresses
    like "149 Rue de Sèvres, 75015 Paris, France" or international
    formats like "221B Baker Street, London W1U 6RS, UK".

    Args:
        client: OpenWeatherMap API client
        location: Location string (address or city name)

    Returns:
        Tuple of (lat, lon, resolved_name, country) if geocoding succeeds,
        None if both attempts fail.
    """
    # First attempt: OpenWeatherMap geocoding (free, handles simple city names)
    geocode_results = await client.geocode(location)
    coords = _extract_location_from_geocode(geocode_results)

    if coords:
        return coords

    # Fallback: Google Geocoding API (handles all international address formats)
    logger.debug(
        "geocode_fallback_to_google",
        original_location=location[:50],
    )
    coords = await forward_geocode(location)

    return coords


# ============================================================================
# WEATHER CONTEXT TYPE REGISTRATION
# ============================================================================


class WeatherForecastItem(BaseModel):
    """Schema for weather data in context registry."""

    location: Any  # Location name or dict
    date: str | None = None  # Forecast date
    description: str | None = None  # Weather description
    temperature: str | None = None  # Current temp
    temp_min: str | None = None  # Minimum temperature
    temp_max: str | None = None  # Maximum temperature
    humidity: str | None = None  # Humidity percentage
    wind_speed: str | None = None  # Wind speed
    wind_direction: str | None = None  # Wind direction
    pressure: str | None = None  # Pressure
    visibility: str | None = None  # Visibility
    clouds: str | None = None  # Cloud coverage
    sunrise: str | None = None  # Sunrise time
    sunset: str | None = None  # Sunset time
    feels_like: str | None = None  # Feels like temp
    type: str | None = None  # 'current', 'forecast', 'hourly'
    temp: Any | None = None  # Forecast temp dict
    hourly: list[Any] | None = None  # Hourly forecast list


# Register weather context type for Data Registry support
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_WEATHER,
        agent_name=AGENT_WEATHER,
        item_schema=WeatherForecastItem,
        primary_id_field="date",
        display_name_field="location",
        reference_fields=[
            "location",
            "description",
            "date",
        ],
        icon="🌤️",
    )
)


# ============================================================================
# WEATHER TOOL IMPLEMENTATION CLASSES
# ============================================================================


class GetCurrentWeatherTool(APIKeyConnectorTool[OpenWeatherMapClient]):
    """Tool for getting current weather using user's OpenWeatherMap API key."""

    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = OpenWeatherMapClient
    # Lot E (2026-08): the active weather provider is resolved per call —
    # OpenWeatherMap (user key) or Google Weather (platform key), both
    # normalized to the same OWM shape at the client boundary.
    functional_category = "weather"
    registry_enabled = True  # Enable Data Registry mode

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> OpenWeatherMapClient:
        """Create OpenWeatherMap client with user's API key."""
        return OpenWeatherMapClient(
            api_key=credentials.api_key,
            user_id=user_id,
        )

    async def execute_api_call(
        self,
        client: OpenWeatherMapClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute current weather API call."""
        from src.domains.agents.tools.location_resolution import resolve_location
        from src.domains.agents.tools.runtime_helpers import (
            get_original_user_message,
            get_user_preferences,
        )

        location = kwargs.get("location")
        units = kwargs.get("units", "metric")
        language = kwargs.get("language", settings.default_language)
        runtime = kwargs.get("runtime")  # InjectedToolArg from parallel_executor

        # Get user_message from parameter or fallback to runtime config
        user_message = kwargs.get("user_message", "")
        if not user_message and runtime:
            user_message = get_original_user_message(runtime)

        # Get user timezone for sunrise/sunset formatting.
        # User's language preference takes precedence over kwargs default so that
        # translated error messages (via _()) match the user's locale.
        user_timezone = "UTC"
        # Use default
        with suppress(Exception):
            if runtime:
                user_timezone, user_lang, _locale = await get_user_preferences(runtime)
                if user_lang:
                    language = user_lang

        lat: float | None = None
        lon: float | None = None
        resolved_name: str = ""
        country: str = ""

        # Auto-detect location when not explicitly provided
        # resolve_location() uses i18n_location.detect_location_type() for i18n phrase detection
        if not location or location.lower() == "auto":
            resolved, fallback_msg = await resolve_location(runtime, user_message, language)
            if resolved:
                lat = resolved.lat
                lon = resolved.lon
                resolved_name = resolved.address or ""  # Empty triggers API city name substitution
                country = ""  # Not available from browser geolocation
                logger.info(
                    "weather_location_auto_resolved",
                    source=resolved.source,
                    lat=lat,
                    lon=lon,
                )
            elif fallback_msg:
                # No location available, return fallback message
                return {
                    "success": False,
                    "error": "location_required",
                    "message": fallback_msg,
                }

        # If not auto-resolved, geocode the explicit location
        if lat is None or lon is None:
            if not location:
                return {
                    "success": False,
                    "error": "location_required",
                    "message": _("Please specify a city or enable geolocation.", language),
                }

            coords = await _geocode_with_city_fallback(client, location)
            if not coords:
                return {
                    "success": False,
                    "error": "location_not_found",
                    "message": _("Unable to find location: {location}", language).format(
                        location=location
                    ),
                }

            lat, lon, resolved_name, country = coords

        # Get current weather
        weather = await client.get_current_weather(
            lat=lat,
            lon=lon,
            units=units,
            lang=language,
        )

        # Format response with user's timezone. The language rides along in the
        # result so the sync formatter can localize its summary (tool instances
        # are singletons — never stash per-request state on self).
        formatted = _format_current_weather_response(
            weather, resolved_name, country, lat, lon, units, user_timezone
        )
        formatted[self._LANGUAGE_RESULT_KEY] = language
        # AQ/pollen enrichment (2026-08): active Google Environment connector
        # ⇒ the answer also carries air quality + in-season pollen. Fail-quiet.
        await attach_environment_extras(formatted, runtime, user_id, lat, lon, language)
        return formatted

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format current weather as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Weather request failed"),
                error_code="weather_api_error",
                metadata={"status": "error", "error": result.get("error")},
            )

        data = result.get("data", {})
        location_info = data.get("location", {})
        weather_info = data.get("weather", {})
        wind_info = weather_info.get("wind", {})

        # Build location string
        location_str = f"{location_info.get('name', 'Unknown')}"
        if location_info.get("country"):
            location_str += f", {location_info['country']}"

        # Create registry item for current weather
        item_id = generate_registry_id(
            RegistryItemType.WEATHER,
            f"current_{location_info.get('name', 'unknown')}_{datetime.now(UTC).strftime('%Y%m%d')}",
        )

        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.WEATHER,
            payload={
                "location": location_info,
                "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "temperature": weather_info.get("temperature"),
                "description": weather_info.get("description"),
                "humidity": weather_info.get("humidity"),
                "wind_speed": wind_info.get("speed"),
                "wind_direction": wind_info.get("direction"),
                "pressure": weather_info.get("pressure"),
                "visibility": weather_info.get("visibility"),
                "clouds": weather_info.get("clouds"),
                "sunrise": weather_info.get("sunrise"),
                "sunset": weather_info.get("sunset"),
                "temp_min": weather_info.get("temp_min"),
                "temp_max": weather_info.get("temp_max"),
                "feels_like": weather_info.get("feels_like"),
                "type": "current",
                **environment_payload_fields(data),
            },
            meta=RegistryItemMeta(
                source="openweathermap",
                domain=CONTEXT_DOMAIN_WEATHER,
                tool_name="get_current_weather",
            ),
        )

        # Build summary for LLM (localized: the model reads and may quote it)
        summary = V3Messages.get_weather_summary_current(
            self._language_from_result(result),
            location=location_str,
            description=str(weather_info.get("description", "N/A")),
            temperature=str(weather_info.get("temperature", "N/A")),
            feels_like=str(weather_info.get("feels_like", "N/A")),
            temp_min=str(weather_info.get("temp_min", "N/A")),
            temp_max=str(weather_info.get("temp_max", "N/A")),
            wind_speed=str(wind_info.get("speed", "N/A")),
            wind_direction=str(wind_info.get("direction", "N/A")),
            humidity=str(weather_info.get("humidity", "N/A")),
            pressure=str(weather_info.get("pressure", "N/A")),
            visibility=str(weather_info.get("visibility", "N/A")),
            clouds=str(weather_info.get("clouds", "N/A")),
            sunrise=str(weather_info.get("sunrise", "N/A")),
            sunset=str(weather_info.get("sunset", "N/A")),
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={"location": location_str, "type": "current"},
        )


class GetWeatherForecastTool(APIKeyConnectorTool[OpenWeatherMapClient]):
    """Tool for getting weather forecast using user's OpenWeatherMap API key."""

    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = OpenWeatherMapClient
    # Lot E (2026-08): the active weather provider is resolved per call —
    # OpenWeatherMap (user key) or Google Weather (platform key), both
    # normalized to the same OWM shape at the client boundary.
    functional_category = "weather"
    registry_enabled = True  # Enable Data Registry mode

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> OpenWeatherMapClient:
        """Create OpenWeatherMap client with user's API key."""
        return OpenWeatherMapClient(
            api_key=credentials.api_key,
            user_id=user_id,
        )

    async def execute_api_call(
        self,
        client: OpenWeatherMapClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute weather forecast API call."""
        from src.core.config import get_settings
        from src.domains.agents.tools.location_resolution import resolve_location
        from src.domains.agents.tools.runtime_helpers import (
            get_original_user_message,
            get_user_preferences,
        )

        # Get configurable forecast limit from settings
        max_forecast_days = get_settings().weather_forecast_max_days

        location = kwargs.get("location")
        days = kwargs.get("days", max_forecast_days)
        units = kwargs.get("units", "metric")
        language = kwargs.get("language", settings.default_language)
        date_ref = kwargs.get("date")  # Temporal reference (e.g., "demain", "tomorrow")
        runtime = kwargs.get("runtime")  # InjectedToolArg from parallel_executor

        # Get user_message from parameter or fallback to runtime config
        user_message = kwargs.get("user_message", "")
        if not user_message and runtime:
            user_message = get_original_user_message(runtime)

        # Get user timezone and language preferences
        user_timezone = "UTC"
        try:
            if runtime:
                user_timezone, user_lang, _locale = await get_user_preferences(runtime)
                if user_lang:
                    language = user_lang
        except Exception as e:
            logger.debug("user_preferences_fallback", error=str(e))

        # Calculate target date from temporal reference in user's timezone
        # Returns: (target_date: str "YYYY-MM-DD", offset: int, is_specific_date: bool)
        target_date, date_offset, is_specific_date = _calculate_target_date(date_ref, user_timezone)

        # For specific date requests (demain, ISO datetime), reduce days to 1
        # When user asks "weather tomorrow" or "weather for my appointment", they want that day only
        if is_specific_date and days == max_forecast_days:
            days = 1  # Override default 5 days to 1 day for specific date requests
            logger.debug(
                "forecast_days_reduced_for_specific_date",
                date_ref=date_ref,
                target_date=target_date,
                original_days=max_forecast_days,
                new_days=days,
            )

        logger.debug(
            "forecast_date_calculation",
            date_ref=date_ref,
            target_date=target_date,
            offset=date_offset,
            days=days,
            user_timezone=user_timezone,
        )

        # Check if date is beyond forecast availability
        if date_offset > max_forecast_days:
            return {
                "success": False,
                "error": "date_beyond_forecast",
                "message": V3Messages.get_forecast_beyond_limit(
                    language, max_forecast_days, date_offset
                ),
            }

        lat: float | None = None
        lon: float | None = None
        resolved_name: str = ""
        country: str = ""

        # Auto-detect location when not explicitly provided
        # resolve_location() uses i18n_location.detect_location_type() for i18n phrase detection
        if not location or location.lower() == "auto":
            resolved, fallback_msg = await resolve_location(runtime, user_message, language)
            if resolved:
                lat = resolved.lat
                lon = resolved.lon
                resolved_name = resolved.address or ""  # Empty triggers API city name substitution
                country = ""
                logger.info(
                    "forecast_location_auto_resolved",
                    source=resolved.source,
                    lat=lat,
                    lon=lon,
                )
            elif fallback_msg:
                return {
                    "success": False,
                    "error": "location_required",
                    "message": fallback_msg,
                }

        # If not auto-resolved, geocode the explicit location
        if lat is None or lon is None:
            if not location:
                return {
                    "success": False,
                    "error": "location_required",
                    "message": _("Please specify a city or enable geolocation.", language),
                }

            coords = await _geocode_with_city_fallback(client, location)
            if not coords:
                return {
                    "success": False,
                    "error": "location_not_found",
                    "message": _("Unable to find location: {location}", language).format(
                        location=location
                    ),
                }

            lat, lon, resolved_name, country = coords

        # Get daily forecast - request enough days to cover offset + requested days
        # Free tier has max N days, so cap total at limit
        total_days_needed = min(date_offset + days, max_forecast_days)
        forecast_result = await client.get_daily_forecast(
            lat=lat,
            lon=lon,
            days=total_days_needed,
            units=units,
            lang=language,
            user_timezone=user_timezone,  # Group data by user's local dates
        )

        # Extract daily data and city info
        daily_data = forecast_result.get("daily", [])
        city_info = forecast_result.get("city", {})

        # Use city name from API if resolved_name is empty (auto-resolved without address)
        if not resolved_name:
            api_city = city_info.get("name", "")
            if api_city:
                resolved_name = api_city
        if not country:
            country = city_info.get("country", "")

        # Format response filtering by target date (not by index offset)
        # This correctly handles cases where API data starts later than today
        formatted = _format_forecast_response(
            daily_data, resolved_name, country, days, units, target_date
        )
        formatted[self._LANGUAGE_RESULT_KEY] = language
        # Same enrichment as current weather: "can I run tomorrow?" is decided
        # by air quality and pollen. Cached per point, so asking weather then
        # forecast costs one fetch, not two.
        await attach_environment_extras(formatted, runtime, user_id, lat, lon, language)
        return formatted

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format weather forecast as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Weather forecast request failed"),
                error_code="weather_forecast_error",
                metadata={"status": "error", "error": result.get("error")},
            )

        data = result.get("data", {})
        location_info = data.get("location", {})
        daily_forecasts = data.get("daily", [])

        # Build location string
        location_str = f"{location_info.get('name', 'Unknown')}"
        if location_info.get("country"):
            location_str += f", {location_info['country']}"

        # Create registry items for each forecast day
        registry_updates: dict[str, RegistryItem] = {}
        forecast_summaries = []

        for idx, day in enumerate(daily_forecasts):
            date_str = day.get("date", f"day_{idx}")
            # _format_forecast_response wraps temps in a dict: {"min": "5°C", "max": "12°C", "avg": "8°C"}
            temp_info = day.get("temp", {})

            item_id = generate_registry_id(
                RegistryItemType.WEATHER,
                f"forecast_{location_info.get('name', 'unknown')}_{date_str}",
            )

            registry_item = RegistryItem(
                id=item_id,
                type=RegistryItemType.WEATHER,
                payload={
                    "location": location_info,
                    "date": date_str,
                    # Extract from temp dict (already formatted with units like "5°C")
                    "temp_min": temp_info.get("min", "N/A"),
                    "temp_max": temp_info.get("max", "N/A"),
                    "temp_day": temp_info.get("avg", "N/A"),
                    "description": day.get("description", "N/A"),
                    "humidity": day.get("humidity", "N/A"),
                    "wind_speed": day.get("wind_speed", "N/A"),
                    "type": "forecast",
                    # Today's air quality / pollen ride on the FIRST day only:
                    # both are same-day signals, and repeating them on every
                    # day would state a measurement the API never made.
                    **(environment_payload_fields(data) if idx == 0 else {}),
                },
                meta=RegistryItemMeta(
                    source="openweathermap",
                    domain=CONTEXT_DOMAIN_WEATHER,
                    tool_name="get_weather_forecast",
                ),
            )
            registry_updates[item_id] = registry_item

            # Build day summary (ISO date for LLM, display formatting is done by cards)
            forecast_summaries.append(
                f"{date_str}: {day.get('description', 'N/A')}, "
                f"{temp_info.get('min', 'N/A')}/{temp_info.get('max', 'N/A')}"
            )

        # Build overall summary for LLM (localized: the model reads and may quote it)
        summary = V3Messages.get_weather_summary_forecast(
            self._language_from_result(result), location_str, len(daily_forecasts)
        )
        summary += "\n" + "\n".join(f"- {s}" for s in forecast_summaries)

        # Expose forecasts via structured_data so downstream skill scripts
        # can consume them through $steps.<step_id>.forecasts references
        # inside a deterministic plan_template (B1 hybrid skills).
        structured_forecasts = [
            {
                "date": day.get("date"),
                "description": day.get("description"),
                "temp_min": day.get("temp", {}).get("min"),
                "temp_max": day.get("temp", {}).get("max"),
                "temp_avg": day.get("temp", {}).get("avg"),
                "humidity": day.get("humidity"),
                "wind_speed": day.get("wind_speed"),
            }
            for day in daily_forecasts
        ]

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            structured_data={
                "location": {
                    "name": location_info.get("name"),
                    "country": location_info.get("country"),
                    "display": location_str,
                },
                "forecasts": structured_forecasts,
                "days": len(daily_forecasts),
            },
            metadata={
                "location": location_str,
                "type": "forecast",
                "days": len(daily_forecasts),
            },
        )


class GetHourlyForecastTool(APIKeyConnectorTool[OpenWeatherMapClient]):
    """Tool for getting hourly forecast using user's OpenWeatherMap API key."""

    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = OpenWeatherMapClient
    # Lot E (2026-08): the active weather provider is resolved per call —
    # OpenWeatherMap (user key) or Google Weather (platform key), both
    # normalized to the same OWM shape at the client boundary.
    functional_category = "weather"
    registry_enabled = True  # Enable Data Registry mode

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> OpenWeatherMapClient:
        """Create OpenWeatherMap client with user's API key."""
        return OpenWeatherMapClient(
            api_key=credentials.api_key,
            user_id=user_id,
        )

    async def execute_api_call(
        self,
        client: OpenWeatherMapClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute hourly forecast API call."""
        from src.core.config import get_settings
        from src.domains.agents.tools.location_resolution import resolve_location
        from src.domains.agents.tools.runtime_helpers import (
            get_original_user_message,
            get_user_preferences,
        )

        # Get configurable forecast limit from settings
        max_forecast_days = get_settings().weather_forecast_max_days

        location = kwargs.get("location")
        hours = kwargs.get("hours", 24)
        units = kwargs.get("units", "metric")
        language = kwargs.get("language", settings.default_language)
        date_ref = kwargs.get("date")  # Temporal reference (e.g., "tomorrow", ISO datetime)
        runtime = kwargs.get("runtime")  # InjectedToolArg from parallel_executor

        # Get user_message from parameter or fallback to runtime config
        user_message = kwargs.get("user_message", "")
        if not user_message and runtime:
            user_message = get_original_user_message(runtime)

        # Get user timezone and language preferences. Timezone is required to map
        # a requested day (and each 3-hour slot) to the user's local calendar date.
        user_timezone = "UTC"
        try:
            if runtime:
                user_timezone, user_lang, _locale = await get_user_preferences(runtime)
                if user_lang:
                    language = user_lang
        except Exception as e:
            logger.debug("user_preferences_fallback", error=str(e))

        # Resolve the requested target day in the user's timezone. When a specific
        # day is asked (e.g. "tomorrow", "2026-07-25", or a calendar ISO datetime),
        # the forecast is filtered to that day's 3-hour slots instead of returning a
        # rolling window from now. Mirrors the daily tool (single source of truth).
        target_date, date_offset, is_specific_date = _calculate_target_date(date_ref, user_timezone)

        # Fail honestly when the requested day is beyond the free-tier window, rather
        # than silently returning near-term slots (which reads to the LLM as "no data").
        if date_offset > max_forecast_days:
            return {
                "success": False,
                "error": "date_beyond_forecast",
                "message": V3Messages.get_forecast_beyond_limit(
                    language, max_forecast_days, date_offset
                ),
            }

        lat: float | None = None
        lon: float | None = None
        resolved_name: str = ""
        country: str = ""

        # Auto-detect location when not explicitly provided
        # resolve_location() uses i18n_location.detect_location_type() for i18n phrase detection
        if not location or location.lower() == "auto":
            resolved, fallback_msg = await resolve_location(runtime, user_message, language)
            if resolved:
                lat = resolved.lat
                lon = resolved.lon
                resolved_name = resolved.address or ""  # Empty triggers API city name substitution
                country = ""
                logger.info(
                    "hourly_location_auto_resolved",
                    source=resolved.source,
                    lat=lat,
                    lon=lon,
                )
            elif fallback_msg:
                return {
                    "success": False,
                    "error": "location_required",
                    "message": fallback_msg,
                }

        # If not auto-resolved, geocode the explicit location
        if lat is None or lon is None:
            if not location:
                return {
                    "success": False,
                    "error": "location_required",
                    "message": _("Please specify a city or enable geolocation.", language),
                }

            coords = await _geocode_with_city_fallback(client, location)
            if not coords:
                return {
                    "success": False,
                    "error": "location_not_found",
                    "message": _("Unable to find location: {location}", language).format(
                        location=location
                    ),
                }

            lat, lon, resolved_name, country = coords

        # Get 3-hour forecast (free tier limit: 8 intervals/day * max_days).
        max_entries = max_forecast_days * 8  # 8 x 3-hour intervals per day
        if is_specific_date:
            # Fetch enough 3-hour entries to fully cover the target day. The +2 days
            # of slots absorb the UTC<->local boundary (a local day spans two UTC
            # days) so the filter never drops a slot; capped at the 5-day window.
            entries_needed = min((date_offset + 2) * 8, max_entries)
        else:
            entries_needed = min(hours // 3 + 1, max_entries)

        forecast_data = await client.get_forecast(
            lat=lat,
            lon=lon,
            units=units,
            lang=language,
            cnt=entries_needed,
        )

        # Format response. For a specific-day request, filter to that day's slots
        # (in the user's timezone); otherwise keep the rolling near-term window.
        formatted = _format_hourly_response(
            forecast_data,
            resolved_name,
            country,
            entries_needed,
            units,
            target_date=target_date if is_specific_date else None,
            user_timezone=user_timezone,
        )

        # Contract: a specific day was asked for but no slot matched (window edge,
        # lowered WEATHER_FORECAST_MAX_DAYS, far-offset timezone). Returning an
        # empty success is indistinguishable from "no data" for the response LLM
        # and reproduces the very symptom this tool is meant to fix — fail loudly
        # with a localized message instead.
        if is_specific_date and not formatted.get("data", {}).get("hourly"):
            logger.info(
                "hourly_forecast_no_slots_for_target_date",
                target_date=target_date,
                date_offset=date_offset,
                entries_requested=entries_needed,
                entries_returned=len(forecast_data.get("list", [])),
                user_timezone=user_timezone,
            )
            return {
                "success": False,
                "error": "no_slots_for_date",
                "message": V3Messages.get_weather_no_slots_for_date(language, target_date),
            }

        # The day actually covered by the returned slots: the requested one, or
        # (rolling window) the day the first slot falls on in the user's timezone.
        # Without it the registry item was stamped "today" even for a future day.
        covered_date = target_date
        if not is_specific_date:
            first_slot = next(iter(forecast_data.get("list", [])), None)
            if first_slot:
                covered_date = _entry_local_date(first_slot, user_timezone) or target_date
        formatted["data"]["date"] = covered_date
        formatted[self._LANGUAGE_RESULT_KEY] = language
        return formatted

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format hourly forecast as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Hourly forecast request failed"),
                error_code="hourly_forecast_error",
                metadata={"status": "error", "error": result.get("error")},
            )

        data = result.get("data", {})
        location_info = data.get("location", {})
        hourly_forecasts = data.get("hourly", [])

        # Build location string
        location_str = f"{location_info.get('name', 'Unknown')}"
        if location_info.get("country"):
            location_str += f", {location_info['country']}"

        # Day actually covered by the slots (set by execute_api_call): the
        # requested day for a targeted request, else the first slot's local day.
        # Stamping "today" here mislabelled every future-day request.
        covered_date = str(data.get("date") or datetime.now(UTC).strftime("%Y-%m-%d"))

        # Create single registry item for hourly forecast (grouped)
        item_id = generate_registry_id(
            RegistryItemType.WEATHER,
            f"hourly_{location_info.get('name', 'unknown')}_{covered_date}",
        )

        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.WEATHER,
            payload={
                "location": location_info,
                "date": covered_date,
                "interval": data.get("interval", "3 hours"),
                "hourly": hourly_forecasts,
                "type": "hourly",
            },
            meta=RegistryItemMeta(
                source="openweathermap",
                domain=CONTEXT_DOMAIN_WEATHER,
                tool_name="get_hourly_forecast",
            ),
        )

        # Build summary showing first few hours
        preview_hours = hourly_forecasts[:4] if len(hourly_forecasts) > 4 else hourly_forecasts
        # HH:MM of the LOCAL wall clock (datetime_text is already localized by
        # _format_hourly_response); same slicing as the weather card so the text
        # the LLM quotes and the card the user sees cannot diverge.
        hour_summaries = [
            f"{h.get('datetime_text', '').split(' ')[-1][:5] or 'N/A'}: "
            f"{h.get('temp', 'N/A')}, {h.get('description', 'N/A')}"
            for h in preview_hours
        ]

        language = self._language_from_result(result)
        summary = V3Messages.get_weather_summary_hourly(
            language, location_str, covered_date, len(hourly_forecasts)
        )
        summary += "\n" + "\n".join(f"- {s}" for s in hour_summaries)
        if len(hourly_forecasts) > 4:
            summary += "\n- " + V3Messages.get_weather_summary_hourly_more(
                language, len(hourly_forecasts) - 4
            )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={
                "location": location_str,
                "type": "hourly",
                "entries": len(hourly_forecasts),
            },
        )


# ============================================================================
# TOOL INSTANCES (singletons - stateless, credentials fetched per request)
# ============================================================================

_get_current_weather_tool_impl = GetCurrentWeatherTool(
    tool_name="get_current_weather",
    operation="current_weather",
)

_get_weather_forecast_tool_impl = GetWeatherForecastTool(
    tool_name="get_weather_forecast",
    operation="daily_forecast",
)

_get_hourly_forecast_tool_impl = GetHourlyForecastTool(
    tool_name="get_hourly_forecast",
    operation="hourly_forecast",
)


# ============================================================================
# TOOL 1: GET CURRENT WEATHER
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_current_weather",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_current_weather_tool(
    location: Annotated[
        str | None,
        "City name (e.g., 'Paris', 'New York') or 'auto' for automatic geolocation",
    ] = None,
    user_message: Annotated[
        str,
        "Original user message (for location phrase detection like 'chez moi', 'nearby')",
    ] = "",
    date: Annotated[
        str | None,
        "Date reference (e.g., 'today', 'now') - ignored, always returns current weather",
    ] = None,
    units: Annotated[
        str, "Temperature units: 'metric' (Celsius) or 'imperial' (Fahrenheit)"
    ] = "metric",
    language: Annotated[
        str, "Language code for weather description (e.g., 'fr', 'en', 'es')"
    ] = "fr",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> str:
    """
    Get current weather for a location.

    Provides:
    - Temperature (current, feels like, min, max)
    - Weather conditions (clear, cloudy, rain, snow, etc.)
    - Humidity, pressure, visibility
    - Wind speed and direction
    - Sunrise/sunset times

    Args:
        location: City name (e.g., 'Paris', 'London,UK') or 'auto' for automatic location
        user_message: Original user message for location phrase detection
        units: 'metric' for Celsius, 'imperial' for Fahrenheit (default: metric)
        language: Language code for descriptions (default: fr)
        runtime: Tool runtime (injected)

    Returns:
        Current weather data as JSON string

    Examples:
        - get_current_weather("Paris")
        - get_current_weather(location="auto", user_message="météo chez moi")
        - get_current_weather("Tokyo", units="metric", language="ja")
    """
    return await _get_current_weather_tool_impl.execute(
        runtime,
        location=location,
        user_message=user_message,
        units=units,
        language=language,
    )


# ============================================================================
# TOOL 2: GET WEATHER FORECAST
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_weather_forecast",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_weather_forecast_tool(
    location: Annotated[
        str | None,
        "City name (e.g., 'Paris', 'New York') or 'auto' for automatic geolocation",
    ] = None,
    user_message: Annotated[
        str,
        "Original user message (for location phrase detection like 'chez moi', 'nearby')",
    ] = "",
    date: Annotated[
        str | None,
        "Temporal reference (e.g., 'demain', 'tomorrow', 'après-demain', 'dans 2 jours') - determines forecast start date",
    ] = None,
    days: Annotated[int, "Number of days to forecast (1-5)"] = settings.weather_forecast_max_days,
    units: Annotated[
        str, "Temperature units: 'metric' (Celsius) or 'imperial' (Fahrenheit)"
    ] = "metric",
    language: Annotated[
        str, "Language code for weather description (e.g., 'fr', 'en', 'es')"
    ] = "fr",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> str:
    """
    Get weather forecast for a location.

    Provides daily forecast including:
    - Temperature (min, max, morning, day, evening, night)
    - Weather conditions
    - Precipitation probability
    - Wind speed

    Args:
        location: City name (e.g., 'Paris', 'London,UK') or 'auto' for automatic location
        user_message: Original user message for location phrase detection
        days: Number of days to forecast (1-5, default: 5)
        units: 'metric' for Celsius, 'imperial' for Fahrenheit (default: metric)
        language: Language code for descriptions (default: fr)
        runtime: Tool runtime (injected)

    Returns:
        Weather forecast data as JSON string

    Examples:
        - get_weather_forecast("Paris", days=3)
        - get_weather_forecast(location="auto", user_message="prévisions chez moi", days=5)
    """
    return await _get_weather_forecast_tool_impl.execute(
        runtime,
        location=location,
        user_message=user_message,
        date=date,
        days=days,
        units=units,
        language=language,
    )


# ============================================================================
# TOOL 3: GET HOURLY FORECAST
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_hourly_forecast",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_hourly_forecast_tool(
    location: Annotated[
        str | None,
        "City name (e.g., 'Paris', 'New York') or 'auto' for automatic geolocation",
    ] = None,
    user_message: Annotated[
        str,
        "Original user message (for location phrase detection like 'chez moi', 'nearby')",
    ] = "",
    date: Annotated[
        str | None,
        "Target day (e.g., 'tomorrow', '2026-07-25', or a calendar ISO datetime). "
        "Returns that specific day's 3-hour slots. Omit for a rolling window from now.",
    ] = None,
    hours: Annotated[
        int,
        "Rolling window size in hours from now (used only when 'date' is omitted).",
    ] = 24,
    units: Annotated[
        str, "Temperature units: 'metric' (Celsius) or 'imperial' (Fahrenheit)"
    ] = "metric",
    language: Annotated[
        str, "Language code for weather description (e.g., 'fr', 'en', 'es')"
    ] = "fr",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> str:
    """
    Get intra-day weather forecast in 3-hour steps for a location.

    Backed by the free 5-day / 3-hour forecast: data is available up to 5 days
    ahead at a 3-hour granularity (NOT hour-by-hour), so a time like 11:15 maps
    to the nearest 3-hour slot. For a whole-day summary prefer get_weather_forecast.

    Provides, per 3-hour slot:
    - Temperature
    - Weather conditions
    - Precipitation probability
    - Wind speed

    Args:
        location: City name (e.g., 'Paris', 'London,UK') or 'auto' for automatic location
        user_message: Original user message for location phrase detection
        date: Target day (temporal reference or ISO date/datetime); when given, only
            that day's 3-hour slots are returned. Beyond the 5-day window an explicit
            error is returned. Omit for a rolling near-term window.
        hours: Rolling window size in hours when no date is given (default: 24)
        units: 'metric' for Celsius, 'imperial' for Fahrenheit (default: metric)
        language: Language code for descriptions (default: fr)
        runtime: Tool runtime (injected)

    Returns:
        3-hour-step forecast data as JSON string

    Examples:
        - get_hourly_forecast("Paris", hours=12)
        - get_hourly_forecast("Paris", date="2026-07-25")  # that day's 3-hour slots
        - get_hourly_forecast(location="auto", user_message="météo par tranches chez moi")
    """
    return await _get_hourly_forecast_tool_impl.execute(
        runtime,
        location=location,
        user_message=user_message,
        date=date,
        hours=hours,
        units=units,
        language=language,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "get_current_weather_tool",
    "get_weather_forecast_tool",
    "get_hourly_forecast_tool",
]
