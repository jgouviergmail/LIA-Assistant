"""Reviewed management exports resume only in the approved browser."""

from src.domains.agents.application.management_export_schemas import ManagementExportPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

INTEREST_EXPORT_OPERATION = ApplicationOperationSpec(
    operation_id="interests.export",
    tool_name="export_lia_interests_tool",
    sections=("interests",),
    input_model=ManagementExportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)

MEMORY_EXPORT_OPERATION = ApplicationOperationSpec(
    operation_id="memories.export",
    tool_name="export_lia_memories_tool",
    sections=("memories",),
    input_model=ManagementExportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)

JOURNAL_EXPORT_OPERATION = ApplicationOperationSpec(
    operation_id="journals.export",
    tool_name="export_lia_journals_tool",
    sections=("journals",),
    input_model=ManagementExportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.JOURNALS,),
)
