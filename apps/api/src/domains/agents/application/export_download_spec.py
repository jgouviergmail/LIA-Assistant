"""An archive download resumes in the original browser, with no invented step-up."""

from src.domains.agents.application.export_download_schemas import ExportDownloadPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

EXPORT_DOWNLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="account_export.download",
    tool_name="download_lia_account_export_tool",
    sections=("security-export",),
    input_model=ExportDownloadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)
