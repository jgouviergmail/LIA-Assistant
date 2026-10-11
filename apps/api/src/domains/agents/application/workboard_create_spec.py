"""The existing ticket tool produces a mandatory native creation draft."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.workboard_create_schemas import WorkboardCreatePatch
from src.domains.feature_switches.registry import PlatformCapability

WORKBOARD_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="workboard_ticket.create",
    tool_name="create_ticket_tool",
    sections=("workboard",),
    input_model=WorkboardCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.WORKBOARD,),
)
