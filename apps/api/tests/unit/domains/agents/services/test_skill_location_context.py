"""Tests for the skill-runner location context (ADR-137 follow-up).

The production failure being pinned: the skill sub-agent had no location
context, so "montre-moi où je suis" produced Google Maps searches for the
literal strings "ma position" and "France" (run ``77ae2a29``, 2026-07-21).

The resolution deliberately goes through ``resolve_location`` — these tests
feed it a REAL config (browser geolocation is read straight from
``LiaRuntimeContext.browser_context``), mocking only the home lookup that would hit the
database.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.skill_location_context import (
    LOCATION_UNKNOWN_VALUE,
    resolve_user_location_for_prompt,
)
from src.domains.agents.tools.location_resolution import ResolvedLocation, resolve_location
from tests.helpers.runtime_context import (
    installed_runtime_context,
    make_contextless_tool_runtime,
    make_tool_runtime,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_database_lookups():
    """Keep the cascade hermetic: both stored sources answer "nothing".

    These tests used to short-circuit before the database because the config
    carried no user id. Identity is now mandatory on the run context (ADR-231),
    so the lookups are actually reached — and a unit test must not depend on a
    database being unreachable. Tests that need a stored position patch the same
    seams again, and the inner patch wins.
    """
    with (
        patch(
            "src.domains.agents.tools.location_resolution.get_user_home_location",
            return_value=None,
        ),
        patch(
            "src.domains.agents.tools.location_resolution.get_user_last_known_location",
            return_value=None,
        ),
    ):
        yield


@contextmanager
def _run(geolocation: dict[str, float] | None = None) -> Iterator[dict[str, Any]]:
    """Install the run context and yield the (plumbing-only) RunnableConfig.

    The browser geolocation reaches the resolver through
    ``LiaRuntimeContext.browser_context`` (ADR-231). No user is installed, so the
    home lookup short-circuits before touching the database.
    """
    browser_context = {"geolocation": geolocation} if geolocation is not None else None
    with installed_runtime_context(browser_context=browser_context):
        yield {"configurable": {}}


class TestResolveUserLocationForPrompt:
    async def test_browser_geolocation_renders_coordinates(self) -> None:
        """Precise browser coordinates come out as a plain 'lat,lon' value."""
        with _run({"lat": 48.610301, "lon": 2.474812}) as config:
            value = await resolve_user_location_for_prompt(config, "montre moi où je suis", "fr")
        assert value == "48.61030,2.47481"

    async def test_no_source_renders_unknown_sentinel(self) -> None:
        with _run() as config:
            value = await resolve_user_location_for_prompt(config, "montre moi une carte", "fr")
        assert value == LOCATION_UNKNOWN_VALUE

    async def test_home_address_is_appended_to_coordinates(self) -> None:
        """When home is the resolved source, its address travels with it."""
        home = ResolvedLocation(lat=48.85, lon=2.35, source="home", address="1 rue de Paris")
        with (
            _run() as config,
            patch(
                "src.domains.agents.tools.location_resolution.get_user_home_location",
                return_value=home,
            ),
        ):
            value = await resolve_user_location_for_prompt(config, "quel temps fait-il", "fr")
        assert value == "48.85000,2.35000 (1 rue de Paris)"

    async def test_last_known_source_carries_its_age_marker(self) -> None:
        """A persisted position renders with the exact marker the prompt
        documents — the model is told to state the age, never claim 'live'."""
        from datetime import UTC, datetime

        last_known = ResolvedLocation(
            lat=43.60450,
            lon=1.44420,
            source="last_known",
            address=None,
            as_of=datetime(2026, 8, 16, 9, 30, tzinfo=UTC),
        )
        with (
            _run() as config,
            patch(
                "src.domains.agents.tools.location_resolution.get_user_last_known_location",
                return_value=last_known,
            ),
        ):
            value = await resolve_user_location_for_prompt(config, "montre moi où je suis", "fr")
        assert value == "43.60450,1.44420 (last_known 2026-08-16T09:30Z)"

    async def test_resolution_failure_degrades_to_unknown(self) -> None:
        """A resolver crash must degrade the context, never kill the turn.

        Patch target: the helper imports ``resolve_location`` lazily inside
        the function body, so the source module is the right seam.
        """
        with (
            _run({"lat": 1.0, "lon": 2.0}) as config,
            patch(
                "src.domains.agents.tools.location_resolution.resolve_location",
                side_effect=RuntimeError("boom"),
            ),
        ):
            value = await resolve_user_location_for_prompt(config, "où je suis", "fr")
        assert value == LOCATION_UNKNOWN_VALUE


class TestResolveLocationQueryBranch:
    """Regression: LocationType.QUERY fell through to a silent (None, None)."""

    async def test_query_phrase_resolves_browser_geolocation(self) -> None:
        runtime = make_tool_runtime(
            browser_context={"geolocation": {"lat": 48.6103, "lon": 2.47481}}
        )
        location, fallback = await resolve_location(runtime, "où suis-je ?", "fr")
        assert location is not None
        assert location.source == "browser"
        assert fallback is None

    async def test_query_phrase_without_source_gets_fallback_message(self) -> None:
        """Before the fix this returned (None, None): no location AND no
        user-facing hint — the model was left to improvise."""
        runtime = make_contextless_tool_runtime()
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

    def test_prompt_documents_the_last_known_age_marker(self) -> None:
        """Same pinning for the last_known suffix: the Python side renders
        ``(last_known <timestamp>)`` and the prompt must teach the model what
        that marker means (state the age, never claim a live position)."""
        template = load_prompt("skill_react_agent_prompt")
        assert "last_known" in template
