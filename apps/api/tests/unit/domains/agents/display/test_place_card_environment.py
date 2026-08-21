"""Air quality on the place card (2026-08).

Rendered with the same honesty rules as the weather card: the provider's own
localized category (Google's universal index is inverted vs EPA), and a
category alone when the national index ships no number.
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.place_card import PlaceCard

pytestmark = pytest.mark.unit


def _ctx() -> RenderContext:
    return RenderContext(viewport="desktop", language="fr", timezone="Europe/Paris")


def _place(**extra: object) -> dict:
    base = {
        "name": "Parc des Buttes-Chaumont",
        "address": "1 Rue Botzaris, 75019 Paris",
        "types": ["park"],
    }
    base.update(extra)
    return base


class TestPlaceAirQualityRendering:
    def test_category_without_a_number_renders(self) -> None:
        html = PlaceCard().render(
            _place(aqi=None, aqi_category="Moyen", aqi_label="IQA (FR)", has_air_quality=True),
            _ctx(),
            with_wrapper=False,
        )
        assert "Moyen" in html
        assert "IQA (FR)" in html
        assert "None" not in html

    def test_value_renders_with_its_own_category(self) -> None:
        html = PlaceCard().render(
            _place(
                aqi=66,
                aqi_category="Bonne qualité",
                aqi_label="Universal AQI",
                has_air_quality=True,
            ),
            _ctx(),
            with_wrapper=False,
        )
        assert "66" in html
        assert "Bonne qualité" in html

    def test_place_without_enrichment_is_unchanged(self) -> None:
        html = PlaceCard().render(_place(), _ctx(), with_wrapper=False)
        assert "Qualité de l" not in html
