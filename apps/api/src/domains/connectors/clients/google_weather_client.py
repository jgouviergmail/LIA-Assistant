"""Google Weather API client, normalized to the OpenWeatherMap shape (lot E).

Platform-key provider of the "weather" functional category. LIA's internal
weather shape is the OWM JSON (19 call sites): this client normalizes the
Google Weather API AT ITS BOUNDARY so every consumer (tools, briefing,
heartbeat, proactive) works unchanged whichever provider is active.

Authentication: global GOOGLE_API_KEY (activation is a user toggle, no
per-user credentials — same doctrine as GooglePlacesClient). Every call is
billed $0.15/1000 (10,000 free/month) and tracked for user rebilling.

Icons: Google condition types are mapped to OWM icon codes so the weather
card renders the SAME visual language for both providers.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    GOOGLE_WEATHER_API_BASE_URL,
    GOOGLE_WEATHER_FORECAST_PAGE_SIZE,
    GOOGLE_WEATHER_MAX_FORECAST_HOURS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
)
from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.clients.google_geocoding_helpers import (
    forward_geocode,
    google_reverse_city,
)
from src.domains.connectors.clients.weather_normalization import aggregate_daily_forecast
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

# Google weatherCondition.type -> OWM icon code (day variant; night swaps d->n).
# Unknown/future types fall back to scattered clouds — a neutral glyph.
_ICON_BY_CONDITION_TYPE: dict[str, str] = {
    "CLEAR": "01",
    "MOSTLY_CLEAR": "02",
    "PARTLY_CLOUDY": "02",
    "MOSTLY_CLOUDY": "03",
    "CLOUDY": "04",
    "FOG": "50",
    "HAZE": "50",
    "WINDY": "50",
    "DRIZZLE": "09",
    "LIGHT_RAIN": "10",
    "RAIN": "10",
    "HEAVY_RAIN": "10",
    "RAIN_SHOWERS": "09",
    "SNOW": "13",
    "LIGHT_SNOW": "13",
    "HEAVY_SNOW": "13",
    "SNOW_SHOWERS": "13",
    "SLEET": "13",
    "HAIL": "13",
    "THUNDERSTORM": "11",
    "THUNDERSHOWER": "11",
}
_ICON_FALLBACK = "03"


def _owm_icon(condition_type: str, is_daytime: bool) -> str:
    """OWM icon code for a Google condition type (day/night aware)."""
    base = _ICON_BY_CONDITION_TYPE.get(condition_type, _ICON_FALLBACK)
    return f"{base}{'d' if is_daytime else 'n'}"


def _kmh_to_ms(value: float | None) -> float | None:
    """Google METRIC wind speeds are km/h; the OWM metric unit is m/s."""
    return round(value / 3.6, 2) if value is not None else None


def _condition_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """OWM `weather[0]` entry from a Google condition block."""
    condition = payload.get("weatherCondition") or {}
    description = (condition.get("description") or {}).get("text", "")
    return {
        "id": 0,
        "main": condition.get("type", ""),
        "description": description,
        "icon": _owm_icon(condition.get("type", ""), bool(payload.get("isDaytime", True))),
    }


def _wind_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """OWM `wind` entry (m/s + degrees) from a Google wind block."""
    wind = payload.get("wind") or {}
    speed = _kmh_to_ms((wind.get("speed") or {}).get("value"))
    entry: dict[str, Any] = {}
    if speed is not None:
        entry["speed"] = speed
    degrees = (wind.get("direction") or {}).get("degrees")
    if degrees is not None:
        entry["deg"] = degrees
    return entry


def _main_block(payload: dict[str, Any]) -> dict[str, Any]:
    """OWM `main` block (temps, humidity, pressure) from current conditions."""
    history = payload.get("currentConditionsHistory") or {}
    main: dict[str, Any] = {
        "temp": (payload.get("temperature") or {}).get("degrees"),
        "feels_like": (payload.get("feelsLikeTemperature") or {}).get("degrees"),
    }
    if payload.get("relativeHumidity") is not None:
        main["humidity"] = payload["relativeHumidity"]
    pressure = (payload.get("airPressure") or {}).get("meanSeaLevelMillibars")
    if pressure is not None:
        main["pressure"] = pressure
    if (history.get("minTemperature") or {}).get("degrees") is not None:
        main["temp_min"] = history["minTemperature"]["degrees"]
    if (history.get("maxTemperature") or {}).get("degrees") is not None:
        main["temp_max"] = history["maxTemperature"]["degrees"]
    return main


def _epoch(iso_time: str | None) -> int:
    """Epoch seconds from an RFC3339 timestamp (now when absent)."""
    if iso_time:
        try:
            return int(datetime.fromisoformat(iso_time.replace("Z", "+00:00")).timestamp())
        except ValueError:
            logger.debug("google_weather_bad_timestamp")
    return int(datetime.now(UTC).timestamp())


class GoogleWeatherClient:
    """Google Weather API client with the OpenWeatherMap-shaped interface."""

    connector_type = ConnectorType.GOOGLE_WEATHER
    api_base_url = GOOGLE_WEATHER_API_BASE_URL

    def __init__(self, user_id: UUID, rate_limit_per_second: int = 10) -> None:
        """Initialize with the platform API key (no per-user credentials).

        Args:
            user_id: User UUID (logging + billing attribution).
            rate_limit_per_second: Local request pacing.
        """
        self.user_id = user_id
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0

    @property
    def api_key(self) -> str:
        """Global API key from settings."""
        if not settings.google_api_key:
            raise ExternalServiceError(
                service_name="google_weather",
                detail="Google Weather service unavailable: API key not configured",
                error_type="configuration_missing",
            )
        return settings.google_api_key

    async def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_interval:
            await asyncio.sleep(self._rate_limit_interval - elapsed)
        self._last_request_time = time.time()

    async def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET one Weather API endpoint with the platform key."""
        await self._rate_limit()
        query = {**params, "key": self.api_key}
        async with httpx.AsyncClient(
            timeout=float(settings.http_timeout_weather),
            limits=httpx.Limits(
                max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                max_connections=HTTP_MAX_CONNECTIONS,
            ),
        ) as client:
            response = await client.get(f"{self.api_base_url}{endpoint}", params=query)
            if response.status_code >= 400:
                raise ConnectorAPIError(
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                    detail="Google Weather API error",
                )
            return dict(response.json())

    async def _resolve_point(
        self, lat: float | None, lon: float | None, city: str | None, country: str | None
    ) -> tuple[float, float, str, str]:
        """Resolve the query point, geocoding the city when needed."""
        if lat is not None and lon is not None:
            return lat, lon, "", ""
        query = f"{city},{country}" if city and country else (city or "")
        coords = await forward_geocode(query)
        if coords is None:
            raise ConnectorAPIError(
                connector_type=self.connector_type.value,
                status_code=404,
                detail="Location not found",
            )
        return coords[0], coords[1], coords[2] or (city or ""), coords[3] or (country or "")

    # =========================================================================
    # OWM-SHAPED INTERFACE
    # =========================================================================

    async def close(self) -> None:
        """No-op: HTTP clients are per-call (briefing/heartbeat call close())."""

    async def reverse_geocode(self, lat: float, lon: float, limit: int = 5) -> list[dict[str, Any]]:
        """Reverse geocode via Google Geocoding, in the OWM geo/1.0 list shape."""
        resolved = await google_reverse_city(lat, lon)
        if resolved is None:
            return []
        city, country = resolved
        return [{"name": city, "country": country}]

    async def geocode(
        self,
        city: str,
        country: str | None = None,
        state: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Geocode via Google Geocoding, in the OWM geo/1.0 list shape."""
        query = ",".join(part for part in (city, state, country) if part)
        coords = await forward_geocode(query)
        if coords is None:
            return []
        lat, lon, name, resolved_country = coords
        return [{"lat": lat, "lon": lon, "name": name, "country": resolved_country}]

    async def get_current_weather(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
    ) -> dict[str, Any]:
        """Current conditions, normalized to the OWM current-weather shape."""
        lat, lon, name, resolved_country = await self._resolve_point(lat, lon, city, country)
        payload = await self._make_request(
            "/v1/currentConditions:lookup",
            params={
                "location.latitude": lat,
                "location.longitude": lon,
                "unitsSystem": "METRIC",
                "languageCode": lang,
            },
        )
        track_google_api_call("weather", "/v1/currentConditions:lookup", cached=False)

        weather: dict[str, Any] = {
            "coord": {"lat": lat, "lon": lon},
            "weather": [_condition_entry(payload)],
            "main": _main_block(payload),
            "wind": _wind_entry(payload),
            "dt": _epoch(payload.get("currentTime") or None),
            "sys": {"country": resolved_country},
            "name": name,
        }
        if payload.get("cloudCover") is not None:
            weather["clouds"] = {"all": payload["cloudCover"]}
        visibility_km = (payload.get("visibility") or {}).get("distance")
        if visibility_km is not None:
            weather["visibility"] = int(visibility_km * 1000)

        logger.info("google_weather_current_retrieved", user_id=str(self.user_id))
        return weather

    async def get_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str = "en",
        cnt: int = 40,
    ) -> dict[str, Any]:
        """Hourly forecast sampled to OWM 3-hour entries ({"list", "city"})."""
        lat, lon, name, resolved_country = await self._resolve_point(lat, lon, city, country)
        hours_needed = min(max(cnt, 1) * 3, GOOGLE_WEATHER_MAX_FORECAST_HOURS)

        forecast_hours: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(forecast_hours) < hours_needed:
            params: dict[str, Any] = {
                "location.latitude": lat,
                "location.longitude": lon,
                "unitsSystem": "METRIC",
                "languageCode": lang,
                "hours": hours_needed,
                "pageSize": GOOGLE_WEATHER_FORECAST_PAGE_SIZE,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = await self._make_request("/v1/forecast/hours:lookup", params=params)
            track_google_api_call("weather", "/v1/forecast/hours:lookup", cached=False)
            forecast_hours.extend(payload.get("forecastHours", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        entries = []
        for hour_entry in forecast_hours[:hours_needed:3]:
            entry: dict[str, Any] = {
                "dt": _epoch((hour_entry.get("interval") or {}).get("startTime")),
                "main": {
                    "temp": (hour_entry.get("temperature") or {}).get("degrees"),
                    "humidity": hour_entry.get("relativeHumidity"),
                },
                "weather": [_condition_entry(hour_entry)],
                "wind": _wind_entry(hour_entry),
            }
            percent = ((hour_entry.get("precipitation") or {}).get("probability") or {}).get(
                "percent"
            )
            if percent is not None:
                entry["pop"] = round(percent / 100, 2)
            entries.append(entry)

        logger.info(
            "google_weather_forecast_retrieved",
            user_id=str(self.user_id),
            entries=len(entries),
        )
        return {
            "list": entries[:cnt],
            "city": {
                "name": name,
                "country": resolved_country,
                "coord": {"lat": lat, "lon": lon},
            },
        }

    async def get_daily_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        days: int = 5,
        user_timezone: str = "UTC",
        lang: str = "en",
    ) -> dict[str, Any]:
        """Daily summaries via the shared aggregation (same as OWM)."""
        forecast = await self.get_forecast(
            lat=lat,
            lon=lon,
            city=city,
            country=country,
            units=units,
            lang=lang,
            cnt=min(days, 10) * 8,  # 8 three-hour slots per day, 10-day cap
        )
        return aggregate_daily_forecast(forecast, days, user_timezone)

    @staticmethod
    def get_weather_icon_url(icon_code: str, size: str = "2x") -> str:
        """OWM icon URL — identical visual language for both providers."""
        return f"https://openweathermap.org/img/wn/{icon_code}@{size}.png"
