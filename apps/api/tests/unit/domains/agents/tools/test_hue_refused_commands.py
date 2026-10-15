"""A Hue command the bridge cannot address is a FAILURE, never a success saying it failed.

Measured in the code on 2026-10-14: the three Hue commands answered a name the
bridge does not hold with ``UnifiedToolOutput.data_success`` carrying
``{"success": False}`` inside its structured data. Every reader of the verdict
reads ``output.success`` (``core.tool_outcome.explicit_success``), so the effect
register settled the act SUCCEEDED, the ReAct performed-actions directive told
the response model it had switched the light, the tool metrics counted a
success, and the pipeline read the refusal as an action confirmation.

Contract pinned here, for the light, the room and the scene:
- the refusal reaches its reader as ``success=False`` with ``NOT_FOUND``, the
  code the runtime failures directive words as « it does not exist there; quote
  the tool's message, which says what DOES exist »;
- the message keeps naming what the bridge does hold;
- nothing is written to the bridge when the target is unknown.
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
)

_BRIDGE_LIGHTS = [
    {"id": "light-1", "metadata": {"name": "Desk"}},
    {"id": "light-2", "metadata": {"name": "Hall"}},
]
_BRIDGE_ROOMS = [{"id": "room-1", "metadata": {"name": "Kitchen"}, "children": []}]
_BRIDGE_SCENES = [{"id": "scene-1", "metadata": {"name": "Reading"}}]


def _client() -> MagicMock:
    client = MagicMock()
    client.list_lights = AsyncMock(return_value=_BRIDGE_LIGHTS)
    client.list_rooms = AsyncMock(return_value=_BRIDGE_ROOMS)
    client.list_scenes = AsyncMock(return_value=_BRIDGE_SCENES)
    client.update_light = AsyncMock(return_value={})
    client.control_room = AsyncMock(return_value={})
    client.activate_scene = AsyncMock(return_value={})
    return client


_CASES = [
    pytest.param(
        ControlHueLightTool(tool_name="control_hue_light", operation="control_light"),
        {"light_name_or_id": "Ceiling", "on": True},
        "update_light",
        ("Ceiling", "Desk", "Hall"),
        id="light",
    ),
    pytest.param(
        ControlHueRoomTool(tool_name="control_hue_room", operation="control_room"),
        {"room_name_or_id": "Garage", "on": False},
        "control_room",
        ("Garage", "Kitchen"),
        id="room",
    ),
    pytest.param(
        ActivateHueSceneTool(tool_name="activate_hue_scene", operation="activate_scene"),
        {"scene_name_or_id": "Party"},
        "activate_scene",
        ("Party", "Reading"),
        id="scene",
    ),
]


class TestUnknownTargetIsRefused:
    @pytest.mark.parametrize(("tool", "kwargs", "write_call", "named"), _CASES)
    async def test_the_payload_declares_the_refusal_and_nothing_is_written(
        self,
        tool: Any,
        kwargs: dict[str, Any],
        write_call: str,
        named: tuple[str, ...],
    ) -> None:
        client = _client()

        payload = await tool.execute_api_call(client, uuid4(), **kwargs)

        assert explicit_success(payload) is False
        assert payload["error_code"] == ToolErrorCode.NOT_FOUND.value
        assert all(name in payload["error"] for name in named)
        getattr(client, write_call).assert_not_awaited()

    @pytest.mark.parametrize(("tool", "kwargs", "write_call", "named"), _CASES)
    async def test_the_reader_receives_a_not_found_failure(
        self,
        tool: Any,
        kwargs: dict[str, Any],
        write_call: str,
        named: tuple[str, ...],
    ) -> None:
        payload = await tool.execute_api_call(_client(), uuid4(), **kwargs)

        output = tool.format_registry_response(payload)

        assert output.success is False
        assert explicit_success(output) is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value
        assert all(name in output.message for name in named)
        assert output.registry_updates == {}


class TestKnownTargetStillSucceeds:
    async def test_a_light_the_bridge_holds_is_switched(self) -> None:
        tool = ControlHueLightTool(tool_name="control_hue_light", operation="control_light")
        client = _client()

        payload = await tool.execute_api_call(client, uuid4(), light_name_or_id="desk", on=True)
        output = tool.format_registry_response(payload)

        client.update_light.assert_awaited_once()
        assert output.success is True
        assert output.structured_data["light_id"] == "light-1"
