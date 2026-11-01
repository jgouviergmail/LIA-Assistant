"""The lights of the « Tools » section, by the person's own hand (ADR-369).

The bridge is opened by its connector's type through the door (no session held
while it answers, ADR-304). One read draws it whole — rooms, lights, scenes;
a lamp belongs to the room whose devices own it. A change sends what the lamp
accepts: a lamp is read first when the change needs to know what it can do
(dimming, colour, temperature), and what it cannot do is refused before
anything is sent; a temperature is held to the lamp's own range (repaired,
never refused: ADR-184). Every change is a state SET — the same request twice
leaves the same light — so a lost answer is « try again », never « outcome
unknown » (``act=False``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.light_colours import hex_to_xy, xy_to_hex
from src.domains.workbench.schemas.lights import (
    LightChange,
    LightsView,
    LightView,
    RoomChange,
    RoomView,
    SceneRecall,
    SceneView,
)

_TOOL = WorkbenchTool.LIGHTS


async def read_lights(user_id: UUID) -> LightsView:
    """The account's bridge: its rooms, lights and scenes."""
    async with open_tool_client(_TOOL, user_id) as opened:
        bridge = opened.client
        async with provider_call(_TOOL, "list", act=False):
            lights = await bridge.list_lights()
            rooms = await bridge.list_rooms()
            scenes = await bridge.list_scenes()
    owners: dict[str | None, str] = {
        device: room["id"] for room in rooms for device in _devices(room)
    }
    views = [_light(light, owners.get(_owner(light))) for light in lights]
    return LightsView(
        rooms=[_room(room, views) for room in rooms],
        lights=views,
        scenes=[_scene(scene) for scene in scenes],
    )


async def change_light(user_id: UUID, change: LightChange) -> None:
    """Set one lamp's state; what it cannot do is refused unsent."""
    async with open_tool_client(_TOOL, user_id) as opened:
        bridge = opened.client
        async with provider_call(_TOOL, "light", act=False):
            mirek = change.mirek
            if change.brightness is not None or change.color_hex or mirek is not None:
                lamp = _light(await bridge.get_light(change.light_id), None)
                mirek = _within_reach(lamp, change)
            await bridge.update_light(
                change.light_id,
                on=change.on,
                brightness=change.brightness,
                color_xy=hex_to_xy(change.color_hex) if change.color_hex else None,
                color_temperature_mirek=mirek,
            )


async def change_room(user_id: UUID, change: RoomChange) -> None:
    """Set every light of one room."""
    async with open_tool_client(_TOOL, user_id) as opened:
        bridge = opened.client
        async with provider_call(_TOOL, "room", act=False):
            await bridge.control_room(change.room_id, on=change.on, brightness=change.brightness)


async def recall_scene(user_id: UUID, recall: SceneRecall) -> None:
    """Show one scene."""
    async with open_tool_client(_TOOL, user_id) as opened:
        bridge = opened.client
        async with provider_call(_TOOL, "scene", act=False):
            await bridge.activate_scene(recall.scene_id)


def _within_reach(lamp: LightView, change: LightChange) -> int | None:
    """The change's temperature held to the lamp's range; refuse what it lacks."""
    lacks_dimming = change.brightness is not None and lamp.brightness is None
    lacks_colour = change.color_hex is not None and not lamp.supports_color
    lacks_temperature = change.mirek is not None and lamp.mirek_min is None
    if lacks_dimming or lacks_colour or lacks_temperature:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    if change.mirek is None or lamp.mirek_min is None or lamp.mirek_max is None:
        return change.mirek
    return min(lamp.mirek_max, max(lamp.mirek_min, change.mirek))


def _owner(light: Mapping[str, Any]) -> str | None:
    owner = light.get("owner") or {}
    return owner.get("rid") if isinstance(owner, Mapping) else None


def _devices(room: Mapping[str, Any]) -> Sequence[str]:
    children = room.get("children") or []
    return [
        child["rid"]
        for child in children
        if isinstance(child, Mapping) and child.get("rtype") == "device" and child.get("rid")
    ]


def _name(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata") or {}
    return str(metadata.get("name") or "") if isinstance(metadata, Mapping) else ""


def _light(light: Mapping[str, Any], room_id: str | None) -> LightView:
    dimming = light.get("dimming") or {}
    colour = (light.get("color") or {}).get("xy") or None
    temperature = light.get("color_temperature") or {}
    schema = temperature.get("mirek_schema") or {}
    return LightView(
        id=str(light.get("id") or ""),
        name=_name(light),
        room_id=room_id,
        on=bool((light.get("on") or {}).get("on")),
        brightness=dimming.get("brightness") if dimming else None,
        supports_color=colour is not None,
        color_hex=xy_to_hex(colour["x"], colour["y"]) if colour else None,
        mirek=temperature.get("mirek") if temperature.get("mirek_valid", True) else None,
        mirek_min=schema.get("mirek_minimum"),
        mirek_max=schema.get("mirek_maximum"),
    )


def _room(room: Mapping[str, Any], lights: Sequence[LightView]) -> RoomView:
    members = [light for light in lights if light.room_id == room.get("id")]
    return RoomView(
        id=str(room.get("id") or ""),
        name=_name(room),
        light_ids=[light.id for light in members],
        on=any(light.on for light in members),
    )


def _scene(scene: Mapping[str, Any]) -> SceneView:
    group = scene.get("group") or {}
    status = scene.get("status") or {}
    return SceneView(
        id=str(scene.get("id") or ""),
        name=_name(scene),
        room_id=group.get("rid") if isinstance(group, Mapping) else None,
        active=isinstance(status, Mapping) and status.get("active", "inactive") != "inactive",
    )
