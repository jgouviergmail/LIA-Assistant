"""Current minutes PDF export through a single original-browser HITL continuation."""

from src.domains.agents.application.meeting_pdf_schemas import MeetingPDFInput, MeetingPDFPatch
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

MEETING_PDF_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.download",
    tool_name="download_lia_meeting_pdf_tool",
    sections=("meetings",),
    input_model=MeetingPDFPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_PDF_MANIFEST = ToolManifest(
    name="download_lia_meeting_pdf_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL to download one owned READY meeting's entire current minutes as a PDF in the original authenticated browser. Proposal seals report and original dated/localized header without generating PDF bytes or placing report text in prompts. Approval shows identity, title, filename, language and exact participant/section counts. No email, new synthesis, recording or report mutation. A changed report/header requires new consent. After confirmation the browser must use its single-use download continuation; no browser origin means unavailable. Transfer freezes the approved original PDF bytes. download_requested is not save_confirmed: never claim the user saved or read the file. No PDF base64, storage paths or credentials in chat. Original CPU rendering runs off the event loop; no new LLM request or cost path.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned ready meeting identifier",
            schema=MeetingPDFInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending original-browser confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="📄", i18n_key="download_lia_meeting_pdf", category="tool"),
)
