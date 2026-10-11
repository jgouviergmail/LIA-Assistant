"""A personal standalone deletion cannot target administrative or plugin servers."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_delete_schemas import PersonalMCPDeletePatch
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.delete",
    tool_name="delete_lia_personal_mcp_server_tool",
    sections=("mcp",),
    input_model=PersonalMCPDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
