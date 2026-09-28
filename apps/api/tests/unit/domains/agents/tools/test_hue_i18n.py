"""Tests for Philips Hue tools internationalisation.

Validates that Hue tool messages are rendered in the user's language by:

1. ``ConnectorTool._fetch_language`` falling back safely when ``self.runtime``
   is absent (no crash, answers the declared language — ADR-323).
2. ``ConnectorTool._language_from_result`` reading the language stashed by
   ``execute_api_call`` via ``_LANGUAGE_RESULT_KEY``.
3. ``format_registry_response`` of each Hue tool honouring the language code
   when producing user-facing messages.

These tests do NOT hit the Philips Hue Bridge or the database — they exercise
only the pure formatters + the base class helpers.
"""

from __future__ import annotations

import contextvars
from typing import Any

import pytest

from src.core.config import settings
from src.core.i18n import _, language_scope
from src.domains.agents.tools.hue_tools import (
    ActivateHueSceneTool,
    ControlHueLightTool,
    ControlHueRoomTool,
    ListHueLightsTool,
    ListHueRoomsTool,
    ListHueScenesTool,
)


@pytest.fixture
def list_lights_tool() -> ListHueLightsTool:
    return ListHueLightsTool(tool_name="list_hue_lights", operation="list_lights")


class TestLanguageHelpers:
    """Base ConnectorTool language helpers."""

    def test_language_from_result_reads_stashed_key(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        result = {"success": True, list_lights_tool._LANGUAGE_RESULT_KEY: "de"}
        assert list_lights_tool._language_from_result(result) == "de"

    def test_language_from_result_falls_back_to_the_declared_language_when_missing(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        with language_scope("de"):
            assert list_lights_tool._language_from_result({}) == "de"

    def test_language_from_result_with_nothing_declared_reads_the_instance_default(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        # A fresh context holds no declaration, whatever the runner's own holds;
        # a copy of the current one would carry a scope an earlier fixture left.
        answer = contextvars.Context().run(list_lights_tool._language_from_result, {})
        assert answer == settings.default_language

    def test_language_from_result_ignores_non_string(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        """Non-string values under the key must not break the contract."""
        result = {list_lights_tool._LANGUAGE_RESULT_KEY: 42}
        with language_scope("it"):
            assert list_lights_tool._language_from_result(result) == "it"

    def test_language_from_result_ignores_empty_string(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        result = {list_lights_tool._LANGUAGE_RESULT_KEY: ""}
        with language_scope("it"):
            assert list_lights_tool._language_from_result(result) == "it"

    @pytest.mark.asyncio
    async def test_fetch_language_no_runtime_returns_the_declared_language(
        self, list_lights_tool: ListHueLightsTool
    ) -> None:
        """When runtime is unset, fetch_language answers the declared language (ADR-323)."""
        list_lights_tool.runtime = None
        with language_scope("es"):
            assert await list_lights_tool._fetch_language() == "es"


class TestListHueLightsFormatting:
    """ListHueLightsTool.format_registry_response produces localised strings."""

    @staticmethod
    def _sample_result(language: str) -> dict[str, Any]:
        lights = [
            {
                "id": "light-1",
                "metadata": {"name": "Living room"},
                "on": {"on": True},
                "dimming": {"brightness": 80},
            },
            {
                "id": "light-2",
                "metadata": {"name": "Kitchen"},
                "on": {"on": False},
            },
        ]
        return {
            "success": True,
            "data": {"lights": lights},
            ListHueLightsTool._LANGUAGE_RESULT_KEY: language,
        }

    def test_french_reads_the_french_catalog(self, list_lights_tool: ListHueLightsTool) -> None:
        output = list_lights_tool.format_registry_response(self._sample_result("fr"))
        # The catalogs are guarded complete (ADR-323): French never falls back
        # to the English msgid.
        french = _("{count} light(s) found", "fr").format(count=2)
        assert french != "2 light(s) found"
        assert french in output.message

    def test_english_renders_the_source_sentence(self, list_lights_tool: ListHueLightsTool) -> None:
        output = list_lights_tool.format_registry_response(self._sample_result("en"))
        # English is the source language: its catalog translates every msgid
        # to itself.
        assert "2 light(s) found" in output.message

    def test_registry_contains_every_light(self, list_lights_tool: ListHueLightsTool) -> None:
        output = list_lights_tool.format_registry_response(self._sample_result("fr"))
        assert len(output.registry_updates) == 2


class TestControlHueLightErrorMessage:
    """ControlHueLightTool returns a localised error on failed lookup."""

    def test_not_found_error_uses_language_from_result(self) -> None:
        tool = ControlHueLightTool(tool_name="control_hue_light", operation="control_light")
        result: dict[str, Any] = {
            "success": False,
            "error": "Light 'foo' not found. Available: bar, baz",
            tool._LANGUAGE_RESULT_KEY: "en",
        }
        output = tool.format_registry_response(result)
        assert "foo" in output.message
        assert "bar" in output.message


class TestOtherHueToolsContract:
    """Smoke tests: every Hue tool can format a response without crashing."""

    @pytest.mark.parametrize(
        ("tool_cls", "fake_result"),
        [
            (
                ListHueRoomsTool,
                {"success": True, "data": {"rooms": []}},
            ),
            (
                ControlHueRoomTool,
                {
                    "success": True,
                    "data": {
                        "room_id": "r1",
                        "name": "Living",
                        "on": True,
                        "brightness": 75,
                    },
                },
            ),
            (
                ListHueScenesTool,
                {"success": True, "data": {"scenes": []}},
            ),
            (
                ActivateHueSceneTool,
                {
                    "success": True,
                    "data": {"scene_id": "s1", "name": "Relax"},
                },
            ),
        ],
    )
    def test_format_registry_response_does_not_crash(
        self, tool_cls: type, fake_result: dict[str, Any]
    ) -> None:
        tool = tool_cls(tool_name=tool_cls.__name__, operation="test")
        output = tool.format_registry_response(fake_result)
        assert output.message is not None
