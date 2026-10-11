"""Existing personal form settings use mandatory application confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_settings_schemas import PersonalMCPSettingsPatch
from src.domains.feature_switches.registry import PlatformCapability

PERSONAL_MCP_SETTINGS_OPERATION = ApplicationOperationSpec(
    operation_id="personal_mcp.settings.update",
    tool_name="update_lia_personal_mcp_server_settings_tool",
    sections=("mcp",),
    input_model=PersonalMCPSettingsPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MCP,),
)
