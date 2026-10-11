"""Exact original five-field minutes editing, always behind explicit HITL."""

from src.domains.agents.application.meeting_report_update_schemas import (
    ReportUpdateInput,
    ReportUpdatePatch,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

REPORT_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.update",
    tool_name="update_lia_meeting_report_tool",
    sections=("meetings",),
    input_model=ReportUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
REPORT_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_meeting_report_tool",
    agent="setting_agent",
    description="Prepare original mandatory HITL to edit one owned meeting: title, participants, sections, location_label or template_ref. Sparse changes preserve every unrequested field. Explicit empty participant/section lists replace them entirely; null is ignored by the original API and refused here. Participants and sections are whole-field replacements, never append or guessed partial content: read the full selected field first when preserving it. Every literal before/after value is shown without truncation. A proposal exceeding the existing native result token ceiling, slot window allowance or 64 KB UTF-8 scope is refused rather than partially approved; use the application for an oversized full-list replacement. Template selection is permitted only before processing (live/interrupted/stopped); show its resolved current name and complete instructions at confirmation. Only the selected reference is saved; processing resolves its then-current definition, so later template edits can affect the future job. Ready minutes change format via reformat, not template_ref. Full private source digest and fresh selected template facts bind consent. No new synthesis, recording or email starts. Original document reindexing after a known changed save may incur its existing costs; indexing is not complete. Changed state needs fresh consent. No-op and uncertain saves never authorize automatic replay. Nonadministrator owned scope only.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned meeting and explicit original sparse changes",
            schema=ReportUpdateInput.model_json_schema(),
        )
    ],
    outputs=[OutputFieldSchema(path="draft", type="object", description="Pending confirmation")],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="update_lia_meeting_report", category="tool"),
)
