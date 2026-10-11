"""The originating browser chooses and confirms the local package after original HITL."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.plugin_file_upload_schemas import PluginFileUploadPatch

PLUGIN_FILE_UPLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="plugin_file.upload",
    tool_name="import_lia_plugin_file_tool",
    sections=("plugins",),
    input_model=PluginFileUploadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)
