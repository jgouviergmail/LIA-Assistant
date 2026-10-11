"""Probe consent includes the existing documentation, generation and embedding effects."""

from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionInput,
)
from src.domains.agents.application.personal_mcp_connection_spec import (
    PERSONAL_MCP_CONNECTION_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_CONNECTION_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_CONNECTION_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory confirmation to test ONE owned personal MCP connection. Resolve exact server_id through get_lia_personal_mcp_servers_tool. Preparation makes no network/model call. Confirmation permits the original endpoint initialization, tool discovery and optional documentation read_me call; it refreshes cached tools, status and last connection, may generate a missing description through the accounted/quota-limited platform model and may compute original tool embeddings. Existing OAuth authentication may refresh stored tokens; a changed authentication snapshot requires fresh consent before saving discovery. Do not promise success or invent discovered tools. URL policy is revalidated before contact; original bounded ephemeral client, cooldown and pool limits apply. No database/actor row lock spans network/model/accounting. Fresh authority, expiry and full-row CAS guard success AND failure persistence afterwards; conflicts may refuse saving after external work/cost occurred. Receipt reports observed connection success separately from acknowledged saved status: connection_success=false means a failed connection was recorded, never a working connection. Raw errors, credentials and cached schemas stay private; consult paged metadata for tool details. No administrative shared server, OAuth authorization or arbitrary remote action. Unknown outcomes cannot replay.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned personal MCP server to test",
            schema=PersonalMCPConnectionInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["test personal MCP connection", "discover personal MCP tools"],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="test_lia_personal_mcp_connection", category="tool"
    ),
)
