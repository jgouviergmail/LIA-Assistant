"""Existing deletion tool produces a bounded native source-subtree confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.workboard_delete_schemas import WorkboardDeletePatch
from src.domains.feature_switches.registry import PlatformCapability

WORKBOARD_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="workboard_ticket.delete",
    tool_name="delete_ticket_tool",
    sections=("workboard",),
    input_model=WorkboardDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.WORKBOARD,),
)
