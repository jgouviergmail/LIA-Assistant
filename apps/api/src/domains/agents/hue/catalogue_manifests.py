"""
Catalogue manifests for Philips Hue smart lighting tools.

Defines tool and agent manifests for the Smart Planner catalogue.
Semantic keywords are multilingual (en, fr, de, es, it, zh).
"""

from datetime import UTC, datetime

from src.domains.agents.constants import AGENT_HUE, CONTEXT_DOMAIN_HUE
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# AGENT MANIFEST
# ============================================================================

hue_agent_manifest = AgentManifest(
    name=AGENT_HUE,
    description="Philips Hue smart lighting control agent",
    tools=[
        "list_hue_lights_tool",
        "control_hue_light_tool",
        "list_hue_rooms_tool",
        "control_hue_room_tool",
        "list_hue_scenes_tool",
        "activate_hue_scene_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=15000,
    prompt_version="v1",
    owner_team="Team Agents",
    version="1.0.0",
    updated_at=datetime(2026, 3, 20, tzinfo=UTC),
)

# ============================================================================
# SHARED PARAMETERS
# ============================================================================

_LIGHT_NAME_PARAM = ParameterSchema(
    name="light_name_or_id",
    type="string",
    required=True,
    description="Name or ID of the light (e.g., 'Bedroom lamp', 'Living room').",
)

_ROOM_NAME_PARAM = ParameterSchema(
    name="room_name_or_id",
    type="string",
    required=True,
    description="Name or ID of the room (e.g., 'Living room', 'Kitchen').",
)

_SCENE_NAME_PARAM = ParameterSchema(
    name="scene_name_or_id",
    type="string",
    required=True,
    description="Name or ID of the scene (e.g., 'Movie', 'Relax', 'Energize').",
)

_ON_PARAM = ParameterSchema(
    name="on",
    type="boolean",
    required=False,
    description="Turn on (true) or off (false). Leave empty to keep current state.",
)

_BRIGHTNESS_PARAM = ParameterSchema(
    name="brightness",
    type="integer",
    required=False,
    description="Brightness 0-100%. Leave empty to keep current.",
)

_COLOR_PARAM = ParameterSchema(
    name="color",
    type="string",
    required=False,
    description="Color name (red, blue, warm_white) or CIE 'x,y'. Leave empty to keep current.",
)

# ============================================================================
# 1. LIST HUE LIGHTS
# ============================================================================

list_hue_lights_catalogue_manifest = ToolManifest(
    name="list_hue_lights_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: list_hue_lights_tool** - List all Philips Hue lights with state.\n"
        "Returns light names, IDs, on/off, brightness, color.\n"
        "**Use for**: 'What lights are on?', 'Show my lights', 'List Hue bulbs'."
    ),
    semantic_keywords=[
        "list all smart lights hue",
        "show my lights status",
        "what lights are on",
        "quelles lumières sont allumées",
        "liste mes ampoules hue",
        "zeige meine Hue Lichter",
        "mostrar luces inteligentes",
        "mostra luci hue",
        "显示所有灯泡",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(path="lights", type="array", description="List of lights"),
        OutputFieldSchema(path="lights[].name", type="string", description="Light name"),
        OutputFieldSchema(path="lights[].is_on", type="boolean", description="On/off state"),
        OutputFieldSchema(path="lights[].brightness", type="number", description="Brightness %"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=500, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name", "is_on", "brightness"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="💡", i18n_key="list_hue_lights", visible=True, category="tool"),
)

# ============================================================================
# 2. CONTROL HUE LIGHT
# ============================================================================

control_hue_light_catalogue_manifest = ToolManifest(
    name="control_hue_light_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: control_hue_light_tool** - Control a specific Hue light.\n"
        "Turn on/off, adjust brightness (0-100%), change color.\n"
        "**Use for**: 'Turn on bedroom light', 'Dim the lamp', 'Set light to blue'."
    ),
    semantic_keywords=[
        "turn on off hue light",
        "dim the light brightness",
        "change light color to blue red",
        "allume éteins la lumière",
        "règle la luminosité",
        "change la couleur",
        "Licht einschalten ausschalten",
        "enciende apaga la luz",
        "accendi spegni la luce",
        "开关灯",
    ],
    parameters=[_LIGHT_NAME_PARAM, _ON_PARAM, _BRIGHTNESS_PARAM, _COLOR_PARAM],
    outputs=[
        OutputFieldSchema(path="name", type="string", description="Light name"),
        OutputFieldSchema(path="on", type="boolean", description="New state"),
        OutputFieldSchema(path="brightness", type="number", description="New brightness"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=200, est_cost_usd=0.001, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name", "on", "brightness"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="💡", i18n_key="control_hue_light", visible=True, category="tool"
    ),
)

# ============================================================================
# 3. LIST HUE ROOMS
# ============================================================================

list_hue_rooms_catalogue_manifest = ToolManifest(
    name="list_hue_rooms_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: list_hue_rooms_tool** - List all Philips Hue rooms.\n"
        "Returns room names, IDs, and device counts.\n"
        "**Use for**: 'What rooms do I have?', 'Show my rooms'."
    ),
    semantic_keywords=[
        "list hue rooms zones",
        "show my rooms",
        "what rooms are configured",
        "quelles pièces ai-je",
        "liste mes pièces hue",
        "zeige meine Räume",
        "mostrar habitaciones",
        "显示房间",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(path="rooms", type="array", description="List of rooms"),
        OutputFieldSchema(path="rooms[].name", type="string", description="Room name"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name", "children"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏠", i18n_key="list_hue_rooms", visible=True, category="tool"),
)

# ============================================================================
# 4. CONTROL HUE ROOM
# ============================================================================

control_hue_room_catalogue_manifest = ToolManifest(
    name="control_hue_room_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: control_hue_room_tool** - Control all lights in a room.\n"
        "Turn on/off and adjust brightness for entire room.\n"
        "**Use for**: 'Turn on living room', 'Dim the bedroom', 'Lights off in kitchen'."
    ),
    semantic_keywords=[
        "turn on off room lights",
        "dim the room brightness",
        "allume éteins le salon la chambre",
        "éclairage de la pièce",
        "Raum Licht einschalten",
        "enciende apaga la habitación",
        "accendi spegni la stanza",
        "开关房间灯",
    ],
    parameters=[_ROOM_NAME_PARAM, _ON_PARAM, _BRIGHTNESS_PARAM],
    outputs=[
        OutputFieldSchema(path="name", type="string", description="Room name"),
        OutputFieldSchema(path="on", type="boolean", description="New state"),
        OutputFieldSchema(path="brightness", type="number", description="New brightness"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=200, est_cost_usd=0.001, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name", "on", "brightness"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏠", i18n_key="control_hue_room", visible=True, category="tool"),
)

# ============================================================================
# 5. LIST HUE SCENES
# ============================================================================

list_hue_scenes_catalogue_manifest = ToolManifest(
    name="list_hue_scenes_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: list_hue_scenes_tool** - List available Philips Hue scenes.\n"
        "Returns scene names and IDs.\n"
        "**Use for**: 'What scenes are available?', 'Show my scenes'."
    ),
    semantic_keywords=[
        "list hue scenes ambiances",
        "show available scenes",
        "what scenes do I have",
        "quelles scènes sont disponibles",
        "liste mes ambiances hue",
        "zeige meine Szenen",
        "mostrar escenas disponibles",
        "显示场景",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(path="scenes", type="array", description="List of scenes"),
        OutputFieldSchema(path="scenes[].name", type="string", description="Scene name"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🎬", i18n_key="list_hue_scenes", visible=True, category="tool"),
)

# ============================================================================
# 6. ACTIVATE HUE SCENE
# ============================================================================

activate_hue_scene_catalogue_manifest = ToolManifest(
    name="activate_hue_scene_tool",
    agent=AGENT_HUE,
    description=(
        "**Tool: activate_hue_scene_tool** - Activate a Philips Hue scene.\n"
        "Applies preconfigured lighting settings.\n"
        "**Use for**: 'Activate movie mode', 'Set relax scene', 'Ambiance lecture'."
    ),
    semantic_keywords=[
        "activate hue scene ambiance",
        "set scene mode",
        "movie relax concentrate scene",
        "active la scène ambiance",
        "mode film lecture détente",
        "Szene aktivieren",
        "activar escena modo",
        "attiva scena",
        "激活场景",
    ],
    parameters=[_SCENE_NAME_PARAM],
    outputs=[
        OutputFieldSchema(path="name", type="string", description="Activated scene name"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=150, est_cost_usd=0.001, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key=CONTEXT_DOMAIN_HUE,
    reference_examples=["name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🎬", i18n_key="activate_hue_scene", visible=True, category="tool"
    ),
)
