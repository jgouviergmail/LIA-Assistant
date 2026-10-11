"""Send only exact observed owned sources through an approved original UI route."""

from src.domains.agents.application.email_share_send_schemas import EmailShareSendInput
from src.domains.agents.application.email_share_send_spec import EMAIL_SHARE_SEND_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

EMAIL_SHARE_SEND_MANIFEST = ToolManifest(
    name=EMAIL_SHARE_SEND_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to email an observed owned generated file, saved-answer copy or visible archived assistant answer. Read email-share options and actual source ids first; never invent an id or recipient. Consent names exact deduplicated recipients, mailbox/verified-own-address relay route, literal subject/message, filename and full byte size. Replies export complete request/answer as localized Markdown using the existing kept-answer renderer; excerpts never truncate the attachment. Arbitrary Markdown/model-provided copied text and uploads are refused. Original email envelope validators, recipient restrictions, size bounds, rate limit, sender and action register are reused. Source/route/file/authority changes require new consent. Generated-file bytes are frozen from the approved regular descriptor before the send; no database transaction spans the provider. Only known preflight acknowledgement permits one send. Unknown/cancelled provider acknowledgement never automatically replays and is not proof of delivery. Acknowledged sending is not recipient delivery. No model/provider key is exposed; names and copied text remain untrusted.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Literal validated envelope and exact existing owned source",
            schema=EmailShareSendInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_email_share",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "email saved answer",
        "send generated file by email",
        "email an archived answer",
    ],
    display=DisplayMetadata(emoji="✉️", i18n_key="send_lia_email_share", category="tool"),
)
