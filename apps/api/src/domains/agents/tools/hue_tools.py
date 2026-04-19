"""
LangChain v1 tools for Philips Hue smart lighting operations.

Provides 6 tools for controlling Philips Hue lights, rooms, and scenes
via the Hue Bridge CLIP v2 API:
- list_hue_lights_tool: List all lights with state
- control_hue_light_tool: Control a specific light (on/off, brightness, color)
- list_hue_rooms_tool: List all rooms with their lights
- control_hue_room_tool: Control all lights in a room
- list_hue_scenes_tool: List available scenes
- activate_hue_scene_tool: Activate a scene

Architecture:
- Uses ConnectorTool base class (same as OAuth/Apple tools)
- Credentials retrieved via connector_service.get_hue_credentials()
- Client registered in ClientRegistry for caching
- Data Registry integration for rich frontend rendering

Created: 2026-03-20
Reference: docs/connectors/CONNECTOR_PHILIPS_HUE.md
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.domains.agents.constants import AGENT_HUE, CONTEXT_DOMAIN_HUE
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.philips_hue_client import (
    PhilipsHueClient,
    resolve_color,
)
from src.domains.connectors.models import ConnectorType
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Context Type Registration (Data Registry)
# =============================================================================


class HueLightItem(BaseModel):
    """Schema for Hue light data in context registry."""

    light_id: str
    name: str
    is_on: bool
    brightness: float | None = None
    color_xy: tuple[float, float] | None = None
    room: str | None = None


ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_HUE,
        agent_name=AGENT_HUE,
        item_schema=HueLightItem,
        primary_id_field="light_id",
        display_name_field="name",
        reference_fields=["name", "is_on", "brightness", "room"],
        icon="💡",
    )
)


# =============================================================================
# Helper: Name-to-ID resolution
# =============================================================================


def _find_resource_by_name(
    resources: list[dict[str, Any]],
    name_or_id: str,
) -> dict[str, Any] | None:
    """
    Find a Hue resource by exact name or ID.

    Performs strict matching only — no fuzzy or partial matching.
    The planner is responsible for resolving user descriptions to exact
    device names via IoT discovery context injection.

    Search order:
    1. Exact ID match
    2. Case-insensitive exact name match on metadata.name

    Args:
        resources: List of Hue API resource dicts.
        name_or_id: Resource name or ID to search for.

    Returns:
        Matching resource dict, or None if not found.
    """
    # Try exact ID match first
    for r in resources:
        if r.get("id") == name_or_id:
            return r

    # Try case-insensitive name match
    search = name_or_id.strip().lower()
    for r in resources:
        resource_name = r.get("metadata", {}).get("name", "").strip().lower()
        if resource_name == search:
            return r

    return None


# =============================================================================
# Tool Class: List Hue Lights
# =============================================================================


class ListHueLightsTool(ConnectorTool[PhilipsHueClient]):
    """Tool for listing Philips Hue lights with their current state."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list lights API call."""
        lights = await client.list_lights()
        return {"success": True, "data": {"lights": lights}}

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format lights as Data Registry UnifiedToolOutput."""
        lights = result.get("data", {}).get("lights", [])
        registry_updates: dict[str, RegistryItem] = {}

        for light in lights:
            item_id = light.get("id", "")
            name = light.get("metadata", {}).get("name", "")
            is_on = light.get("on", {}).get("on", False)
            brightness = light.get("dimming", {}).get("brightness")

            registry_updates[item_id] = RegistryItem(
                id=generate_registry_id(RegistryItemType.HUE_LIGHT, item_id),
                type=RegistryItemType.HUE_LIGHT,
                payload={
                    "light_id": item_id,
                    "name": name,
                    "is_on": is_on,
                    "brightness": brightness,
                    "room": light.get("owner", {}).get("rid", ""),
                },
                meta=RegistryItemMeta(
                    source=AGENT_HUE,
                    domain=CONTEXT_DOMAIN_HUE,
                    tool_name="list_hue_lights",
                ),
            )

        summary_parts = []
        on_count = sum(1 for lt in lights if lt.get("on", {}).get("on", False))
        summary_parts.append(f"{len(lights)} light(s) found")
        if on_count:
            summary_parts.append(f"{on_count} currently on")

        return UnifiedToolOutput.data_success(
            message=", ".join(summary_parts),
            registry_updates=registry_updates,
            structured_data={
                "count": len(lights),
                "on_count": on_count,
            },
            metadata={"type": "hue_lights", "count": len(lights)},
        )


# =============================================================================
# Tool Class: Control Hue Light
# =============================================================================


class ControlHueLightTool(ConnectorTool[PhilipsHueClient]):
    """Tool for controlling a specific Philips Hue light."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute light control API call."""
        light_name_or_id: str = kwargs.get("light_name_or_id", "")
        on: bool | None = kwargs.get("on")
        brightness: int | None = kwargs.get("brightness")
        color: str | None = kwargs.get("color")

        # Resolve name → ID
        lights = await client.list_lights()
        target = _find_resource_by_name(lights, light_name_or_id)
        if not target:
            available = [lt.get("metadata", {}).get("name", "?") for lt in lights]
            return {
                "success": False,
                "error": f"Light '{light_name_or_id}' not found. Available: {available}",
            }

        light_id = target["id"]
        light_name = target.get("metadata", {}).get("name", light_id)

        # Build update params
        color_xy = resolve_color(color) if color else None
        brightness_float = float(brightness) if brightness is not None else None

        result = await client.update_light(
            light_id,
            on=on,
            brightness=brightness_float,
            color_xy=color_xy,
        )

        return {
            "success": True,
            "data": {
                "light_id": light_id,
                "name": light_name,
                "on": on,
                "brightness": brightness,
                "color": color,
                "api_result": result,
            },
        }

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format light control result."""
        if not result.get("success"):
            return UnifiedToolOutput.data_success(
                message=result.get("error", "Light control failed"),
                structured_data={"action": "control_light", "success": False},
                metadata={"type": "hue_control", "success": False},
            )

        data = result.get("data", {})
        parts = [f"'{data.get('name')}':"]
        if data.get("on") is not None:
            parts.append("on" if data["on"] else "off")
        if data.get("brightness") is not None:
            parts.append(f"brightness {data['brightness']}%")
        if data.get("color"):
            parts.append(f"color {data['color']}")

        return UnifiedToolOutput.data_success(
            message=" ".join(parts),
            structured_data={
                "action": "control_light",
                "success": True,
                "light_id": data.get("light_id"),
                "name": data.get("name"),
                "on": data.get("on"),
                "brightness": data.get("brightness"),
                "color": data.get("color"),
            },
            metadata={"type": "hue_control", "light_id": data.get("light_id")},
        )


# =============================================================================
# Tool Class: List Hue Rooms
# =============================================================================


class ListHueRoomsTool(ConnectorTool[PhilipsHueClient]):
    """Tool for listing Philips Hue rooms."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list rooms API call."""
        rooms = await client.list_rooms()
        return {"success": True, "data": {"rooms": rooms}}

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format rooms list."""
        rooms = result.get("data", {}).get("rooms", [])

        summary_parts = []
        structured_rooms: list[dict[str, Any]] = []
        for room in rooms:
            name = room.get("metadata", {}).get("name", "?")
            room_id = room.get("id", "")
            children_count = len(room.get("children", []))
            summary_parts.append(f"{name} ({children_count} devices)")
            structured_rooms.append(
                {
                    "room_id": room_id,
                    "name": name,
                    "children_count": children_count,
                }
            )

        return UnifiedToolOutput.data_success(
            message=(
                f"{len(rooms)} room(s): {', '.join(summary_parts)}" if rooms else "No rooms found"
            ),
            structured_data={"rooms": structured_rooms, "count": len(rooms)},
            metadata={"type": "hue_rooms", "count": len(rooms)},
        )


# =============================================================================
# Tool Class: Control Hue Room
# =============================================================================


class ControlHueRoomTool(ConnectorTool[PhilipsHueClient]):
    """Tool for controlling all lights in a Philips Hue room."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute room control API call."""
        room_name_or_id: str = kwargs.get("room_name_or_id", "")
        on: bool | None = kwargs.get("on")
        brightness: int | None = kwargs.get("brightness")

        # Resolve name → ID
        rooms = await client.list_rooms()
        target = _find_resource_by_name(rooms, room_name_or_id)
        if not target:
            available = [r.get("metadata", {}).get("name", "?") for r in rooms]
            return {
                "success": False,
                "error": f"Room '{room_name_or_id}' not found. Available: {available}",
            }

        room_id = target["id"]
        room_name = target.get("metadata", {}).get("name", room_id)

        brightness_float = float(brightness) if brightness is not None else None
        result = await client.control_room(room_id, on=on, brightness=brightness_float)

        return {
            "success": True,
            "data": {
                "room_id": room_id,
                "name": room_name,
                "on": on,
                "brightness": brightness,
                "api_result": result,
            },
        }

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format room control result."""
        if not result.get("success"):
            return UnifiedToolOutput.data_success(
                message=result.get("error", "Room control failed"),
                structured_data={"action": "control_room", "success": False},
                metadata={"type": "hue_room_control", "success": False},
            )

        data = result.get("data", {})
        parts = [f"Room '{data.get('name')}':"]
        if data.get("on") is not None:
            parts.append("all on" if data["on"] else "all off")
        if data.get("brightness") is not None:
            parts.append(f"brightness {data['brightness']}%")

        return UnifiedToolOutput.data_success(
            message=" ".join(parts),
            structured_data={
                "action": "control_room",
                "success": True,
                "room_id": data.get("room_id"),
                "name": data.get("name"),
                "on": data.get("on"),
                "brightness": data.get("brightness"),
            },
            metadata={"type": "hue_room_control", "room_id": data.get("room_id")},
        )


# =============================================================================
# Tool Class: List Hue Scenes
# =============================================================================


class ListHueScenesTool(ConnectorTool[PhilipsHueClient]):
    """Tool for listing Philips Hue scenes."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list scenes API call."""
        scenes = await client.list_scenes()
        return {"success": True, "data": {"scenes": scenes}}

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format scenes list."""
        scenes = result.get("data", {}).get("scenes", [])
        names = [s.get("metadata", {}).get("name", "?") for s in scenes]
        structured_scenes = [
            {
                "scene_id": s.get("id", ""),
                "name": s.get("metadata", {}).get("name", "?"),
                "group": s.get("group", {}).get("rid"),
            }
            for s in scenes
        ]

        return UnifiedToolOutput.data_success(
            message=f"{len(scenes)} scene(s): {', '.join(names)}" if scenes else "No scenes found",
            structured_data={"scenes": structured_scenes, "count": len(scenes)},
            metadata={"type": "hue_scenes", "count": len(scenes)},
        )


# =============================================================================
# Tool Class: Activate Hue Scene
# =============================================================================


class ActivateHueSceneTool(ConnectorTool[PhilipsHueClient]):
    """Tool for activating a Philips Hue scene."""

    connector_type = ConnectorType.PHILIPS_HUE
    client_class = PhilipsHueClient
    registry_enabled = True

    async def execute_api_call(
        self,
        client: PhilipsHueClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute scene activation API call."""
        scene_name_or_id: str = kwargs.get("scene_name_or_id", "")

        # Resolve name → ID
        scenes = await client.list_scenes()
        target = _find_resource_by_name(scenes, scene_name_or_id)
        if not target:
            available = [s.get("metadata", {}).get("name", "?") for s in scenes]
            return {
                "success": False,
                "error": f"Scene '{scene_name_or_id}' not found. Available: {available}",
            }

        scene_id = target["id"]
        scene_name = target.get("metadata", {}).get("name", scene_id)

        result = await client.activate_scene(scene_id)

        return {
            "success": True,
            "data": {
                "scene_id": scene_id,
                "name": scene_name,
                "api_result": result,
            },
        }

    def format_registry_response(
        self,
        result: dict[str, Any],
    ) -> UnifiedToolOutput:
        """Format scene activation result."""
        if not result.get("success"):
            return UnifiedToolOutput.data_success(
                message=result.get("error", "Scene activation failed"),
                structured_data={"action": "activate_scene", "success": False},
                metadata={"type": "hue_scene", "success": False},
            )

        data = result.get("data", {})
        return UnifiedToolOutput.data_success(
            message=f"Scene '{data.get('name')}' activated",
            structured_data={
                "action": "activate_scene",
                "success": True,
                "scene_id": data.get("scene_id"),
                "name": data.get("name"),
            },
            metadata={"type": "hue_scene", "scene_id": data.get("scene_id")},
        )


