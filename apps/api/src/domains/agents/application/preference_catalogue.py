"""Saved personalization manifests expose the exact readable preference fields."""

from src.domains.agents.application.preference_fields import PreferenceField
from src.domains.agents.application.schemas import PreferenceChangeRequest, PreferenceRead
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_READ_SCHEMA = PreferenceRead.model_json_schema()

PREFERENCES_READ_MANIFEST = ToolManifest(
    name="get_lia_preferences_tool",
    agent="setting_agent",
    description=(
        "Read this user's saved LIA application preferences: interface font size, "
        "font family, theme, language, timezone, personality and image defaults. "
        "No mutation. Returns actual localized option labels with their accepted IDs; "
        "use those labels in answers and IDs in writes, never invent choices. "
        "Account values are distinct from an unsaved device preview."
    ),
    parameters=[
        ParameterSchema(
            name="fields",
            type="array",
            required=False,
            description=PreferenceRead.model_fields["fields"].description or "Fields to read",
            schema={
                **_READ_SCHEMA["properties"]["fields"],
                "$defs": _READ_SCHEMA.get("$defs", {}),
            },
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
                nullable=field is PreferenceField.FULL_NAME,
                semantic_type="Text",
            )
            for field in (
                PreferenceField.FULL_NAME,
                PreferenceField.TIMEZONE,
                PreferenceField.LANGUAGE,
                PreferenceField.THEME,
                PreferenceField.COLOR_THEME,
                PreferenceField.FONT_FAMILY,
                PreferenceField.IMAGE_QUALITY,
                PreferenceField.IMAGE_SIZE,
                PreferenceField.IMAGE_FORMAT,
                PreferenceField.EXCHANGE_RHYTHM,
            )
        ],
        OutputFieldSchema(path="total", type="integer", description="Exact returned field count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_preferences",
    semantic_keywords=[
        "what is my interface font size",
        "read my LIA settings",
        "which language and timezone are configured",
    ],
    reference_examples=["preferences.values.font_size"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_preferences", category="tool"),
)

PREFERENCES_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_preferences_tool",
    agent="setting_agent",
    description=(
        "Save reversible personalization in the user's LIA settings without confirmation. "
        "Font increase/decrease is exactly one pixel, resolved before preview. "
        "Returns the actual saved state; read choices first when the user names an option. "
        "Use set with a concrete patch, increase_font or decrease_font without a patch."
    ),
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Explicit settings patch or one-pixel font change",
            schema=PreferenceChangeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="application_result",
            type="object",
            description="Saved state or refusal",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_preferences",
    semantic_keywords=[
        "increase interface font size",
        "change LIA theme and language",
        "adjust application settings",
    ],
    display=DisplayMetadata(emoji="⚙️", i18n_key="update_lia_preferences", category="tool"),
)
