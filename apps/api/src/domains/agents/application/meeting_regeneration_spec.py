"""Rebuilding minutes starts the original quota-controlled asynchronous synthesis."""

from src.domains.agents.application.meeting_regeneration_schemas import (
    MeetingRegenerationInput,
    MeetingRegenerationPatch,
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

MEETING_REGENERATION_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.regenerate",
    tool_name="regenerate_lia_meeting_report_tool",
    sections=("meetings",),
    input_model=MeetingRegenerationPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_REGENERATION_MANIFEST = ToolManifest(
    name="regenerate_lia_meeting_report_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to regenerate all minutes of an owned ready, idle meeting with a retained transcript. Uses the stored transcript without new recording or transcription. The successful background job replaces the entire current report, including manual edits, and updates its generated revision, then schedules indexing; the previous report remains readable during synthesis. Show current validity/title/counts, transcript turn count and the complete template definition at confirmation. Bodies and private witnesses never reach prompts. The later original job rereads template references and runtime configuration, so later changes may affect it. Existing synthesis/embedding costs and account quotas apply, including platform-funded use without a personal key; no exact price is promised. Queue acceptance is not processing or indexing completion. No automatic email/notification. Unknown commits never authorize replay. Source changes need new consent. Refuse oversized complete consent without truncation and direct the user to the application. No foreign/admin data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned ready meeting identifier",
            schema=MeetingRegenerationInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="regenerate_lia_meeting_report", category="tool"),
)
