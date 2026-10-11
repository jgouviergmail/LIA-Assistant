"""Reviewed personal commitment reads require the source platform capability."""

from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopClosePatch,
    OpenLoopUpdatePatch,
)
from src.domains.agents.application.open_loop_schemas import OpenLoopProjection, OpenLoopRead
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

OPEN_LOOP_READ_OPERATION = ApplicationOperationSpec(
    operation_id="open_loops.read",
    tool_name="get_lia_open_loops_tool",
    sections=("open-loops",),
    input_model=OpenLoopRead,
    output_model=OpenLoopProjection,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.OPEN_LOOPS,),
)

OPEN_LOOP_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="open_loops.update",
    tool_name="update_lia_open_loop_tool",
    sections=("open-loops",),
    input_model=OpenLoopUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.OPEN_LOOPS,),
)

OPEN_LOOP_CLOSE_OPERATION = ApplicationOperationSpec(
    operation_id="open_loops.close",
    tool_name="close_lia_open_loop_tool",
    sections=("open-loops",),
    input_model=OpenLoopClosePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.OPEN_LOOPS,),
)
