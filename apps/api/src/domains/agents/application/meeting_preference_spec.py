"""Meeting settings are current-account reads and explicitly confirmed preferences."""

from src.domains.agents.application.meeting_preference_schemas import MeetingPreferencePatch
from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.meeting_preferences import MeetingPreferenceState

MEETING_PREFERENCE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_preferences.read",
    tool_name="get_lia_meeting_preferences_tool",
    sections=("meetings",),
    input_model=ApplicationEmptyRead,
    output_model=MeetingPreferenceState,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_PREFERENCE_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_preferences.update",
    tool_name="update_lia_meeting_preferences_tool",
    sections=("meetings",),
    input_model=MeetingPreferencePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
