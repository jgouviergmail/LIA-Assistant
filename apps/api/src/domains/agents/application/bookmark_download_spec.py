"""Saved-copy export needs the original browser and stays available independently of indexing."""

from src.domains.agents.application.bookmark_download_schemas import BookmarkDownloadPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

BOOKMARK_DOWNLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="saved_answer.download",
    tool_name="download_lia_saved_answer_tool",
    sections=("generated-assets",),
    input_model=BookmarkDownloadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)
