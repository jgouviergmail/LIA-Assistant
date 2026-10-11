"""Existing saved copies stay removable when new saving/indexing is disabled."""

from src.domains.agents.application.bookmark_delete_schemas import BookmarkDeletePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

BOOKMARK_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="saved_answer.delete",
    tool_name="delete_lia_saved_answer_tool",
    sections=("generated-assets",),
    input_model=BookmarkDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
