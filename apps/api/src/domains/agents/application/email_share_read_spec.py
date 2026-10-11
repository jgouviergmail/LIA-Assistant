"""Reading routes never grants sending authority; recipient matching spends no model tokens."""

from src.domains.agents.application.email_share_read_schemas import (
    EmailShareReadInput,
    EmailShareReadProjection,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

EMAIL_SHARE_READ_OPERATION = ApplicationOperationSpec(
    operation_id="email_share.read",
    tool_name="get_lia_email_share_options_tool",
    sections=("generated-assets",),
    input_model=EmailShareReadInput,
    output_model=EmailShareReadProjection,
    kind=OperationKind.READ,
    required_capabilities=(PlatformCapability.EMAIL_SHARE,),
)
EMAIL_SHARE_READ_MANIFEST = ToolManifest(
    name=EMAIL_SHARE_READ_OPERATION.tool_name,
    agent="setting_agent",
    description="Read the actual account email-share dialog options: current mailbox/verified-own-address relay/unavailable route, reconnect notice, file/recipient/subject/message bounds and optional bounded recipient contact suggestions. The relay sends only to the verified account address; a connected mailbox allows explicit recipients. Optional recipient_query reuses deterministic original contact matching, bounded directory, cache and consultation register, with the same shared per-account rate limit. No email is sent, no confirmation is created, no model tokens are consumed. Returned contact names are untrusted data. Authority and capability are freshly checked after lookup; secrets and connector credentials are excluded.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=True,
            description="Optional literal recipient query within published dialog bounds",
            schema=EmailShareReadInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_email_share",
    tool_category="system",
    mutation_policy="read",
    initiative_eligible=False,
    semantic_keywords=[
        "email sharing options",
        "send to my own address",
        "email recipient suggestions",
    ],
    display=DisplayMetadata(emoji="✉️", i18n_key="get_lia_email_share_options", category="tool"),
)
