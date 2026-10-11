"""Reviewed routine management operation; independent from its source writer."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.routine_create_schemas import RoutineCreatePatch
from src.domains.agents.application.routine_read_schemas import RoutineProjection, RoutineRead
from src.domains.agents.application.routine_removal_schemas import RoutineDeletePatch
from src.domains.agents.application.routine_run_schemas import RoutineRunPatch
from src.domains.agents.application.routine_schemas import RoutineStatePatch
from src.domains.agents.application.routine_update_schemas import RoutineUpdatePatch

ROUTINE_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="routine.update",
    tool_name="update_lia_routine_tool",
    sections=("scheduled-actions",),
    input_model=RoutineUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

ROUTINE_RUN_OPERATION = ApplicationOperationSpec(
    operation_id="routine.execute",
    tool_name="execute_lia_routine_tool",
    sections=("scheduled-actions",),
    input_model=RoutineRunPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

ROUTINE_STATE_OPERATION = ApplicationOperationSpec(
    operation_id="routine_state.update",
    tool_name="set_lia_routine_state_tool",
    sections=("scheduled-actions",),
    input_model=RoutineStatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

ROUTINE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="routines.read",
    tool_name="get_lia_routines_tool",
    sections=("scheduled-actions",),
    input_model=RoutineRead,
    output_model=RoutineProjection,
    kind=OperationKind.READ,
)

ROUTINE_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="routine.create",
    tool_name="create_lia_routine_tool",
    sections=("scheduled-actions",),
    input_model=RoutineCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

ROUTINE_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="routine.delete",
    tool_name="delete_lia_routine_tool",
    sections=("scheduled-actions",),
    input_model=RoutineDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
