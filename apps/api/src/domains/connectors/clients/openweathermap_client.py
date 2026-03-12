"""
OpenWeatherMap API client.

Provides weather data retrieval for current conditions, forecasts, and historical data.
Uses the OpenWeatherMap API v2.5/3.0.

API Reference:
- https://openweathermap.org/api
- Current Weather: https://openweathermap.org/current
- 5-day Forecast: https://openweathermap.org/forecast5
- Geocoding: https://openweathermap.org/api/geocoding-api

Free tier limits:
- 1,000 API calls/day
- Current weather, 5-day/3-hour forecast, geocoding
- 60 calls/minute rate limit

Required:
- API key from https://home.openweathermap.org/api_keys
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, HTTP_TIMEOUT_WEATHER
from src.core.exceptions import MaxRetriesExceededError

logger = structlog.get_logger(__name__)


class OpenWeatherMapClient:
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

    api_base_url = "https://api.openweathermap.org"
    geo_base_url = "https://api.openweathermap.org/geo/1.0"

    def __init__(
        self,
        api_key: str,
        user_id: UUID | None = None,
        rate_limit_per_second: int | None = None,
    ) -> None:
        """
        Initialize OpenWeatherMap client.

        Args:
            api_key: OpenWeatherMap API key
            user_id: Optional user ID for logging
            rate_limit_per_second: Max requests per second (None = use settings)
        """
        self.api_key = api_key
        self.user_id = user_id
        # Use settings if not explicitly provided
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_openweathermap_per_second
        )
        self._rate_limit_per_second = effective_rate_limit
        self._rate_limit_interval = 1.0 / effective_rate_limit
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_WEATHER,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                ),
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanup HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _rate_limit(self) -> None:
        """Apply simple rate limiting."""
        import time

        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < self._rate_limit_interval:
            wait_time = self._rate_limit_interval - elapsed
            await asyncio.sleep(wait_time)

        self._last_request_time = time.monotonic()

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

        params = {
            "q": query,
            "limit": limit,
            "appid": self.api_key,
        }

        response = await self._make_geocoding_request(
            f"{self.geo_base_url}/direct",
            params,
        )

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
        params = {
            "lat": lat,
            "lon": lon,
            "limit": limit,
            "appid": self.api_key,
        }

        response = await self._make_geocoding_request(
            f"{self.geo_base_url}/reverse",
            params,
        )

        return response

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

        response = await self._make_request(
            f"{self.api_base_url}/data/2.5/weather",
            params,
        )

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

        response = await self._make_request(
            f"{self.api_base_url}/data/2.5/forecast",
            params,
        )

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
        # Get full 3-hour forecast
        forecast = await self.get_forecast(
            lat=lat,
            lon=lon,
            city=city,
            country=country,
            units=units,
            lang=lang,
        )

        # Parse user timezone (fallback to UTC if invalid)
        try:
            tz = ZoneInfo(user_timezone)
        except (KeyError, ValueError):
            logger.warning("invalid_user_timezone", timezone=user_timezone, fallback="UTC")
            tz = UTC

        # Aggregate by day IN USER'S TIMEZONE
        # This ensures "tomorrow" is correctly grouped according to user's local midnight
        daily_data: dict[str, dict[str, Any]] = {}

        for entry in forecast.get("list", []):
            # Convert UTC timestamp to user's timezone before extracting date
            dt_utc = datetime.fromtimestamp(entry["dt"], tz=UTC)
            dt_user = dt_utc.astimezone(tz)
            date_key = dt_user.strftime("%Y-%m-%d")

            if date_key not in daily_data:
                daily_data[date_key] = {
                    "date": date_key,
                    "date_formatted": dt_user.strftime("%A, %B %d"),
                    "temps": [],
                    "conditions": [],
                    "humidity": [],
                    "wind_speed": [],
                }

            main = entry.get("main", {})
            weather = entry.get("weather", [{}])[0]
            wind = entry.get("wind", {})

            daily_data[date_key]["temps"].append(main.get("temp", 0))
            daily_data[date_key]["conditions"].append(weather.get("description", ""))
            daily_data[date_key]["humidity"].append(main.get("humidity", 0))
            daily_data[date_key]["wind_speed"].append(wind.get("speed", 0))

        # Calculate daily summaries (sorted by date, limited to requested days)
        daily_list = []
        for _date_key, data in sorted(daily_data.items())[:days]:
            temps = data["temps"]
            daily_list.append(
                {
                    "date": data["date"],
                    "date_formatted": data["date_formatted"],
                    "temp_min": round(min(temps), 1),
                    "temp_max": round(max(temps), 1),
                    "temp_avg": round(sum(temps) / len(temps), 1),
                    "condition": max(set(data["conditions"]), key=data["conditions"].count),
                    "humidity_avg": round(sum(data["humidity"]) / len(data["humidity"])),
                    "wind_speed_avg": round(sum(data["wind_speed"]) / len(data["wind_speed"]), 1),
                }
            )

        return {
            "daily": daily_list,
            "city": forecast.get("city", {}),
        }

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
        """Build query parameters for weather API calls."""
        params: dict[str, Any] = {
            "appid": self.api_key,
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

    async def _make_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Make authenticated request to OpenWeatherMap API (dict response).

        Args:
            url: Full API URL
            params: Query parameters

        Returns:
            JSON response as dict
        """
        # Apply rate limiting
        await self._rate_limit()

        client = await self._get_client()

        # Make request with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(url, params=params)

                if response.status_code == 429:
                    # Rate limited
                    wait_time = 2**attempt
                    logger.warning(
                        "weather_rate_limited",
                        user_id=str(self.user_id) if self.user_id else None,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code == 401:
                    logger.error(
                        "weather_invalid_api_key",
                        user_id=str(self.user_id) if self.user_id else None,
                    )
                    raise ValueError("Invalid OpenWeatherMap API key")

                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result

            except httpx.HTTPStatusError as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "weather_request_failed",
                        user_id=str(self.user_id) if self.user_id else None,
                        url=url,
                        error=str(e),
                        status_code=e.response.status_code if e.response else None,
                    )
                    raise

                wait_time = 2**attempt
                logger.warning(
                    "weather_request_retry",
                    user_id=str(self.user_id) if self.user_id else None,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "weather_request_error",
                        user_id=str(self.user_id) if self.user_id else None,
                        url=url,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

                await asyncio.sleep(2**attempt)

        # Should never reach here, but satisfy type checker
        raise MaxRetriesExceededError(
            operation="openweathermap_request",
            max_retries=3,
        )

    async def _make_geocoding_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Make geocoding request to OpenWeatherMap API (list response).

        Args:
            url: Full API URL
            params: Query parameters

        Returns:
            JSON response as list
        """
        # Apply rate limiting
        await self._rate_limit()

        client = await self._get_client()

        # Make request with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(url, params=params)

                if response.status_code == 429:
                    # Rate limited
                    wait_time = 2**attempt
                    logger.warning(
                        "weather_rate_limited",
                        user_id=str(self.user_id) if self.user_id else None,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code == 401:
                    logger.error(
                        "weather_invalid_api_key",
                        user_id=str(self.user_id) if self.user_id else None,
                    )
                    raise ValueError("Invalid OpenWeatherMap API key")

                response.raise_for_status()
                result: list[dict[str, Any]] = response.json()
                return result

            except httpx.HTTPStatusError as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "weather_geocoding_failed",
                        user_id=str(self.user_id) if self.user_id else None,
                        url=url,
                        error=str(e),
                        status_code=e.response.status_code if e.response else None,
                    )
                    raise

                wait_time = 2**attempt
                logger.warning(
                    "weather_request_retry",
                    user_id=str(self.user_id) if self.user_id else None,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "weather_geocoding_error",
                        user_id=str(self.user_id) if self.user_id else None,
                        url=url,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

                await asyncio.sleep(2**attempt)

        # Should never reach here, but satisfy type checker
        raise MaxRetriesExceededError(
            operation="openweathermap_geocoding_request",
            max_retries=3,
        )

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
