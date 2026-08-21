"""Behavioral tests for PlaceCard — the audit-added display branches.

Pins the four display gaps found by the 2026-08 Places audit: permanently /
temporarily closed status (a closed-forever place rendered as a normal one),
the feature badges (paid Enterprise+Atmosphere data whose card branch was
dead), the parking section, and the price range chip.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.place_card import PlaceCard

pytestmark = pytest.mark.unit


@pytest.fixture
def card() -> PlaceCard:
    return PlaceCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(language="fr")


def _render(card: PlaceCard, ctx: RenderContext, **data: Any) -> str:
    payload: dict[str, Any] = {"name": "Chez Test", "address": "1 rue du Test, Paris"}
    payload.update(data)
    return card.render(payload, ctx, with_wrapper=False)


class TestBusinessStatus:
    def test_permanently_closed_badge_is_rendered(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, business_status="CLOSED_PERMANENTLY")
        assert "Définitivement fermé" in html

    def test_temporarily_closed_badge_is_rendered(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, business_status="CLOSED_TEMPORARILY")
        assert "Temporairement fermé" in html

    def test_permanently_closed_suppresses_open_now_chip(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        """A stale openNow=True must never contradict a permanent closure."""
        html = _render(card, ctx, business_status="CLOSED_PERMANENTLY", open_now=True)
        assert "Définitivement fermé" in html
        assert "Ouvert" not in html

    def test_no_status_renders_no_closure_badge(self, card: PlaceCard, ctx: RenderContext) -> None:
        html = _render(card, ctx, open_now=True)
        assert "fermé" not in html.lower()


class TestFeatureBadges:
    def test_feature_keys_render_localized_badges(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, features=["dine_in", "serves_vegetarian_food"])
        assert "Sur place" in html
        assert "Végétarien" in html


class TestParkingSection:
    def test_true_parking_options_render_localized_labels(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(
            card,
            ctx,
            parkingOptions={
                "freeParkingLot": True,
                "paidStreetParking": True,
                "valetParking": False,
            },
        )
        assert "Parking gratuit" in html
        assert "Stationnement payant dans la rue" in html
        assert "voiturier" not in html.lower()

    def test_all_false_parking_options_render_nothing(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, parkingOptions={"valetParking": False})
        assert "Parking" not in html


class TestPriceRangeChip:
    def test_bounded_range_renders_with_currency_symbol(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, price_range={"start": 10, "end": 25, "currency": "EUR"})
        assert "10–25 €" in html

    def test_open_ended_range_renders_lower_bound_only(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, price_range={"start": 100, "end": None, "currency": "EUR"})
        assert "100 €" in html
        assert "–" not in html.split("100 €")[0][-10:]

    def test_price_range_wins_over_price_level(self, card: PlaceCard, ctx: RenderContext) -> None:
        """An exact range beats the legacy €€ approximation when both exist."""
        html = _render(
            card,
            ctx,
            price_range={"start": 10, "end": 25, "currency": "EUR"},
            priceLevel="PRICE_LEVEL_MODERATE",
        )
        assert "10–25 €" in html
        assert "€€" not in html


class TestPrimaryType:
    def test_primary_type_display_name_wins_over_type_mapping(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        html = _render(card, ctx, primary_type="Pizzéria", types=["restaurant"])
        assert "Pizzéria" in html

    def test_primary_type_is_escaped_exactly_once(
        self, card: PlaceCard, ctx: RenderContext
    ) -> None:
        """render_chip escapes its text — pre-escaping here would double-escape."""
        html = _render(card, ctx, primary_type="Fish & Chips")
        assert "Fish &amp; Chips" in html
        assert "&amp;amp;" not in html
