"""One source reset family covers soft, full and complete owned purge."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.psyche_reset_schemas import PsycheResetPatch
from src.domains.feature_switches.registry import PlatformCapability

PSYCHE_RESET_OPERATION = ApplicationOperationSpec(
    operation_id="psyche.reset",
    tool_name="reset_lia_psyche_tool",
    sections=("psyche",),
    input_model=PsycheResetPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PSYCHE,),
)
