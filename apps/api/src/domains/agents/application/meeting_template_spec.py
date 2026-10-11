"""Distinct creation, replacement and removal are independently exact HITL actions."""

from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreatePatch,
    TemplateDeletePatch,
    TemplateUpdatePatch,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

TEMPLATE_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_template.create",
    tool_name="create_lia_meeting_template_tool",
    sections=("meetings",),
    input_model=TemplateCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
TEMPLATE_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_template.update",
    tool_name="update_lia_meeting_template_tool",
    sections=("meetings",),
    input_model=TemplateUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
TEMPLATE_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_template.delete",
    tool_name="delete_lia_meeting_template_tool",
    sections=("meetings",),
    input_model=TemplateDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
