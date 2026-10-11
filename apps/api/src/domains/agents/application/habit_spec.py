"""Stored habit records stay readable independently of the learning capability switch."""

from src.domains.agents.application.habit_action_schemas import HabitDeletePatch, HabitStatusPatch
from src.domains.agents.application.habit_detail_schemas import (
    HabitDetailProjection,
    HabitDetailRead,
)
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch
from src.domains.agents.application.habit_read_schemas import HabitRead, HabitsProjection
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputePatch
from src.domains.agents.application.habit_settings_schemas import HabitSettingsPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

HABIT_READ_OPERATION = ApplicationOperationSpec(
    operation_id="habits.read",
    tool_name="get_lia_habits_tool",
    sections=("habits",),
    input_model=HabitRead,
    output_model=HabitsProjection,
    kind=OperationKind.READ,
)

HABIT_DETAIL_OPERATION = ApplicationOperationSpec(
    operation_id="habits.details",
    tool_name="get_lia_habit_details_tool",
    sections=("habits",),
    input_model=HabitDetailRead,
    output_model=HabitDetailProjection,
    kind=OperationKind.READ,
)

HABIT_SETTINGS_OPERATION = ApplicationOperationSpec(
    operation_id="habit_settings.update",
    tool_name="update_lia_habit_settings_tool",
    sections=("habits",),
    input_model=HabitSettingsPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HABIT_STATUS_OPERATION = ApplicationOperationSpec(
    operation_id="habits.status",
    tool_name="set_lia_habit_status_tool",
    sections=("habits",),
    input_model=HabitStatusPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HABIT_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="habits.delete",
    tool_name="delete_lia_habit_tool",
    sections=("habits",),
    input_model=HabitDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HABIT_FORGET_OPERATION = ApplicationOperationSpec(
    operation_id="habits.forget",
    tool_name="delete_all_lia_habits_tool",
    sections=("habits",),
    input_model=HabitForgetPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HABIT_RECOMPUTE_OPERATION = ApplicationOperationSpec(
    operation_id="habits.recompute",
    tool_name="recompute_lia_habits_tool",
    sections=("habits",),
    input_model=HabitRecomputePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.HABITS,),
)
