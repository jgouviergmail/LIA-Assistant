"""Tests for the skill-runner location context (ADR-137 follow-up).

The production failure being pinned: the skill sub-agent had no location
context, so "montre-moi où je suis" produced Google Maps searches for the
literal strings "ma position" and "France" (run ``77ae2a29``, 2026-07-21).

The resolution deliberately goes through ``resolve_location`` — these tests
feed it a REAL config (browser geolocation is read straight from
``__browser_context``), mocking only the home lookup that would hit the
database.
"""

from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.skill_location_context import (
    LOCATION_UNKNOWN_VALUE,
    resolve_user_location_for_prompt,
)
from src.domains.agents.tools.runtime_helpers import ResolvedLocation, resolve_location

pytestmark = pytest.mark.unit


def _config(geolocation: dict[str, float] | None = None) -> dict[str, Any]:
    """A graph-shaped RunnableConfig; no ``user_id`` so the home lookup
    short-circuits before touching the database."""
    configurable: dict[str, Any] = {}
    if geolocation is not None:
        configurable["__browser_context"] = {"geolocation": geolocation}
    return {"configurable": configurable}


class TestResolveUserLocationForPrompt:
    async def test_browser_geolocation_renders_coordinates(self) -> None:
        """Precise browser coordinates come out as a plain 'lat,lon' value."""
        value = await resolve_user_location_for_prompt(
            _config({"lat": 48.610301, "lon": 2.474812}),
            "montre moi où je suis",
            "fr",
        )
        assert value == "48.61030,2.47481"

    async def test_no_source_renders_unknown_sentinel(self) -> None:
        value = await resolve_user_location_for_prompt(_config(), "montre moi une carte", "fr")
        assert value == LOCATION_UNKNOWN_VALUE

    async def test_home_address_is_appended_to_coordinates(self) -> None:
        """When home is the resolved source, its address travels with it."""
        home = ResolvedLocation(lat=48.85, lon=2.35, source="home", address="1 rue de Paris")
        with patch(
            "src.domains.agents.tools.runtime_helpers.get_user_home_location",
            return_value=home,
        ):
            value = await resolve_user_location_for_prompt(_config(), "quel temps fait-il", "fr")
        assert value == "48.85000,2.35000 (1 rue de Paris)"

    async def test_resolution_failure_degrades_to_unknown(self) -> None:
        """A resolver crash must degrade the context, never kill the turn.

        Patch target: the helper imports ``resolve_location`` lazily inside
        the function body, so the source module is the right seam.
        """
        with patch(
            "src.domains.agents.tools.runtime_helpers.resolve_location",
            side_effect=RuntimeError("boom"),
        ):
            value = await resolve_user_location_for_prompt(
                _config({"lat": 1.0, "lon": 2.0}), "où je suis", "fr"
            )
        assert value == LOCATION_UNKNOWN_VALUE


class TestResolveLocationQueryBranch:
    """Regression: LocationType.QUERY fell through to a silent (None, None)."""

    async def test_query_phrase_resolves_browser_geolocation(self) -> None:
        from langchain.tools import ToolRuntime

        runtime = ToolRuntime(
            state=None,
            context=None,
            config=_config({"lat": 48.6103, "lon": 2.47481}),
            stream_writer=lambda _: None,
            tool_call_id=None,
            store=None,
        )
        location, fallback = await resolve_location(runtime, "où suis-je ?", "fr")
        assert location is not None
        assert location.source == "browser"
        assert fallback is None

    async def test_query_phrase_without_source_gets_fallback_message(self) -> None:
        """Before the fix this returned (None, None): no location AND no
        user-facing hint — the model was left to improvise."""
        from langchain.tools import ToolRuntime

        runtime = ToolRuntime(
            state=None,
            context=None,
            config=_config(),
            stream_writer=lambda _: None,
            tool_call_id=None,
            store=None,
        )
        location, fallback = await resolve_location(runtime, "où suis-je ?", "fr")
        assert location is None
        assert fallback is not None


class TestPromptContract:
    """The prompt file and the wiring must agree on variables and sentinel."""

    def test_prompt_formats_with_exactly_the_wired_variables(self) -> None:
        """Mirrors the prompt_vars built in response_node's runner branch —
        a variable added on either side without the other breaks here."""
        template = load_prompt("skill_react_agent_prompt")
        formatted = template.format(
            current_datetime="2026-07-21 18:00",
            skills_catalog="<available_skills/>",
            user_language="fr",
            user_location="48.61030,2.47481",
        )
        assert "UserLocation: 48.61030,2.47481" in formatted

    def test_prompt_documents_the_unknown_sentinel(self) -> None:
        """The prompt's behavioral rules reference the exact sentinel the
        Python side renders — the coupling is deliberate and pinned."""
        template = load_prompt("skill_react_agent_prompt")
        assert f'"{LOCATION_UNKNOWN_VALUE}"' in template
