"""Irreversible whole-meeting deletion requires the original exact human approval."""

from src.domains.agents.application.meeting_deletion_schemas import (
    MeetingDeletionInput,
    MeetingDeletionPatch,
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

MEETING_DELETION_OPERATION = ApplicationOperationSpec(
    operation_id="meeting.delete",
    tool_name="delete_lia_meeting_tool",
    sections=("meetings",),
    input_model=MeetingDeletionPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_DELETION_MANIFEST = ToolManifest(
    name="delete_lia_meeting_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to irreversibly delete one owned non-live meeting: entire current/generated reports, retained transcript, owned audio directory and its owned knowledge-space projection/chunks. Refuse an active processing lease; discard live capture through its original device controls. Seal all source row/audio bytes/projection metadata and show status/title/counts, retained transcript presence, exact audio file count/bytes, projection and count of derived minutes retained. Bodies, file paths and private witnesses never reach prompts. Derived minutes and their transcripts are preserved; their source reference is cleared by the original foreign key. Queue no new paid provider work; an already running rebuild/indexing may already have consumed billed work. Database deletion acknowledgment and observed file cleanup are separate facts. Cleanup failure stays explicit, never claimed complete or automatically replayed. Changed source needs new consent; unknown commits never authorize replay. No foreign/admin data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned meeting identifier",
            schema=MeetingDeletionInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="delete_lia_meeting", category="tool"),
)
