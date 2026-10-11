"""One independently registered personal transcript deletion operation."""

from src.domains.agents.application.meeting_transcript_schemas import (
    TranscriptDeleteInput,
    TranscriptDeletePatch,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

TRANSCRIPT_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_transcript.delete",
    tool_name="delete_lia_meeting_transcript_tool",
    sections=("meetings",),
    input_model=TranscriptDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
TRANSCRIPT_DELETE_MANIFEST = ToolManifest(
    name="delete_lia_meeting_transcript_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to delete the original transcript of one current-owner meeting, identified by meeting_id from the owned meeting list/detail. The original service refuses live or processing meetings. The selected meeting title/status/stage, transcript presence and deletion scope are shown; fresh ciphertext/state CAS and capability/actor/expiry checks apply under its row lock. This preserves the minutes, their knowledge-space projection and retained audio; it does not erase transcript-derived words already present in those minutes. Deleting the transcript removes the source for later regeneration/reformatting; no model/job/email starts. Unknown commit acknowledgments are fenced and must not replay automatically. A missing transcript is an explicit no-op. No administrator data or foreign meetings.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned meeting identifier",
            schema=TranscriptDeleteInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="delete_lia_meeting_transcript", category="tool"),
)
