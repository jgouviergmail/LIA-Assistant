"""Layout manifests share the reviewed UI models and runtime list bounds."""

from src.domains.agents.application.layout_schemas import LayoutPreferenceRead
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.infrastructure.account_preferences import LayoutPreferencePatch

_READ = LayoutPreferenceRead.model_json_schema()
LAYOUT_READ_MANIFEST = ToolManifest(
    name="get_lia_layout_preferences_tool",
    agent="setting_agent",
    description="Read the user's current briefing grid, chat slash shortcuts and pinned settings sections as displayed in the application. Administrative pins are restricted to current administrators.",
    parameters=[
        ParameterSchema(
            name="fields",
            type="array",
            required=False,
            description="Distinct layout selectors",
            schema={**_READ["properties"]["fields"], "$defs": _READ.get("$defs", {})},
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="preferences",
            type="object",
            description="Current displayed account values",
        ),
        OutputFieldSchema(path="total", type="integer", description="Exact returned field count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_layout_preferences",
    semantic_keywords=[
        "which briefing cards are hidden",
        "list my shortcuts",
        "which settings are pinned",
    ],
    reference_examples=["preferences.values.chat_shortcuts"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_layout_preferences", category="tool"),
)
LAYOUT_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_layout_preferences_tool",
    agent="setting_agent",
    description="Save reversible briefing grid or shortcut personalization without confirmation. Read existing lists first, preserve entries not requested for removal and include complete intended lists. Concurrent edits are refused rather than overwritten.",
    parameters=[
        ParameterSchema(
            name="patch",
            type="object",
            required=True,
            description="Complete lists for each selected layout; omitted layouts remain unchanged",
            schema=LayoutPreferencePatch.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="application_result",
            type="object",
            description="Saved personalization state",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_layout_preferences",
    semantic_keywords=[
        "hide a briefing card",
        "change my slash shortcuts",
        "pin a settings section",
    ],
    display=DisplayMetadata(emoji="⚙️", i18n_key="update_lia_layout_preferences", category="tool"),
)
