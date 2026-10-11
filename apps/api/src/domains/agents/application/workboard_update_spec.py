"""Existing update capability owns all source update fields and move/run-now gestures."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdatePatch
from src.domains.feature_switches.registry import PlatformCapability

WORKBOARD_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="workboard_ticket.update",
    tool_name="update_ticket_tool",
    sections=("workboard",),
    input_model=WorkboardUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.WORKBOARD,),
)
