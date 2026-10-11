"""Personal MCP token withdrawal is a confirmed native action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    PersonalMCPOAuthDisconnectPatch,
)
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.oauth.disconnect",
    tool_name="disconnect_lia_personal_mcp_oauth_tool",
    sections=("mcp",),
    input_model=PersonalMCPOAuthDisconnectPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
