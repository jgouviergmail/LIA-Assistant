"""Existing comment tool requires an exact native confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentPatch
from src.domains.feature_switches.registry import PlatformCapability

WORKBOARD_COMMENT_OPERATION = ApplicationOperationSpec(
    operation_id="workboard_ticket.comment",
    tool_name="comment_ticket_tool",
    sections=("workboard",),
    input_model=WorkboardCommentPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.WORKBOARD,),
)
