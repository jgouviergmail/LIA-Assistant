"""Both orchestration modes observe the same original meeting owners."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.meeting_reads import MeetingReadInput, MeetingReadPage, TemplateReadInput

MEETING_READ_OPERATION = ApplicationOperationSpec(
    operation_id="meetings.read",
    tool_name="get_lia_meetings_tool",
    sections=("meetings",),
    input_model=MeetingReadInput,
    output_model=MeetingReadPage,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_TEMPLATE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_templates.read",
    tool_name="get_lia_meeting_templates_tool",
    sections=("meetings",),
    input_model=TemplateReadInput,
    output_model=MeetingReadPage,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