# =============================================================================
# Tool Instances (Singletons)
# =============================================================================

_list_hue_lights_impl = ListHueLightsTool(
    tool_name="list_hue_lights",
    operation="list_lights",
)

_control_hue_light_impl = ControlHueLightTool(
    tool_name="control_hue_light",
    operation="control_light",
)

_list_hue_rooms_impl = ListHueRoomsTool(
    tool_name="list_hue_rooms",
    operation="list_rooms",
)

_control_hue_room_impl = ControlHueRoomTool(
    tool_name="control_hue_room",
    operation="control_room",
)

_list_hue_scenes_impl = ListHueScenesTool(
    tool_name="list_hue_scenes",
    operation="list_scenes",
)

_activate_hue_scene_impl = ActivateHueSceneTool(
    tool_name="activate_hue_scene",
    operation="activate_scene",
)


# =============================================================================
# LangChain Tool Functions (@tool decorated)
# =============================================================================


@tool
@track_tool_metrics(
    tool_name="list_hue_lights",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def list_hue_lights_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    List all Philips Hue lights with their current state.

    Returns light names, IDs, on/off state, brightness, and color.
    Use this to discover available lights before controlling them.
    """
    return await _list_hue_lights_impl.execute(runtime)


@tool
@track_tool_metrics(
    tool_name="control_hue_light",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def control_hue_light_tool(
    light_name_or_id: Annotated[
        str,
        "Name or ID of the light to control (e.g., 'Bedroom lamp', 'Living room')",
    ],
    on: Annotated[
        bool | None,
        "Turn light on (true) or off (false). Leave empty to keep current state.",
    ] = None,
    brightness: Annotated[
        int | None,
        "Brightness percentage 0-100 (0=off, 100=max). Leave empty to keep current.",
    ] = None,
    color: Annotated[
        str | None,
        "Color name (red, blue, warm_white, etc.) or CIE 'x,y' coordinates. Leave empty to keep current.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Control a specific Philips Hue light.

    Can turn on/off, adjust brightness (0-100%), and change color.
    Use list_hue_lights_tool first to find available light names.
    Supported colors: red, blue, green, yellow, orange, purple, pink,
    warm_white, cool_white, white (also in French, German, Spanish).
    """
    return await _control_hue_light_impl.execute(
        runtime,
        light_name_or_id=light_name_or_id,
        on=on,
        brightness=brightness,
        color=color,
    )


@tool
@track_tool_metrics(
    tool_name="list_hue_rooms",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def list_hue_rooms_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    List all Philips Hue rooms with their devices.

    Returns room names, IDs, and the number of devices in each room.
    Use this to find room names before controlling them.
    """
    return await _list_hue_rooms_impl.execute(runtime)


@tool
@track_tool_metrics(
    tool_name="control_hue_room",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def control_hue_room_tool(
    room_name_or_id: Annotated[
        str,
        "Name or ID of the room to control (e.g., 'Living room', 'Bedroom')",
    ],
    on: Annotated[
        bool | None,
        "Turn all lights on (true) or off (false). Leave empty to keep current.",
    ] = None,
    brightness: Annotated[
        int | None,
        "Brightness percentage 0-100 for all lights. Leave empty to keep current.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Control all lights in a Philips Hue room at once.

    Adjusts all lights in the specified room simultaneously.
    Use list_hue_rooms_tool first to find available room names.
    """
    return await _control_hue_room_impl.execute(
        runtime,
        room_name_or_id=room_name_or_id,
        on=on,
        brightness=brightness,
    )


@tool
@track_tool_metrics(
    tool_name="list_hue_scenes",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def list_hue_scenes_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    List all available Philips Hue scenes.

    Returns scene names and IDs. Scenes are preconfigured lighting
    setups (e.g., 'Movie', 'Relax', 'Concentrate').
    """
    return await _list_hue_scenes_impl.execute(runtime)


@tool
@track_tool_metrics(
    tool_name="activate_hue_scene",
    agent_name=AGENT_HUE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def activate_hue_scene_tool(
    scene_name_or_id: Annotated[
        str,
        "Name or ID of the scene to activate (e.g., 'Movie', 'Relax', 'Energize')",
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Activate a Philips Hue scene by name or ID.

    Scenes apply preconfigured light settings to a room.
    Use list_hue_scenes_tool first to find available scene names.
    """
    return await _activate_hue_scene_impl.execute(
        runtime,
        scene_name_or_id=scene_name_or_id,
    )
