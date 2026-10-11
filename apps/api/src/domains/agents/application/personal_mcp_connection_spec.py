"""Owned MCP discovery uses the original explicit confirmation path."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionPatch,
)
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_CONNECTION_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.connection.test",
    tool_name="test_lia_personal_mcp_connection_tool",
    sections=("mcp",),
    input_model=PersonalMCPConnectionPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
