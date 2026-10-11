"""Whole generated-version restoration is a distinct exact HITL action."""

from src.domains.agents.application.meeting_report_restore_schemas import (
    ReportRestoreInput,
    ReportRestorePatch,
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

REPORT_RESTORE_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.restore",
    tool_name="restore_lia_meeting_report_tool",
    sections=("meetings",),
    input_model=ReportRestorePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
REPORT_RESTORE_MANIFEST = ToolManifest(
    name="restore_lia_meeting_report_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to replace the selected owned meeting's entire current minutes with its saved generated version. This is whole-version restoration, never a selective field edit, new synthesis or email. Approval identifies the meeting, current/generated titles, exact participant/section counts and up to twelve literal headings; summary_only explicitly means report text is not displayed. A private digest binds every byte of both original report revisions; changed content requires new consent even when metadata is identical. Preserve location and recorded audio/transcript. The original background knowledge-space reindex may incur its existing embedding costs; queued indexing is not completed indexing. An ongoing generation can later publish another report: do not promise permanent finality. Known commits only; uncertain commits never authorize automatic replay. An already identical saved version is a no-op. No admin data or foreign meetings.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned meeting identifier",
            schema=ReportRestoreInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="restore_lia_meeting_report", category="tool"),
)
