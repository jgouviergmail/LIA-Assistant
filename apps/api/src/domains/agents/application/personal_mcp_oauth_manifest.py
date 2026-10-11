"""One consent opens private provider authorization, followed by an explicit browser save."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthInput
from src.domains.agents.application.personal_mcp_oauth_spec import PERSONAL_MCP_OAUTH_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_OAUTH_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_OAUTH_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory confirmation to authorize an exact owned OAuth personal MCP server. Obtain its id through get_lia_personal_mcp_servers_tool. Requires the originating authenticated browser. Proposal and approval contact no provider. After approval the user opens a private provider authorization page and explicitly completes saving in the original browser. Never request codes, tokens, client secrets or authorization URLs in chat. Provider return stages encrypted tokens privately; it does not save or prove a connection. Current account/capability/session, expiry, full-row CAS and original approval fences apply throughout. Changed settings require fresh consent. Unknown attempts cannot replay. No administrator server or account-security action.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned OAuth personal server",
            schema=PersonalMCPOAuthInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["authorize personal MCP server", "connect MCP OAuth"],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="authorize_lia_personal_mcp_server", category="tool"
    ),
)
