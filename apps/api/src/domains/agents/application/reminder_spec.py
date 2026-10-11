"""Reviewed reminder management reads compose the source DTO."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.reminder_create_schemas import ReminderCreatePatch
from src.domains.agents.application.reminder_read_schemas import ReminderProjection, ReminderRead
from src.domains.agents.application.reminder_removal_schemas import ReminderDeletePatch
from src.domains.agents.application.reminder_update_schemas import ReminderUpdatePatch

REMINDER_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="reminder.update",
    tool_name="update_lia_reminder_tool",
    sections=("reminders",),
    input_model=ReminderUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

REMINDER_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="reminder.delete",
    tool_name="delete_lia_reminder_tool",
    sections=("reminders",),
    input_model=ReminderDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

REMINDER_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="reminder.create",
    tool_name="create_lia_reminder_tool",
    sections=("reminders",),
    input_model=ReminderCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

REMINDER_READ_OPERATION = ApplicationOperationSpec(
    operation_id="reminders.read",
    tool_name="get_lia_reminders_tool",
    sections=("reminders",),
    input_model=ReminderRead,
    output_model=ReminderProjection,
    kind=OperationKind.READ,
)
