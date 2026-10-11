"""Assistant preference manifests publish the shared API schema, without secrets."""

from src.domains.agents.application.assistant_schemas import (
    AssistantPreferenceField,
    AssistantPreferenceRead,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.auth.preference_commands import AssistantPreferencePatch

_READ = AssistantPreferenceRead.model_json_schema()

ASSISTANT_READ_MANIFEST = ToolManifest(
    name="get_lia_assistant_preferences_tool",
    agent="setting_agent",
    description="Read this user's saved memory and health consent, voice, execution, location-use and display preferences. Never reads credentials or current coordinates.",
    parameters=[
        ParameterSchema(
            name="fields",
            type="array",
            required=False,
            description=AssistantPreferenceRead.model_fields["fields"].description
            or "Fields to read",
            schema={**_READ["properties"]["fields"], "$defs": _READ.get("$defs", {})},
        )
    ],
    outputs=[
        OutputFieldSchema(path="preferences", type="object", description="Current account values"),
        OutputFieldSchema(
            path="preferences.values", type="object", description="Selected saved preference fields"
        ),
        *[
            OutputFieldSchema(
                path=f"preferences.values.{field.value}",
                type="string",
                description=f"Current saved {field.value.replace('_', ' ')}; absent when not selected",
                semantic_type="Text",
            )
            for field in (
                AssistantPreferenceField.EXECUTION_MODE,
                AssistantPreferenceField.VOICE_STT_MODE,
                AssistantPreferenceField.RESPONSE_DISPLAY_MODE,
            )
        ],
        OutputFieldSchema(path="total", type="integer", description="Exact returned field count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_assistant_preferences",
    semantic_keywords=[
        "is memory enabled",
        "which execution mode",
        "voice and response display settings",
    ],
    reference_examples=["preferences.values.memory_enabled"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_assistant_preferences", category="tool"),
)

ASSISTANT_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_assistant_preferences_tool",
    agent="setting_agent",
    description="Save reversible assistant display and activation settings directly. Enabling hands-free microphone listening, remote speech processing, location/health access and login notifications retain human confirmation; mixed patches containing one of these also require confirmation. Disabling hands-free mode is immediate. Disabling location-use removes the saved position.",
    parameters=[
        ParameterSchema(
            name="patch",
            type="object",
            required=True,
            description="Non-empty non-secret preference patch",
            schema=AssistantPreferencePatch.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="application_result",
            type="object",
            description="Saved state for reversible preferences",
        ),
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending confirmation for sensitive consent",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_assistant_preferences",
    semantic_keywords=[
        "disable memory",
        "change voice settings",
        "switch execution mode",
        "stop using saved location",
    ],
    display=DisplayMetadata(
        emoji="⚙️", i18n_key="update_lia_assistant_preferences", category="tool"
    ),
)
