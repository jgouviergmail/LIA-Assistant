"""Credentials and full endpoints belong exclusively to the existing browser form."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationInput,
)
from src.domains.agents.application.personal_mcp_configuration_spec import (
    PERSONAL_MCP_CONFIGURATION_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_CONFIGURATION_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_CONFIGURATION_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory confirmation to open a secure browser form for a personal MCP server. Omit server_id to create; choose an exact owned id through get_lia_personal_mcp_servers_tool to modify. To add one of LIA's known servers (the keys known_server lists), pass known_server with no server_id: the form opens prefilled with that server's public name, address and authentication type, and the user still saves it there. Requires the originating authenticated browser. Never ask for credentials or secret-bearing URLs in chat: the user enters endpoint/authentication values only in the form and explicitly saves. Proposal and approval perform no CRUD, network or authorization. The approved live browser may submit once; original schema, HTTPS/SSRF, ownership, current gates, expiry, full-row CAS and serial quota/name constraints apply before commit. Only sanitized saved metadata persists in assistant receipts; saved configuration does not prove a working connection. Use the separate confirmed connection test or OAuth flow. No administrator shared server, provider-wide grant or account-security change. Unknown commits cannot replay.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description=(
                "Owned server to edit, a known_server key to add one of the known "
                "servers, or empty object for a new server typed in the form"
            ),
            schema=PersonalMCPConfigurationInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "add personal MCP server",
        "add a known app as MCP server",
        "connect an app through MCP",
        "configure personal MCP authentication",
        "change MCP endpoint",
    ],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="configure_lia_personal_mcp_server", category="tool"
    ),
)
