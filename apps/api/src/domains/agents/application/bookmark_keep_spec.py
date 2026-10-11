"""A saved-answer copy always requires exact confirmation and the original keep capability."""

from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

BOOKMARK_KEEP_OPERATION = ApplicationOperationSpec(
    operation_id="saved_answer.keep",
    tool_name="keep_lia_saved_answer_tool",
    sections=("generated-assets",),
    input_model=BookmarkKeepPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.BOOKMARKS,),
)
