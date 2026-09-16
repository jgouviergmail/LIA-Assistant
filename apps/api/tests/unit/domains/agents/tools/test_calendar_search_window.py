"""The calendar listing's default window is ONE published setting.

``get_events_tool()`` with no end bound covered ``now + timedelta(days=30)``
written in the tool, while the Apple client carried a second default
(``-30 / +90`` days) that no caller could reach — every one of the twelve
callers of ``list_events`` passes both bounds (measured 2026-09-16). One
authority: ``calendar_tool_default_days_ahead``, read by the tool and
published on every surface the models read (ADR-184: a bound the code
enforces is a bound the prompt publishes, from one constant).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.core.config import settings
from src.domains.agents.calendar.catalogue_manifests import get_events_catalogue_manifest
from src.domains.agents.tools import calendar_tools
from src.domains.agents.tools.calendar_tools import SearchEventsTool, get_events_tool
from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)


def _tool() -> SearchEventsTool:
    tool = SearchEventsTool()
    tool.runtime = MagicMock()
    return tool


def _client(spec: type) -> MagicMock:
    client = MagicMock(spec=spec)
    client.list_events = AsyncMock(return_value={"items": []})
    client.connector_service = MagicMock()
    client.connector_type = MagicMock()
    return client


@contextlib.contextmanager
def _frozen_turn() -> Any:
    """A fixed clock, neutral preferences, the primary calendar."""
    with (
        patch.object(calendar_tools, "now_utc", return_value=_NOW),
        patch.object(
            calendar_tools,
            "get_user_preferences",
            new=AsyncMock(return_value=("UTC", "fr", None)),
        ),
        patch.object(
            calendar_tools, "resolve_calendar_name", new=AsyncMock(return_value="primary")
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults.read_owner_preference_name",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


class TestTheWindowIsTheSetting:
    async def test_a_listing_with_no_end_covers_the_configured_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "calendar_tool_default_days_ahead", 7)
        client = _client(GoogleCalendarClient)

        with _frozen_turn():
            await _tool().execute_api_call(client, uuid4())

        kwargs = client.list_events.await_args.kwargs
        assert kwargs["time_min"] == _NOW.isoformat()
        assert kwargs["time_max"] == (_NOW + timedelta(days=7)).isoformat()

    async def test_the_default_is_read_from_settings_not_a_literal(self) -> None:
        client = _client(GoogleCalendarClient)

        with _frozen_turn():
            await _tool().execute_api_call(client, uuid4())

        expected = (_NOW + timedelta(days=settings.calendar_tool_default_days_ahead)).isoformat()
        assert client.list_events.await_args.kwargs["time_max"] == expected

    async def test_an_explicit_end_is_kept(self) -> None:
        client = _client(GoogleCalendarClient)

        with _frozen_turn():
            await _tool().execute_api_call(client, uuid4(), time_max="2026-09-20T00:00:00Z")

        assert client.list_events.await_args.kwargs["time_max"].startswith("2026-09-20")


class TestTheClientNeverDecidesTheWindow:
    """Apple's client carries its own default range; the tool never lets it
    apply — both bounds always travel, whatever the provider."""

    async def test_apple_receives_both_bounds_like_google(self) -> None:
        client = _client(AppleCalendarClient)

        with _frozen_turn():
            await _tool().execute_api_call(client, uuid4())

        kwargs = client.list_events.await_args.kwargs
        assert kwargs["time_min"] == _NOW.isoformat()
        assert (
            kwargs["time_max"]
            == (_NOW + timedelta(days=settings.calendar_tool_default_days_ahead)).isoformat()
        )


def _react_tool() -> BaseTool:
    """The registered LangChain tool (the decorator's return type hides it)."""
    return cast(BaseTool, get_events_tool)


class TestTheWindowIsPublished:
    """What the tool enforces is what the two readers are told (ADR-184)."""

    def test_the_react_schema_names_the_configured_window(self) -> None:
        days = settings.calendar_tool_default_days_ahead
        schema = _react_tool().args_schema
        assert isinstance(schema, type) and issubclass(schema, BaseModel)
        field = schema.model_fields["time_max"]
        assert f"{days} days" in (field.description or "")

    def test_the_planner_manifest_names_the_configured_window(self) -> None:
        days = settings.calendar_tool_default_days_ahead
        time_max = next(p for p in get_events_catalogue_manifest.parameters if p.name == "time_max")
        assert f"{days} days" in time_max.description

    def test_no_surface_carries_the_old_literal(self) -> None:
        assert "30 days" not in _react_tool().description
        assert "30 days" not in get_events_catalogue_manifest.description
