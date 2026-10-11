"""Reviewed owned interest-management read identity."""

from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeletePatch
from src.domains.agents.application.interest_create_schemas import InterestCreatePatch
from src.domains.agents.application.interest_detail_schemas import (
    InterestDetailProjection,
    InterestDetailRead,
)
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackPatch
from src.domains.agents.application.interest_history_schemas import (
    InterestHistoryProjection,
    InterestHistoryRead,
)
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivationPatch
from src.domains.agents.application.interest_read_schemas import InterestProjection, InterestRead
from src.domains.agents.application.interest_removal_schemas import InterestDeletePatch
from src.domains.agents.application.interest_settings_schemas import InterestSettingsPatch
from src.domains.agents.application.interest_update_schemas import InterestUpdatePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

INTEREST_READ_OPERATION = ApplicationOperationSpec(
    operation_id="interests.read",
    tool_name="get_lia_interests_tool",
    sections=("interests",),
    input_model=InterestRead,
    output_model=InterestProjection,
    kind=OperationKind.READ,
)

INTEREST_REACTIVATE_OPERATION = ApplicationOperationSpec(
    operation_id="interests.reactivate",
    tool_name="reactivate_lia_interest_tool",
    sections=("interests",),
    input_model=InterestReactivationPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_FEEDBACK_OPERATION = ApplicationOperationSpec(
    operation_id="interests.feedback",
    tool_name="submit_lia_interest_feedback_tool",
    sections=("interests",),
    input_model=InterestFeedbackPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_BULK_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="interests.delete_all",
    tool_name="delete_all_lia_interests_tool",
    sections=("interests",),
    input_model=InterestBulkDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_SETTINGS_OPERATION = ApplicationOperationSpec(
    operation_id="interest_settings.update",
    tool_name="update_lia_interest_settings_tool",
    sections=("interests",),
    input_model=InterestSettingsPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="interests.create",
    tool_name="create_lia_interest_tool",
    sections=("interests",),
    input_model=InterestCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="interests.update",
    tool_name="update_lia_interest_tool",
    sections=("interests",),
    input_model=InterestUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="interests.delete",
    tool_name="delete_lia_interest_tool",
    sections=("interests",),
    input_model=InterestDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

INTEREST_DETAILS_OPERATION = ApplicationOperationSpec(
    operation_id="interests.details.read",
    tool_name="get_lia_interest_details_tool",
    sections=("interests",),
    input_model=InterestDetailRead,
    output_model=InterestDetailProjection,
    kind=OperationKind.READ,
)

INTEREST_HISTORY_OPERATION = ApplicationOperationSpec(
    operation_id="interests.history.read",
    tool_name="get_lia_interest_history_tool",
    sections=("interests",),
    input_model=InterestHistoryRead,
    output_model=InterestHistoryProjection,
    kind=OperationKind.READ,
)
