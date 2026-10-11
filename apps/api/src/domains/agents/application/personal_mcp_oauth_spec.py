"""Provider authorization follows the original sole HITL and browser continuation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthPatch
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_OAUTH_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.oauth_authorize",
    tool_name="authorize_lia_personal_mcp_server_tool",
    sections=("mcp",),
    input_model=PersonalMCPOAuthPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.MCP,),
)
