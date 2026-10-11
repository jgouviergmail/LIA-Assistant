"""Heartbeat manifests publish the shared UI limits and native confirmation schema."""

from src.domains.agents.application.heartbeat_schemas import (
    HeartbeatPreferencePatch,
    HeartbeatPreferenceRead,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_READ = HeartbeatPreferenceRead.model_json_schema()
HEARTBEAT_READ_MANIFEST = ToolManifest(
    name="get_lia_heartbeat_preferences_tool",
    agent="setting_agent",
    description="Read saved heartbeat settings, platform delivery switches, connected sources, source refusals and dependencies. Saved enabled does not guarantee delivery: honor the platform switch, hours and source availability. No provider calls.",
    parameters=[
        ParameterSchema(
            name="fields",
            type="array",
            required=False,
            description="Distinct heartbeat selectors",
            schema={**_READ["properties"]["fields"], "$defs": _READ.get("$defs", {})},
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="preferences",
            type="object",
            description="Saved values and current platform/source status",
        ),
        OutputFieldSchema(path="total", type="integer", description="Exact returned field count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_heartbeat_preferences",
    semantic_keywords=[
        "is heartbeat enabled",
        "which proactive sources are refused",
        "why do I receive no proactive notifications",
    ],
    reference_examples=["preferences.values.chat_shortcuts"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_heartbeat_preferences", category="tool"),
)
HEARTBEAT_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_heartbeat_preferences_tool",
    agent="setting_agent",
    description="Save reversible Heartbeat enablement, local hours and source/moment refusal lists directly. Read existing lists first and preserve entries not requested for removal. Source constraints and concurrent-edit checks apply; saving preferences does not deliver a notification or invoke a model.",
    parameters=[
        ParameterSchema(
            name="patch",
            type="object",
            required=True,
            description="Desired heartbeat fields; arrays replace complete refusal lists",
            schema=HeartbeatPreferencePatch.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="application_result",
            type="object",
            description="Saved state for reviewed reversible preferences",
        ),
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending confirmation when sensitive fields are included",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_heartbeat_preferences",
    semantic_keywords=[
        "disable proactive notifications",
        "change notification hours",
        "refuse proactive email nudges",
    ],
    display=DisplayMetadata(
        emoji="⚙️", i18n_key="update_lia_heartbeat_preferences", category="tool"
    ),
)
