"""Private credentials remain in the confirmed browser, using an existing DEVICE interaction."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationPatch,
)
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_CONFIGURATION_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.configuration",
    tool_name="configure_lia_personal_mcp_server_tool",
    sections=("mcp",),
    input_model=PersonalMCPConfigurationPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.MCP,),
)
