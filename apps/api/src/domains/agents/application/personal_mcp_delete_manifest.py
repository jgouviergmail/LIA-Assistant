"""Only an exact owned standalone MCP server can be proposed for removal."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.personal_mcp_delete_schemas import PersonalMCPDeleteInput
from src.domains.agents.application.personal_mcp_delete_spec import PERSONAL_MCP_DELETE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_DELETE_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_DELETE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to delete ONE owned personal standalone MCP server selected by server_id from get_lia_personal_mcp_servers_tool. Original ownership, fresh capabilities, expiry and full-row CAS are checked under account/server locks. Plugin-installed servers refuse before any connection change: use delete_lia_plugin_tool for a complete owned plugin uninstall. The original connection pool is disconnected before SQL deletion and current authorization is checked again before the write. No administrative shared server, remote server deletion, external tool execution or model charge. Never claim deletion before a known commit; an uncertain commit cannot be replayed. Private endpoint paths and credentials are excluded from confirmation.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned standalone personal server UUID",
            schema=PersonalMCPDeleteInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["delete personal MCP server", "remove personal MCP connection"],
    display=DisplayMetadata(emoji="🔌", i18n_key="delete_lia_personal_mcp_server", category="tool"),
)
