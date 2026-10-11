"""Withdrawal is local and preserves original OAuth client configuration."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    PersonalMCPOAuthDisconnectInput,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_spec import (
    PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_OAUTH_DISCONNECT_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory confirmation to disconnect OAuth for ONE owned personal MCP server, selected through get_lia_personal_mcp_servers_tool. Only OAuth servers qualify. Preparation changes nothing. Confirmation reuses the original local token purge: access/refresh tokens are removed, client credentials retained, status becomes auth_required and pool metadata invalidated. This does not revoke the provider's grant or disable/delete the server. Exact actor, current capability gates, expiry and full-row CAS are checked before writing and again before commit; changes require new consent. Secrets never enter public previews/results. No authorization browser flow, model call, admin shared server or arbitrary remote action. Unknown commits cannot replay.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned OAuth personal MCP server",
            schema=PersonalMCPOAuthDisconnectInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["disconnect personal MCP OAuth", "remove personal MCP connection tokens"],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="disconnect_lia_personal_mcp_oauth", category="tool"
    ),
)
