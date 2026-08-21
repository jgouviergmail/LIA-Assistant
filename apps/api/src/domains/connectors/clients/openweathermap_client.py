"""
OpenWeatherMap API Client - Weather Data & Geocoding.

Provides access to OpenWeatherMap API:
- https://openweathermap.org/api
- Current Weather: https://openweathermap.org/current
- 5-day Forecast: https://openweathermap.org/forecast5
- Geocoding: https://openweathermap.org/api/geocoding-api

Authentication:
- API key as ``appid`` query parameter
- API key from https://home.openweathermap.org/api_keys

Built on BaseAPIKeyClient (F3 migration): Redis-backed rate limiting with
local fallback, circuit breaker, retry with backoff, connection pooling.
The public contract is unchanged: methods RAISE on errors (callers absorb —
``gather(return_exceptions=True)`` in heartbeat, broad except in geocoding,
error-family catch in briefing) and the geocoding endpoints return lists.
One deliberate nuance (2026-08-20): geo/1.0 answers HTTP 404 for a query it
cannot match — that is a no-results verdict, so geocode()/reverse_geocode()
return [] there instead of raising.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import httpx

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class OpenWeatherMapClient(BaseAPIKeyClient):
    """
    Client for OpenWeatherMap API.

    Provides access to:
    - Current weather conditions
    - 5-day/3-hour forecasts
    - Geocoding (location lookup)
    - Weather icons and descriptions

    Example:
        >>> client = OpenWeatherMapClient(api_key="your_api_key")
        >>> weather = await client.get_current_weather(city="Paris", country="FR")
        >>> print(f"Temperature: {weather['main']['temp']}°C")
    """

    connector_type = ConnectorType.OPENWEATHERMAP
    api_base_url = "https://api.openweathermap.org"

    # API key travels as the ``appid`` query parameter
    auth_method = "query"
    auth_query_param = "appid"

    def __init__(
        self,
        api_key: str,
        user_id: UUID | None = None,
        rate_limit_per_second: float | None = None,
    ) -> None:
        """
        Initialize OpenWeatherMap client.

        Args:
            api_key: OpenWeatherMap API key
            user_id: Optional user ID for logging and rate-limit scoping
            rate_limit_per_second: Max requests per second (None = use settings)
        """
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_openweathermap_per_second
        )
        super().__init__(
            user_id=user_id,
            credentials=APIKeyCredentials(api_key=api_key),
            rate_limit_per_second=effective_rate_limit,
        )
        self.api_key = api_key

    def _get_http_timeout(self) -> float:
        """Weather API has a dedicated timeout setting."""
        return float(settings.http_timeout_weather)

    # =========================================================================
    # GEOCODING OPERATIONS
    # =========================================================================

    async def geocode(
        self,
        city: str,
        country: str | None = None,
        state: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Convert city name to coordinates.

        Args:
            city: City name
            country: ISO 3166 country code (e.g., "FR", "US")
            state: State code for US locations
            limit: Maximum number of results (default: 5)

        Returns:
            List of locations with lat, lon, name, country

        Example:
            >>> locations = await client.geocode("Paris", country="FR")
            >>> print(f"Paris: {locations[0]['lat']}, {locations[0]['lon']}")
        """
        # Build query string
        query_parts = [city]
        if state:
            query_parts.append(state)
        if country:
            query_parts.append(country)
        query = ",".join(query_parts)

        params: dict[str, Any] = {"q": query, "limit": limit}

        try:
            # geo/1.0 endpoints return a JSON list (not a dict)
            response = cast(
                "list[dict[str, Any]]",
                await self._make_request("GET", "geo/1.0/direct", params=params),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # geo/1.0 answers 404 {"cod":"404","message":"not found"} for a
                # query it cannot match (measured in prod 2026-08-19). That is a
                # no-results verdict, not a failure: returning [] keeps the
                # Google fallback and the tools' location_not_found path
                # reachable instead of surfacing a raw traceback.
                logger.info(
                    "weather_geocode_no_results",
                    user_id=str(self.user_id) if self.user_id else None,
                    query_chars=len(query),
                )
                return []
            raise

        logger.info(
            "weather_geocode_completed",
            user_id=str(self.user_id) if self.user_id else None,
            query=query,
            results_count=len(response),
        )

        return response

    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Convert coordinates to location name.

        Args:
            lat: Latitude
            lon: Longitude
            limit: Maximum number of results (default: 5)

        Returns:
            List of locations with name, country, state
        """
        params: dict[str, Any] = {"lat": lat, "lon": lon, "limit": limit}

        try:
            # geo/1.0 endpoints return a JSON list (not a dict)
            return cast(
                "list[dict[str, Any]]",
                await self._make_request("GET", "geo/1.0/reverse", params=params),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # Same no-results verdict as geocode() — see comment there.
                logger.info(
                    "weather_reverse_geocode_no_results",
                    user_id=str(self.user_id) if self.user_id else None,
                )
                return []
            raise

    # =========================================================================
    # CURRENT WEATHER
    # =========================================================================

    async def get_current_weather(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
    ) -> dict[str, Any]:
        """
        Get current weather conditions.

        Either provide lat/lon OR city (and optional country).

        Args:
            lat: Latitude (use with lon)
            lon: Longitude (use with lat)
            city: City name (alternative to lat/lon)
            country: ISO 3166 country code
            units: Temperature units - "metric" (°C), "imperial" (°F), "standard" (K)
            lang: Language for descriptions (e.g., "en", "fr", "es")

        Returns:
            Weather data including temperature, humidity, wind, conditions

        Example:
            >>> weather = await client.get_current_weather(city="Paris", country="FR")
            >>> temp = weather["main"]["temp"]
            >>> desc = weather["weather"][0]["description"]
            >>> print(f"{temp}°C - {desc}")
        """
        params = self._build_weather_params(
            lat=lat,
            lon=lon,
            city=city,
            country=country,
            units=units,
            lang=lang,
        )

        response = await self._make_request("GET", "data/2.5/weather", params=params)

        logger.info(
            "weather_current_retrieved",
            user_id=str(self.user_id) if self.user_id else None,
            location=response.get("name"),
            temp=response.get("main", {}).get("temp"),
            units=units,
        )

        return response

    # =========================================================================
    # FORECAST
    # =========================================================================

    async def get_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
        cnt: int | None = None,
    ) -> dict[str, Any]:
        """
        Get 5-day / 3-hour weather forecast.

        Either provide lat/lon OR city (and optional country).

        Args:
            lat: Latitude (use with lon)
            lon: Longitude (use with lat)
            city: City name (alternative to lat/lon)
            country: ISO 3166 country code
            units: Temperature units - "metric" (°C), "imperial" (°F), "standard" (K)
            lang: Language for descriptions
            cnt: Number of forecast entries to return (max 40 = 5 days)

        Returns:
            Forecast data with list of 3-hour intervals

        Example:
            >>> forecast = await client.get_forecast(city="Paris", country="FR")
            >>> for entry in forecast["list"][:8]:  # Next 24 hours
            ...     dt = entry["dt_txt"]
            ...     temp = entry["main"]["temp"]
            ...     print(f"{dt}: {temp}°C")
        """
        params = self._build_weather_params(
            lat=lat,
            lon=lon,
            city=city,
            country=country,
            units=units,
            lang=lang,
        )

        if cnt:
            params["cnt"] = min(cnt, 40)

        response = await self._make_request("GET", "data/2.5/forecast", params=params)

        logger.info(
            "weather_forecast_retrieved",
            user_id=str(self.user_id) if self.user_id else None,
            location=response.get("city", {}).get("name"),
            entries_count=len(response.get("list", [])),
        )

        return response

    async def get_daily_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
        days: int = 5,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> dict[str, Any]:
        """
        Get simplified daily forecast.

        Aggregates 3-hour forecast data into daily summaries.
        Data is grouped by date in the user's timezone to ensure correct
        day boundaries (e.g., "tomorrow" means tomorrow in user's local time).

        Args:
            lat: Latitude
            lon: Longitude
            city: City name
            country: Country code
            units: Temperature units
            lang: Language
            days: Number of days (max 5 for free tier)
            user_timezone: User's IANA timezone for date grouping (e.g., "Europe/Paris")

        Returns:
            Dict with:
            - "daily": List of daily summaries with min/max temp, conditions
            - "city": City info from API (name, country, coord, etc.)
            Each day in "daily" has a "date" field in YYYY-MM-DD format (user's timezone).

        Example:
            >>> result = await client.get_daily_forecast(city="Paris", days=3, user_timezone="Europe/Paris")
            >>> for day in result["daily"]:
            ...     print(f"{day['date']}: {day['temp_min']}°C - {day['temp_max']}°C")
        """
        # Get full 3-hour forecast, then aggregate through the shared helper
        # (one implementation for every weather provider — lot E, 2026-08).
        from src.domains.connectors.clients.weather_normalization import (
            aggregate_daily_forecast,
        )

        forecast = await self.get_forecast(
            lat=lat,
            lon=lon,
            city=city,
            country=country,
            units=units,
            lang=lang,
        )
        return aggregate_daily_forecast(forecast, days, user_timezone)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _build_weather_params(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
    ) -> dict[str, Any]:
        """Build query parameters for weather API calls (appid injected by base)."""
        params: dict[str, Any] = {
            "units": units,
            "lang": lang,
        }

        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
        elif city:
            query = city
            if country:
                query = f"{city},{country}"
            params["q"] = query
        else:
            raise ValueError("Either lat/lon or city must be provided")

        return params

    @staticmethod
    def get_weather_icon_url(icon_code: str, size: str = "2x") -> str:
        """
        Get URL for weather condition icon.

        Args:
            icon_code: Icon code from API response (e.g., "01d", "10n")
            size: Icon size - "1x", "2x", "4x"

        Returns:
            URL to the weather icon
        """
        return f"https://openweathermap.org/img/wn/{icon_code}@{size}.png"
