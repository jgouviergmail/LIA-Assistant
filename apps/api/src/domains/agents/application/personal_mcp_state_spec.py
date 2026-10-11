"""A personal MCP switch never changes an administrative shared server."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_state_schemas import PersonalMCPStatePatch
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_STATE_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.state.update",
    tool_name="set_lia_personal_mcp_server_enabled_tool",
    sections=("mcp",),
    input_model=PersonalMCPStatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
