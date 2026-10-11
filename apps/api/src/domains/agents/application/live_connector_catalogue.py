"""Reviewed non-secret Live settings and bounded provider choice discovery."""

from src.domains.agents.application.live_connector_schemas import LiveConnectorChangeRequest
from src.domains.agents.application.live_options_schemas import LiveOptionsRead
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

LIVE_CONNECTOR_READ_MANIFEST = ToolManifest(
    name="get_lia_live_connector_settings_tool",
    agent="setting_agent",
    description="Read saved Live providers, active provider, remembered model settings, voice, thinking level, durations, indicative session budget and instance bounds. No provider lookup, credential, current session state or mutation.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="connectors", type="array", description="Saved account Live connectors"
        ),
        OutputFieldSchema(
            path="configuration", type="object", description="Effective instance bounds"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_live_connectors",
    semantic_keywords=[
        "my live model",
        "my live voice",
        "live session duration",
        "live session budget",
    ],
    display=DisplayMetadata(
        emoji="🎙️", i18n_key="get_lia_live_connector_settings", category="tool"
    ),
)
LIVE_CONNECTOR_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_live_connector_settings_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation of a saved Live provider and non-secret settings delta. Omitted fields are preserved; switching model restores its remembered settings. A never-configured model requires an explicit available voice and any required thinking level; never submit a fallback voice. Selecting the provider also selects future sessions' provider. No save or provider probe before confirmation. Confirmation may briefly connect on the user's key and consume provider quota. Current session retains its model; standby wake may read saved settings. Budget is indicative, not a platform quota.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Owned provider and explicit settings delta",
            schema=LiveConnectorChangeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Exact pending human confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_live_connectors",
    semantic_keywords=[
        "change live model",
        "change live voice",
        "change live provider",
        "change live session limit",
    ],
    display=DisplayMetadata(
        emoji="🎙️", i18n_key="update_lia_live_connector_settings", category="tool"
    ),
)
LIVE_OPTIONS_READ_MANIFEST = ToolManifest(
    name="get_lia_live_options_tool",
    agent="setting_agent",
    description="Read a bounded page of models or voices from this account's saved active Live keys. Voices require the provider. Selectable models have declared pricing or vendor billing; unpriced entries are visible but not selectable, with scope all owned providers. Preserve published/discovered/portal voice provenance; an empty portal list is intentional. Use next_cursor to continue after the last shown item; restart if the catalogue changes. May consume vendor listing API quota, never opens a session or synthesizes audio.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Bounded choice listing and opaque continuation",
            schema=LiveOptionsRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="choices", type="array", description="Bounded choices with availability"
        ),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Opaque continuation, null at end",
        ),
        OutputFieldSchema(
            path="details", type="object", description="Provenance and catalogue metadata"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_live_connectors",
    semantic_keywords=["available live models", "available live voices", "live thinking levels"],
    display=DisplayMetadata(emoji="🎙️", i18n_key="get_lia_live_options", category="tool"),
)
