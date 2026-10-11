"""A plugin is removed only as one exact owned group with mandatory confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.plugin_delete_schemas import PluginDeletePatch

PLUGIN_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="plugin.delete",
    tool_name="delete_lia_plugin_tool",
    sections=("plugins",),
    input_model=PluginDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
