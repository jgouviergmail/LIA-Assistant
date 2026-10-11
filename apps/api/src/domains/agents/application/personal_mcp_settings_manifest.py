"""Non-secret form edits never collect endpoints, credentials or OAuth tokens."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.personal_mcp_settings_schemas import PersonalMCPSettingsInput
from src.domains.agents.application.personal_mcp_settings_spec import (
    PERSONAL_MCP_SETTINGS_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_SETTINGS_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_SETTINGS_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to edit ONE owned personal MCP server's existing non-secret form settings: name, domain_description, timeout_seconds or iterative_mode. Select the exact server_id through get_lia_personal_mcp_servers_tool. Send only requested patch fields; null clears only domain_description. The original name uniqueness and size/range validators apply. Whole original row, including private connection/authentication metadata, is sealed and rechecked under current account/server locks; any change requires new approval. Matching values are a confirmed no-op. URL, authentication credentials, OAuth scopes and the API-only HITL override are excluded. No connection, test, discovery, model call, administrative shared-server edit or tool execution. The draft is the confirmation; only a known commit may be reported as success.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned server and non-empty supported setting patch",
            schema=PersonalMCPSettingsInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["personal MCP name", "MCP timeout", "MCP description", "MCP iterative mode"],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="update_lia_personal_mcp_server_settings", category="tool"
    ),
)
