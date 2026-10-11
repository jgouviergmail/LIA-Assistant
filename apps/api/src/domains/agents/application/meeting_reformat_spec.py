"""Reformat starts the original paid synthesis with explicit replacement or new output."""

from src.domains.agents.application.meeting_reformat_schemas import (
    MeetingReformatInput,
    MeetingReformatPatch,
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

MEETING_REFORMAT_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.reformat",
    tool_name="reformat_lia_meeting_report_tool",
    sections=("meetings",),
    input_model=MeetingReformatPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_REFORMAT_MANIFEST = ToolManifest(
    name="reformat_lia_meeting_report_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to write an owned ready meeting's minutes with another owned or built-in template. mode=replace replaces the entire current report including manual edits on successful synthesis; refuse an in-place active rebuild. mode=new creates separate minutes from the retained transcript, preserves the source report, copies no audio and adds no transcription charge; it may run while the source already synthesizes. Show the complete selected template instructions, original source summary and destination identifier. Private bodies/witnesses never reach prompts. The later original quota-controlled worker rereads template references/runtime configuration, so later edits may affect it. Existing synthesis/indexing costs and platform quotas apply even without a personal key; no final price promised. Processing and indexing remain incomplete on queue acceptance. No recording, new transcription, automatic email or notification. Original HITL and fresh source/capability checks are mandatory; changed source requires new consent. Never automatically replay unknown commit acknowledgment. Refuse oversized complete consent without truncation and direct to the application. No foreign/admin data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned meeting, selected template and original replace/new mode",
            schema=MeetingReformatInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="reformat_lia_meeting_report", category="tool"),
)
