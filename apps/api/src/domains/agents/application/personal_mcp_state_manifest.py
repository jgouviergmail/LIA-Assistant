"""Setting personal MCP state always presents fresh exact consent."""

from src.domains.agents.application.personal_mcp_state_schemas import PersonalMCPStateInput
from src.domains.agents.application.personal_mcp_state_spec import PERSONAL_MCP_STATE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_STATE_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_STATE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory explicit confirmation to enable or disable ONE owned personal MCP server. Select server_id via get_lia_personal_mcp_servers_tool; enabled is the concrete desired boolean, never a toggle instruction. Disabled/auth-required/error and plugin-installed personal servers are eligible. Whole current row, credential changes and cached metadata are sealed; changed state requires fresh approval. Fresh account/application/MCP/personal availability, exact ownership and expiry are rechecked under account/server locks and before commit. Already matching state is a confirmed no-op. Disabling disconnects the original personal connection pool; enabling does not probe or authorize a server. No administrative shared server, credential/OAuth write, discovery, tool execution or model charge. Never claim success before a known commit; an unknown result cannot replay.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned server and explicit desired enabled state",
            schema=PersonalMCPStateInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "enable personal MCP server",
        "disable personal MCP server",
        "personal MCP activation",
    ],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="set_lia_personal_mcp_server_enabled", category="tool"
    ),
)
