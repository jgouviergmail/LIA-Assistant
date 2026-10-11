"""One platform minutes email requires original exact human consent."""

from src.domains.agents.application.meeting_email_schemas import (
    MeetingEmailInput,
    MeetingEmailPatch,
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

MEETING_EMAIL_OPERATION = ApplicationOperationSpec(
    operation_id="meeting_report.email",
    tool_name="email_lia_meeting_report_tool",
    sections=("meetings",),
    input_model=MeetingEmailPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.MEETINGS,),
)
MEETING_EMAIL_MANIFEST = ToolManifest(
    name="email_lia_meeting_report_tool",
    agent="setting_agent",
    description="Prepare mandatory original HITL to email the entire selected owned ready meeting's current minutes to the account's own email from the platform SMTP sender. No arbitrary recipient, mailbox connector or new synthesis. Consent displays recipient, sender, subject, language and exact participant/section counts. summary_only means report body is not displayed; a private digest binds complete HTML/plain-text body and dated headers. Any changed report, recipient, sender, language or previous send date needs fresh consent. A newly confirmed request can intentionally resend. SMTP acknowledgment never proves recipient delivery or reading; a failed/unknown acknowledgment never permits automatic resend. Recording the send date can fail after SMTP succeeded; retain the truthful provider receipt. No paid LLM/provider call is added. Foreign/admin meetings are excluded.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned ready meeting identifier",
            schema=MeetingEmailInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="email_lia_meeting_report", category="tool"),
)
