"""Live account reflexes apply at session creation and never open a provider connection."""

from src.domains.agents.application.live_schemas import LivePreferenceRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

LIVE_PREFERENCES_READ_MANIFEST = ToolManifest(
    name="get_lia_live_preferences_tool",
    agent="setting_agent",
    description="Read effective account Live reflexes: interruptions, end_of_speech (calm/normal/lively), result_delivery (interrupt/when_idle). defaulted_fields identifies missing or invalid saved fields using defaults. These apply to future sessions; provider/model choices and current session state are separate. No credential or provider call.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="preferences", type="object", description="Effective account Live reflexes"
        ),
        OutputFieldSchema(
            path="defaulted_fields",
            type="array",
            description="Fields using defaults instead of valid saved values",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_live_preferences",
    semantic_keywords=["my live interruptions", "live pause sensitivity", "live result delivery"],
    display=DisplayMetadata(emoji="🎙️", i18n_key="get_lia_live_preferences", category="tool"),
)
LIVE_PREFERENCES_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_live_preferences_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation of specified Live reflex changes. Preserve other reflexes and provider choice; apply only to future sessions. Never start, restart or reconfigure a current session. No write before confirmation. Changed saved state requires a new preview.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="One or more explicit non-null Live reflex values",
            schema=LivePreferenceRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_live_preferences",
    semantic_keywords=[
        "change live interruptions",
        "adjust live pause sensitivity",
        "delay live delegated answers",
    ],
    display=DisplayMetadata(emoji="🎙️", i18n_key="update_lia_live_preferences", category="tool"),
)
