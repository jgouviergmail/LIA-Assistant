"""URL plugin imports preserve the original component pipeline and mandatory consent."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportPatch

PLUGIN_URL_IMPORT_OPERATION = ApplicationOperationSpec(
    operation_id="plugin_url.import",
    tool_name="import_lia_plugin_url_tool",
    sections=("plugins",),
    input_model=PluginUrlImportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
