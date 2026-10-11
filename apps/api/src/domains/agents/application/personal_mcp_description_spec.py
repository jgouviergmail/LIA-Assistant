"""Original cached-metadata regeneration is an accounted confirmed action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionPatch,
)
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_DESCRIPTION_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.description.regenerate",
    tool_name="regenerate_lia_personal_mcp_description_tool",
    sections=("mcp",),
    input_model=PersonalMCPDescriptionPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
