"""A requeue initiates the original potentially paid, quota-controlled workflow."""

from src.domains.agents.application.meeting_retry_schemas import (
    MeetingRetryInput,
    MeetingRetryPatch,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

MEETING_RETRY_OPERATION = ApplicationOperationSpec(
    operation_id="meeting.retry",
    tool_name="retry_lia_meeting_tool",
    sections=("meetings",),
    input_model=MeetingRetryPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_RETRY_MANIFEST = ToolManifest(
    name="retry_lia_meeting_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to retry the original durable processing of an owned stopped/failed meeting with existing audio. Never retry a live/ready/processing meeting; use other original lifecycle actions. Seal all source row/audio bytes and show status, title, attempts, actual audio file count/bytes, transcript availability, retention deadline and current account preferences. The reset requeues the original workflow; processing_completed is always false in the action result. The original worker may reuse checkpoints, transcribe audio, select a template, synthesize and replace minutes, enrich location/calendar, notify, email when auto_email is enabled, index in the meeting knowledge space and purge unkept audio. Existing model/transcription/embedding costs and usage limits apply, including platform-funded use. No exact final price or immediate success is promised. Preferences and runtime/template definitions are shown at confirmation and reread by the original later job; later edits can affect it. Content is not displayed; private witnesses never reach prompts. Source changes require new consent. Unknown commits never authorize automatic replay. No foreign/admin data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned stopped/failed meeting identifier",
            schema=MeetingRetryInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="retry_lia_meeting", category="tool"),
)
