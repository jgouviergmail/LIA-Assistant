"""Air quality + pollen tools (lot E, 2026-08).

Both tools resolve the point like the places tools do (explicit location →
geocode; otherwise the implicit browser/last-known/home cascade) and return
the client's EXACT indices as structured data.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.environment_tools import (
    GetAirQualityTool,
    GetPollenForecastTool,
)

pytestmark = pytest.mark.unit


def _tool(tool_class: Any) -> Any:
    tool = tool_class()
    tool.runtime = MagicMock()
    return tool


def _patch_language() -> Any:
    return patch(
        "src.domains.agents.tools.runtime_helpers.get_user_language_safe",
        new=AsyncMock(return_value="fr"),
    )


def _patch_implicit(lat: float | None = 48.85, lon: float | None = 2.35) -> Any:
    location = SimpleNamespace(lat=lat, lon=lon, source="browser") if lat is not None else None
    return patch(
        "src.domains.agents.tools.location_resolution.resolve_implicit_location",
        new=AsyncMock(return_value=location),
    )


class TestAirQualityTool:
    async def test_implicit_location_and_exact_indexes(self) -> None:
        client = MagicMock()
        client.get_air_quality = AsyncMock(
            return_value={
                "region_code": "fr",
                "date_time": "2026-08-21T09:00:00Z",
                "indexes": [{"code": "uaqi", "aqi": 77, "category": "Good air quality"}],
            }
        )
        with _patch_language(), _patch_implicit():
            result = await _tool(GetAirQualityTool).execute_api_call(client, uuid4())

        client.get_air_quality.assert_awaited_once_with(lat=48.85, lon=2.35, language="fr")
        assert result["success"] is True
        assert result["indexes"][0]["aqi"] == 77

    async def test_explicit_location_is_geocoded(self) -> None:
        client = MagicMock()
        client.get_air_quality = AsyncMock(return_value={"indexes": [], "region_code": ""})
        with (
            _patch_language(),
            patch(
                "src.domains.agents.tools.environment_tools.forward_geocode",
                new=AsyncMock(return_value=(45.76, 4.83, "Lyon", "FR")),
            ),
        ):
            result = await _tool(GetAirQualityTool).execute_api_call(
                client, uuid4(), location="Lyon"
            )

        client.get_air_quality.assert_awaited_once_with(lat=45.76, lon=4.83, language="fr")
        assert result["location_label"] == "Lyon"

    async def test_no_resolvable_location_is_a_clear_error(self) -> None:
        client = MagicMock()
        with _patch_language(), _patch_implicit(lat=None):
            result = await _tool(GetAirQualityTool).execute_api_call(client, uuid4())
        assert result["success"] is False
        assert result["error"] == "location_required"


class TestPollenForecastTool:
    async def test_days_passthrough_and_structured_days(self) -> None:
        client = MagicMock()
        client.get_pollen_forecast = AsyncMock(
            return_value={
                "region_code": "FR",
                "days": [{"date": "2026-08-21", "types": [{"code": "GRASS", "index_value": 3}]}],
            }
        )
        with _patch_language(), _patch_implicit():
            result = await _tool(GetPollenForecastTool).execute_api_call(client, uuid4(), days=5)

        client.get_pollen_forecast.assert_awaited_once_with(
            lat=48.85, lon=2.35, days=5, language="fr"
        )
        assert result["success"] is True
        assert result["days"][0]["types"][0]["code"] == "GRASS"
