"""What the assistant gains with the lights screen (ADR-369, lot 13).

The screen and the assistant reach the same bridge: a zone is found by name beside the rooms, a
room takes a colour, a scene plays in motion and a lamp that does not answer is said. A colour
nobody can read is refused, never sent as nothing and told as done (ADR-310).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.tool_outcome import explicit_success
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.hue_tools import (
    ActivateHueSceneTool,
    ControlHueLightTool,
    ControlHueRoomTool,
    ListHueLightsTool,
    ListHueRoomsTool,
)

pytestmark = pytest.mark.unit

_LIGHTS = [
    {
        "id": "light-1",
        "owner": {"rid": "device-1", "rtype": "device"},
        "metadata": {"name": "Desk"},
        "on": {"on": True},
    },
    {
        "id": "light-2",
        "owner": {"rid": "device-2", "rtype": "device"},
        "metadata": {"name": "Hall"},
        "on": {"on": False},
    },
]
_ROOMS = [{"id": "room-1", "metadata": {"name": "Kitchen"}, "children": [{"rid": "device-1"}]}]
_ZONES = [{"id": "zone-1", "metadata": {"name": "TV corner"}, "children": [{"rid": "light-1"}]}]
_SCENES = [{"id": "scene-1", "metadata": {"name": "Reading"}}]


def _client() -> MagicMock:
    client = MagicMock()
    client.list_lights = AsyncMock(return_value=_LIGHTS)
    client.list_rooms = AsyncMock(return_value=_ROOMS)
    client.list_zones = AsyncMock(return_value=_ZONES)
    client.list_scenes = AsyncMock(return_value=_SCENES)
    client.list_connectivity = AsyncMock(
        return_value=[
            {"owner": {"rid": "device-1"}, "status": "connected"},
            {"owner": {"rid": "device-2"}, "status": "connectivity_issue"},
        ]
    )
    client.update_light = AsyncMock(return_value={})
    client.control_room = AsyncMock(return_value={})
    client.activate_scene = AsyncMock(return_value={})
    return client


def _tool(kind: Any, name: str, operation: str) -> Any:
    tool = kind(tool_name=name, operation=operation)
    tool._fetch_language = AsyncMock(return_value="en")
    return tool


_ROOM = (ControlHueRoomTool, "control_hue_room", "control_room")


class TestAZone:
    async def test_it_is_listed_beside_the_rooms(self) -> None:
        tool = _tool(ListHueRoomsTool, "list_hue_rooms", "list_rooms")

        result = await tool.execute_api_call(_client(), uuid4())
        output = tool.format_registry_response(result)

        rooms = output.structured_data["rooms"]
        assert [(room["name"], room["kind"]) for room in rooms] == [
            ("Kitchen", "room"),
            ("TV corner", "zone"),
        ]
        assert "TV corner" in output.message

    async def test_it_is_found_by_its_name_and_reached_as_a_zone(self) -> None:
        client = _client()

        result = await _tool(*_ROOM).execute_api_call(
            client, uuid4(), room_name_or_id="tv corner", on=True
        )

        assert explicit_success(result)
        assert client.control_room.await_args.args == ("zone-1",)
        assert client.control_room.await_args.kwargs["group"] == "zone"

    async def test_a_room_is_still_reached_as_a_room(self) -> None:
        client = _client()

        await _tool(*_ROOM).execute_api_call(client, uuid4(), room_name_or_id="Kitchen", on=True)

        assert client.control_room.await_args.kwargs["group"] == "room"

    async def test_an_unknown_name_names_the_zones_too(self) -> None:
        client = _client()

        result = await _tool(*_ROOM).execute_api_call(
            client, uuid4(), room_name_or_id="Garage", on=True
        )

        assert not explicit_success(result)
        assert "TV corner" in str(result)
        client.control_room.assert_not_awaited()


class TestARoomsColour:
    async def test_it_is_sent_as_its_chromaticity_and_told(self) -> None:
        client = _client()
        tool = _tool(*_ROOM)

        result = await tool.execute_api_call(
            client, uuid4(), room_name_or_id="Kitchen", color="red"
        )
        output = tool.format_registry_response(result)

        assert client.control_room.await_args.kwargs["color_xy"] is not None
        assert output.structured_data["color"] == "red"
        assert "red" in output.message

    @pytest.mark.parametrize(
        ("tool", "target"),
        [
            (_ROOM, {"room_name_or_id": "Kitchen"}),
            (
                (ControlHueLightTool, "control_hue_light", "control_light"),
                {"light_name_or_id": "Desk"},
            ),
        ],
    )
    async def test_a_colour_nobody_can_read_is_refused_and_nothing_sent(
        self, tool: Any, target: dict[str, str]
    ) -> None:
        client = _client()

        result = await _tool(*tool).execute_api_call(
            client, uuid4(), color="the colour of joy", **target
        )

        assert not explicit_success(result)
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT
        client.control_room.assert_not_awaited()
        client.update_light.assert_not_awaited()


class TestASceneInMotion:
    @pytest.mark.parametrize(
        ("motion", "action"),
        [(None, "active"), (True, "dynamic_palette"), (False, "static")],
    )
    async def test_it_asks_what_the_person_said(self, motion: bool | None, action: str) -> None:
        client = _client()
        tool = _tool(ActivateHueSceneTool, "activate_hue_scene", "activate_scene")

        await tool.execute_api_call(client, uuid4(), scene_name_or_id="Reading", motion=motion)

        client.activate_scene.assert_awaited_once_with("scene-1", action=action)


class TestALampThatDoesNotAnswer:
    async def test_it_is_said_by_name(self) -> None:
        tool = _tool(ListHueLightsTool, "list_hue_lights", "list_lights")

        result = await tool.execute_api_call(_client(), uuid4())
        output = tool.format_registry_response(result)

        assert output.structured_data["unreachable"] == ["Hall"]
        assert "Hall" in output.message

    async def test_nothing_is_said_when_every_lamp_answers(self) -> None:
        client = _client()
        client.list_connectivity = AsyncMock(return_value=[])
        tool = _tool(ListHueLightsTool, "list_hue_lights", "list_lights")

        result = await tool.execute_api_call(client, uuid4())
        output = tool.format_registry_response(result)

        assert output.structured_data["unreachable"] == []
