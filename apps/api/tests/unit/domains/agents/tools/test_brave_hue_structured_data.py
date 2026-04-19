"""Tests for ``structured_data`` on Brave Search and Philips Hue tools.

These tools historically leaked domain data into ``metadata`` (debug field)
instead of ``structured_data`` (queryable field). This test suite enforces
the INTELLIPLANNER B+ contract where:

* ``structured_data`` carries queryable entities (``braves``, ``rooms``,
  ``scenes``, action results) aligned with ``$steps.<step_id>.<key>``.
* ``metadata`` is reserved for debug/observability fields (counts, types,
  cache flags).
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.tools.brave_tools import BraveSearchToolImpl
from src.domains.agents.tools.hue_tools import (
    ActivateHueSceneTool,
    ControlHueLightTool,
    ControlHueRoomTool,
    ListHueLightsTool,
    ListHueRoomsTool,
    ListHueScenesTool,
)


def _brave_raw_results() -> list[dict[str, Any]]:
    return [
        {"title": "Result 1", "url": "https://a.example", "description": "desc1"},
        {"title": "Result 2", "url": "https://b.example", "description": "desc2"},
    ]


class TestBraveStructuredData:
    """Brave Search exposes ``braves`` list in ``structured_data``."""

    def test_brave_search_exposes_braves_in_structured_data(self) -> None:
        tool = BraveSearchToolImpl(tool_name="brave_search", operation="web_search")
        tool_result: dict[str, Any] = {
            "success": True,
            "data": {
                "query": "python",
                "endpoint": "web",
                "results": _brave_raw_results(),
                "total": 2,
                "requested_count": 5,
            },
        }

        output = tool.format_registry_response(tool_result)

        assert "braves" in output.structured_data
        assert len(output.structured_data["braves"]) == 2
        assert output.structured_data["count"] == 2
        assert output.structured_data["query"] == "python"
        assert output.structured_data["endpoint"] == "web"

    def test_brave_no_longer_leaks_results_into_metadata(self) -> None:
        tool = BraveSearchToolImpl(tool_name="brave_search", operation="web_search")
        tool_result: dict[str, Any] = {
            "success": True,
            "data": {
                "query": "python",
                "endpoint": "web",
                "results": _brave_raw_results(),
                "total": 2,
                "requested_count": 5,
            },
        }

        output = tool.format_registry_response(tool_result)

        assert "braves" not in output.metadata


class TestHueListToolsStructuredData:
    """List* Hue tools expose their entities via ``structured_data``."""

    def test_list_rooms_exposes_rooms(self) -> None:
        tool = ListHueRoomsTool(tool_name="list_hue_rooms", operation="list_rooms")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "rooms": [
                    {
                        "id": "r1",
                        "metadata": {"name": "Living room"},
                        "children": [{"rid": "l1"}, {"rid": "l2"}],
                    },
                    {
                        "id": "r2",
                        "metadata": {"name": "Bedroom"},
                        "children": [{"rid": "l3"}],
                    },
                ]
            },
        }

        output = tool.format_registry_response(result)

        assert "rooms" in output.structured_data
        assert output.structured_data["count"] == 2
        names = {r["name"] for r in output.structured_data["rooms"]}
        assert names == {"Living room", "Bedroom"}

    def test_list_scenes_exposes_scenes(self) -> None:
        tool = ListHueScenesTool(tool_name="list_hue_scenes", operation="list_scenes")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "scenes": [
                    {
                        "id": "s1",
                        "metadata": {"name": "Sunset"},
                        "group": {"rid": "r1"},
                    },
                    {
                        "id": "s2",
                        "metadata": {"name": "Concentrate"},
                        "group": {"rid": "r2"},
                    },
                ]
            },
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["count"] == 2
        ids = {s["scene_id"] for s in output.structured_data["scenes"]}
        assert ids == {"s1", "s2"}

    def test_list_lights_exposes_count_alongside_registry(self) -> None:
        tool = ListHueLightsTool(tool_name="list_hue_lights", operation="list_lights")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "lights": [
                    {
                        "id": "l1",
                        "metadata": {"name": "Lamp"},
                        "on": {"on": True},
                        "dimming": {"brightness": 80.0},
                    },
                    {
                        "id": "l2",
                        "metadata": {"name": "Ceiling"},
                        "on": {"on": False},
                    },
                ]
            },
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["count"] == 2
        assert output.structured_data["on_count"] == 1
        # Registry items remain the source of truth for the UI
        assert len(output.registry_updates) == 2


class TestHueControlToolsStructuredData:
    """Action-oriented Hue tools expose the action payload."""

    def test_control_light_exposes_action_payload(self) -> None:
        tool = ControlHueLightTool(tool_name="control_hue_light", operation="control_light")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "light_id": "l1",
                "name": "Lamp",
                "on": True,
                "brightness": 75,
                "color": None,
                "api_result": {},
            },
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["action"] == "control_light"
        assert output.structured_data["success"] is True
        assert output.structured_data["light_id"] == "l1"
        assert output.structured_data["on"] is True
        assert output.structured_data["brightness"] == 75

    def test_control_light_failure_exposes_success_false(self) -> None:
        tool = ControlHueLightTool(tool_name="control_hue_light", operation="control_light")
        result: dict[str, Any] = {
            "success": False,
            "error": "Light not found",
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["action"] == "control_light"
        assert output.structured_data["success"] is False

    def test_control_room_exposes_action_payload(self) -> None:
        tool = ControlHueRoomTool(tool_name="control_hue_room", operation="control_room")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "room_id": "r1",
                "name": "Living room",
                "on": False,
                "brightness": None,
                "api_result": {},
            },
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["action"] == "control_room"
        assert output.structured_data["room_id"] == "r1"
        assert output.structured_data["on"] is False

    def test_activate_scene_exposes_action_payload(self) -> None:
        tool = ActivateHueSceneTool(tool_name="activate_hue_scene", operation="activate_scene")
        result: dict[str, Any] = {
            "success": True,
            "data": {
                "scene_id": "s1",
                "name": "Sunset",
                "api_result": {},
            },
        }

        output = tool.format_registry_response(result)

        assert output.structured_data["action"] == "activate_scene"
        assert output.structured_data["scene_id"] == "s1"
        assert output.structured_data["name"] == "Sunset"
