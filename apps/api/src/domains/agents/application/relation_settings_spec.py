"""Relationship controls live on the existing Relations page, independently of paid synthesis."""

from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.relation_settings_read import RelationSettingsProjection
from src.domains.agents.application.relation_settings_schemas import RelationSettingsPatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

RELATION_SETTINGS_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="relation_settings.update",
    tool_name="update_lia_relation_settings_tool",
    sections=("relations",),
    input_model=RelationSettingsPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
RELATION_SETTINGS_UPDATE_MANIFEST = ToolManifest(
    name=RELATION_SETTINGS_UPDATE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare exact mandatory human confirmation for the account's Relations-page settings. Explicit relation_debrief_enabled boolean and/or a complete relation_overview_scope using source sections, directions, meeting roles and max_items. Empty arrays exclude those sources. Omitted scope subfields use source defaults, so read the current scope and preserve choices unless explicitly changing them. Only selected top-level settings change; other settings and stored relationship data remain intact. A disabled platform debrief remains unavailable even when the personal preference is enabled. This performs no provider request or paid debrief. Source owner lock compares the exact approved stored values, including an unsaved null scope; stale values require a fresh proposal. Reuse get_lia_relation_settings_tool to inspect current effective defaults and availability.",
    parameters=[
        ParameterSchema(
            name="patch",
            type="object",
            required=True,
            description="Explicit sparse relation preferences; whole scope replacement",
            schema=RelationSettingsPatch.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Exact pending before/after approval"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_relation_settings",
    initiative_eligible=False,
    semantic_keywords=["relationship settings", "disable daily debrief", "change 360 degree scope"],
    display=DisplayMetadata(emoji="🤝", i18n_key="update_lia_relation_settings", category="tool"),
)

RELATION_SETTINGS_READ_OPERATION = ApplicationOperationSpec(
    operation_id="relation_settings.read",
    tool_name="get_lia_relation_settings_tool",
    sections=("relations",),
    input_model=ApplicationEmptyRead,
    output_model=RelationSettingsProjection,
    kind=OperationKind.READ,
)
RELATION_SETTINGS_READ_MANIFEST = ToolManifest(
    name=RELATION_SETTINGS_READ_OPERATION.tool_name,
    agent="setting_agent",
    description="Read the authenticated account's Relations-page controls: whether the daily relationship debrief is personally enabled, current platform availability, and the exact effective 360-degree sections/directions/meeting roles/items-per-section selection. Reuse source scope defaults when never saved or the stored legacy shape is unreadable. Empty source sections mean no sources. Oversized stored selections refuse rather than consuming unbounded model context. This neither fetches contacts/email/calendar nor initializes, generates or charges a debrief. Current relationship facts and peer messages remain covered by existing domain tools; these are control values, not a relationship report.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="overview_scope",
            type="object",
            description="Effective source 360-degree selection",
        ),
        OutputFieldSchema(
            path="debrief_enabled", type="boolean", description="Owned saved debrief preference"
        ),
        OutputFieldSchema(
            path="debrief_platform_enabled",
            type="boolean",
            description="Fresh operator availability",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    tool_category="system",
    mutation_policy="read",
    binding_unit="lia_relation_settings",
    initiative_eligible=False,
    semantic_keywords=[
        "relationship settings",
        "360 degree scope",
        "daily relationship debrief enabled",
    ],
    display=DisplayMetadata(emoji="🤝", i18n_key="get_lia_relation_settings", category="tool"),
)
