"""Behavioral tests for RouteCard (10.8% covered — the lowest of the card layer).

RouteCard renders the output of ``get_route_tool``: distance/duration, traffic,
turn-by-turn steps, and — the risky part — public-transit steps whose line
COLORS come straight from the Google Routes API. Those colors are injected into
an inline ``style`` attribute, which the cross-component escaping contract does
not exercise (it never populates a transit step), so this module pins them
directly, plus the branchy formatting the card is made of.
"""

from html.parser import HTMLParser
from typing import Any

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.route_card import RouteCard

pytestmark = pytest.mark.unit


@pytest.fixture
def card() -> RouteCard:
    return RouteCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(language="fr")


class _AttrCollector(HTMLParser):
    """Collects attribute names and their values per tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.event_handlers: list[tuple[str, str]] = []
        self.style_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.event_handlers.append((tag, name.lower()))
            if name.lower() == "style" and value:
                self.style_values.append(value)

    handle_startendtag = handle_starttag


def _parse(html: str) -> _AttrCollector:
    collector = _AttrCollector()
    collector.feed(html)
    collector.close()
    return collector


# ============================================================================
# VALIDATION GATE
# ============================================================================


class TestRenderValidation:
    """A route with no destination is a validation failure → empty card."""

    def test_missing_destination_renders_nothing(self, card: RouteCard, ctx: RenderContext) -> None:
        assert card.render({"origin": "Paris"}, ctx) == ""

    def test_empty_destination_renders_nothing(self, card: RouteCard, ctx: RenderContext) -> None:
        assert card.render({"destination": ""}, ctx) == ""

    def test_nested_route_structure_is_accepted(self, card: RouteCard, ctx: RenderContext) -> None:
        """The tool may return ``{"route": {...}}`` or a flat dict."""
        nested = card.render({"route": {"destination": "Lyon"}}, ctx)
        flat = card.render({"destination": "Lyon"}, ctx)

        assert "Lyon" in nested
        assert "Lyon" in flat


# ============================================================================
# CORE RENDERING
# ============================================================================


class TestCoreRendering:
    ROUTE = {
        "origin": "Bastille",
        "destination": "Gare de Lyon",
        "travel_mode": "DRIVE",
        "distance_km": 4.2,
        "duration_minutes": 18,
        "traffic_conditions": "MODERATE",
    }

    def test_endpoints_are_shown(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(self.ROUTE, ctx)
        assert "Bastille" in html
        assert "Gare de Lyon" in html

    def test_distance_over_one_km_uses_kilometres(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        assert "4.2 km" in card.render(self.ROUTE, ctx)

    def test_distance_under_one_km_uses_metres(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render({**self.ROUTE, "distance_km": 0.45}, ctx)
        assert "450 m" in html
        assert "0.45 km" not in html

    def test_duration_is_formatted_when_not_provided(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        assert "18 min" in card.render(self.ROUTE, ctx)

    def test_provided_duration_format_is_preferred(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render({**self.ROUTE, "duration_formatted": "20 minutes"}, ctx)
        assert "20 minutes" in html

    def test_missing_origin_falls_back_to_my_location(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render({"destination": "Lyon"}, ctx)
        # "Ma position" (fr) — never an empty endpoint value
        assert "lia-route__endpoint-value" in html

    def test_maps_url_is_built_when_absent(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(self.ROUTE, ctx)
        assert "google.com/maps" in html


class TestDurationFormatting:
    @pytest.mark.parametrize(
        ("minutes", "language", "expected"),
        [
            (45, "fr", "45 min"),
            (45, "en", "45 min"),
            (45, "de", "45 Min."),
            (45, "zh-CN", "45分钟"),
            (90, "fr", "1h30"),
            (90, "en", "1h 30min"),
            (120, "fr", "2h"),
            (150, "zh-CN", "2小时30分钟"),
        ],
    )
    def test_localised_durations(
        self, card: RouteCard, minutes: int, language: str, expected: str
    ) -> None:
        assert card._format_duration(minutes, language) == expected


# ============================================================================
# TRANSIT STEP COLORS — the unescaped inline-style surface
# ============================================================================


class TestTransitStepColorSafety:
    """Transit line colors come from the Google API and land in a ``style`` attr."""

    def _route_with_transit(self, **transit: Any) -> dict[str, Any]:
        return {
            "destination": "Gare de Lyon",
            "origin": "Bastille",
            "steps": [
                {
                    "instruction": "Take the metro",
                    "distance_meters": 800,
                    "transit": {
                        "line_name": "M1",
                        "vehicle_type": "SUBWAY",
                        "departure_stop": "Bastille",
                        "arrival_stop": "Gare de Lyon",
                        "stop_count": 3,
                        **transit,
                    },
                }
            ],
        }

    def test_a_valid_hex_color_is_applied(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(self._route_with_transit(line_color="#00A", line_text_color="#FFF"), ctx)
        styles = " ".join(_parse(html).style_values)
        assert "#00A" in styles or "#00a" in styles

    def test_hex_color_without_hash_is_normalised(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render(self._route_with_transit(line_color="00AA00"), ctx)
        styles = " ".join(_parse(html).style_values)
        assert "#00AA00" in styles or "#00aa00" in styles

    def test_hostile_color_cannot_inject_an_event_handler(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        """Regression: ``#fff" onmouseover="alert(1)`` broke out of the style attr."""
        html = card.render(self._route_with_transit(line_color='#fff" onmouseover="alert(1)'), ctx)

        assert _parse(html).event_handlers == []
        assert "onmouseover" not in html.lower()

    def test_hostile_text_color_cannot_inject_an_event_handler(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render(
            self._route_with_transit(line_color="#fff", line_text_color='#000" onload="alert(1)'),
            ctx,
        )

        assert _parse(html).event_handlers == []

    def test_non_color_junk_does_not_reach_the_style(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render(self._route_with_transit(line_color="url(javascript:alert(1))"), ctx)
        styles = " ".join(_parse(html).style_values).lower()
        assert "javascript" not in styles

    def test_transit_step_renders_line_name_and_stops(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render(self._route_with_transit(line_color="#00A"), ctx)
        assert "M1" in html
        assert "Bastille" in html
        assert "Gare de Lyon" in html


# ============================================================================
# STEPS
# ============================================================================


class TestSteps:
    BASE = {"destination": "Lyon", "origin": "Paris"}

    def test_no_steps_means_no_collapsible(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(self.BASE, ctx)
        assert "lia-route__steps" not in html

    def test_regular_steps_are_rendered(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(
            {**self.BASE, "steps": [{"instruction": "Turn left", "distance_meters": 300}]}, ctx
        )
        assert "Turn left" in html

    def test_string_step_is_accepted(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render({**self.BASE, "steps": ["Head north"]}, ctx)
        assert "Head north" in html

    def test_steps_are_capped_and_a_more_indicator_is_shown(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        from src.core.config import settings

        many = [
            {"instruction": f"Step {i}", "distance_meters": 100}
            for i in range(settings.routes_max_steps + 5)
        ]
        html = card.render({**self.BASE, "steps": many}, ctx)

        # The full count is shown on the trigger, but the last steps are folded away.
        assert f"Step {settings.routes_max_steps + 4}" not in html

    def test_step_instruction_is_escaped(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(
            {**self.BASE, "steps": [{"instruction": "<script>alert(1)</script>"}]}, ctx
        )
        assert "<script>" not in html


# ============================================================================
# TRAFFIC & AVOIDANCES
# ============================================================================


class TestTrafficAndModifiers:
    BASE = {"destination": "Lyon", "origin": "Paris", "duration_minutes": 60}

    @pytest.mark.parametrize("condition", ["NORMAL", "LIGHT", "MODERATE", "HEAVY"])
    def test_every_traffic_condition_renders(
        self, card: RouteCard, ctx: RenderContext, condition: str
    ) -> None:
        html = card.render({**self.BASE, "traffic_conditions": condition}, ctx)
        assert isinstance(html, str)
        assert "lia-route" in html

    def test_avoidance_flags_produce_chips(self, card: RouteCard, ctx: RenderContext) -> None:
        html = card.render(
            {**self.BASE, "avoid_tolls": True, "avoid_highways": True, "avoid_ferries": True}, ctx
        )
        assert "lia-chip" in html

    def test_toll_info_row_is_shown_when_not_avoiding_tolls(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render({**self.BASE, "toll_info": {"formatted": "3,50 €"}}, ctx)
        assert "3,50" in html

    def test_toll_info_is_hidden_when_avoiding_tolls(
        self, card: RouteCard, ctx: RenderContext
    ) -> None:
        html = card.render(
            {**self.BASE, "avoid_tolls": True, "toll_info": {"formatted": "3,50 €"}}, ctx
        )
        assert "3,50" not in html
