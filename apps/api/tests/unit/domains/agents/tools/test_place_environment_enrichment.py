"""Air quality on a place detail card (2026-08).

"On va au parc cet après-midi ?" — the air quality AT THE PLACE is what
answers it, and the place detail already carries the coordinates. Scope is
deliberately narrow:

- DETAIL only, never list/search results: enriching a list of ten places
  would fire ten billed pairs of calls for a signal the user did not ask for;
- air quality only, no pollen: pollen is a regional daily figure already
  shown on the weather surfaces, whereas air quality varies per location;
- fail-quiet and cached, exactly like the weather enrichment.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import places_environment as places_env

pytestmark = pytest.mark.unit


class TestPlaceAirQuality:
    async def test_detail_gets_air_quality_from_its_coordinates(self) -> None:
        details: dict[str, Any] = {
            "name": "Parc des Buttes-Chaumont",
            "location": {"lat": 48.8799, "lon": 2.3831},
        }
        extras = {
            "aqi": None,
            "aqi_category": "Moyen",
            "aqi_label": "IQA (FR)",
            "has_air_quality": True,
            "pollen": [{"name": "Graminées", "category": "Élevé", "index": 4}],
        }
        with patch.object(
            places_env, "environment_extras_or_none", new=AsyncMock(return_value=extras)
        ) as fetch:
            await places_env.attach_place_air_quality(details, MagicMock(), uuid4(), "fr")

        assert details["aqi_category"] == "Moyen"
        assert details["aqi_label"] == "IQA (FR)"
        assert details["has_air_quality"] is True
        # Pollen is a regional daily figure — it belongs to the weather
        # surfaces, not to a venue card.
        assert "pollen" not in details
        # Coordinates of the PLACE, not of the user.
        assert fetch.await_args.args[2:4] == (48.8799, 2.3831)

    async def test_place_without_coordinates_is_skipped(self) -> None:
        details: dict[str, Any] = {"name": "Sans coordonnées"}
        with patch.object(places_env, "environment_extras_or_none", new=AsyncMock()) as fetch:
            await places_env.attach_place_air_quality(details, MagicMock(), uuid4(), "fr")
        fetch.assert_not_awaited()
        assert "aqi_category" not in details

    async def test_unusable_air_quality_leaves_the_card_untouched(self) -> None:
        details: dict[str, Any] = {"location": {"lat": 1.0, "lon": 2.0}}
        with patch.object(
            places_env,
            "environment_extras_or_none",
            new=AsyncMock(return_value={"has_air_quality": False, "aqi": None, "aqi_category": ""}),
        ):
            await places_env.attach_place_air_quality(details, MagicMock(), uuid4(), "fr")
        assert "aqi_category" not in details
        assert "has_air_quality" not in details

    async def test_failure_is_fail_quiet(self) -> None:
        details: dict[str, Any] = {"location": {"lat": 1.0, "lon": 2.0}}
        with patch.object(
            places_env,
            "environment_extras_or_none",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            await places_env.attach_place_air_quality(details, MagicMock(), uuid4(), "fr")
        assert "aqi_category" not in details
