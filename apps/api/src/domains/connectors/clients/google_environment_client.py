"""Google Environment client — Air Quality + Pollen (lot E, 2026-08).

Platform-key client behind the GOOGLE_ENVIRONMENT toggle, independent of the
weather provider choice (deliberately outside the "weather" category — an
OpenWeatherMap user keeps AQ/pollen).

Billing (tracked per call): Air Quality $5/1000 (10,000 free/month),
Pollen $10/1000 (5,000 free/month).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    GOOGLE_AIR_QUALITY_API_URL,
    GOOGLE_POLLEN_API_URL,
    GOOGLE_POLLEN_MAX_DAYS,
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
)
from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class GoogleEnvironmentClient:
    """Air Quality + Pollen client (platform GOOGLE_API_KEY)."""

    connector_type = ConnectorType.GOOGLE_ENVIRONMENT

    def __init__(self, user_id: UUID, rate_limit_per_second: int = 10) -> None:
        """Initialize with the platform API key (no per-user credentials)."""
        self.user_id = user_id
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0

    @property
    def api_key(self) -> str:
        """Global API key from settings."""
        if not settings.google_api_key:
            raise ExternalServiceError(
                service_name="google_environment",
                detail="Google Environment services unavailable: API key not configured",
                error_type="configuration_missing",
            )
        return settings.google_api_key

    async def _pace(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_interval:
            await asyncio.sleep(self._rate_limit_interval - elapsed)
        self._last_request_time = time.time()

    async def _make_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call one Environment API endpoint with the platform key."""
        await self._pace()
        query = {**(params or {}), "key": self.api_key}
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_external_api,
            limits=httpx.Limits(
                max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                max_connections=HTTP_MAX_CONNECTIONS,
            ),
        ) as client:
            response = await client.request(method, url, params=query, json=json_data)
            if response.status_code >= 400:
                raise ConnectorAPIError(
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                    detail="Google Environment API error",
                )
            return dict(response.json())

    async def get_air_quality(self, lat: float, lon: float, language: str = "en") -> dict[str, Any]:
        """Current air quality at a point (UAQI + local national index).

        Args:
            lat: Latitude.
            lon: Longitude.
            language: Language for category labels.

        Returns:
            {"region_code", "date_time", "indexes": [{code, display_name,
            aqi, category, dominant_pollutant}]} — exact API aggregates.
        """
        payload = await self._make_request(
            "POST",
            GOOGLE_AIR_QUALITY_API_URL,
            json_data={
                "location": {"latitude": lat, "longitude": lon},
                "languageCode": language,
                # The local (national) index matters to the user as much as
                # the universal one — both are requested explicitly.
                "extraComputations": ["LOCAL_AQI"],
            },
        )
        track_google_api_call("air_quality", "/v1/currentConditions:lookup", cached=False)

        indexes = [
            {
                "code": index.get("code", ""),
                "display_name": index.get("displayName", ""),
                "aqi": index.get("aqi"),
                "category": index.get("category", ""),
                "dominant_pollutant": index.get("dominantPollutant", ""),
            }
            for index in payload.get("indexes", [])
        ]
        logger.info("air_quality_retrieved", user_id=str(self.user_id), indexes=len(indexes))
        return {
            "region_code": payload.get("regionCode", ""),
            "date_time": payload.get("dateTime", ""),
            "indexes": indexes,
        }

    async def get_pollen_forecast(
        self, lat: float, lon: float, days: int = 3, language: str = "en"
    ) -> dict[str, Any]:
        """Pollen forecast at a point (grass/tree/weed types with indices).

        Args:
            lat: Latitude.
            lon: Longitude.
            days: Forecast days (clamped to the API maximum).
            language: Language for display names and categories.

        Returns:
            {"region_code", "days": [{date, types: [{code, display_name,
            in_season, index_value, category}]}]} — exact API values;
            out-of-season types appear with an honest empty index.
        """
        payload = await self._make_request(
            "GET",
            GOOGLE_POLLEN_API_URL,
            params={
                "location.latitude": lat,
                "location.longitude": lon,
                "days": max(1, min(days, GOOGLE_POLLEN_MAX_DAYS)),
                "languageCode": language,
            },
        )
        track_google_api_call("pollen", "/v1/forecast:lookup", cached=False)

        days_out = []
        for daily in payload.get("dailyInfo", []):
            date = daily.get("date") or {}
            types = [
                {
                    "code": pollen.get("code", ""),
                    "display_name": pollen.get("displayName", ""),
                    "in_season": bool(pollen.get("inSeason", False)),
                    "index_value": (pollen.get("indexInfo") or {}).get("value"),
                    "category": (pollen.get("indexInfo") or {}).get("category", ""),
                }
                for pollen in daily.get("pollenTypeInfo", [])
            ]
            days_out.append(
                {
                    "date": (
                        f"{date.get('year', 0):04d}-{date.get('month', 0):02d}"
                        f"-{date.get('day', 0):02d}"
                    ),
                    "types": types,
                }
            )
        logger.info("pollen_forecast_retrieved", user_id=str(self.user_id), days=len(days_out))
        return {"region_code": payload.get("regionCode", ""), "days": days_out}
