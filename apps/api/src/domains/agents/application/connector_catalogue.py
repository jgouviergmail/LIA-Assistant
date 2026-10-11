"""Bounded connector preference manifests derive public schemas from the domain contract."""

from src.domains.agents.application.connector_schemas import (
    ConnectorPreferencesRead,
    ConnectorPreferenceUpdateRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

CONNECTOR_PREFERENCES_READ_MANIFEST = ToolManifest(
    name="get_lia_connector_preferences_tool",
    agent="setting_agent",
    description="Read this account's saved non-secret calendar/task-list defaults and saved connector status. No credentials, OAuth tokens or live provider health test. Read all pages through next_cursor when a complete list is required; other connector settings are separate secure flows.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Bounded page; pass next_cursor as after_id",
            schema=ConnectorPreferencesRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="connectors", type="array", description="Owned non-secret saved preferences"
        ),
        OutputFieldSchema(path="total", type="integer", description="Total matching connectors"),
        OutputFieldSchema(
            path="next_cursor", type="string", description="Next page cursor, null at the last page"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_connector_preferences",
    semantic_keywords=[
        "my default calendar",
        "my default task list",
        "saved connector preferences",
    ],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_connector_preferences", category="tool"),
)
CONNECTOR_PREFERENCES_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_connector_preferences_tool",
    agent="setting_agent",
    description="Prepare human confirmation to set or clear a saved calendar/task-list default on one owned connector. Read its current id first. Preview the exact sanitized value; no write before approval. Empty string clears the default, preserving the existing provider fallback. This saves a preference, not a provider availability guarantee; credentials and connection authorization stay in secure UI flows.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Owned connector and one explicit preference change",
            schema=ConnectorPreferenceUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_connector_preferences",
    semantic_keywords=["change default calendar", "clear default task list"],
    display=DisplayMetadata(
        emoji="⚙️", i18n_key="update_lia_connector_preferences", category="tool"
    ),
)
