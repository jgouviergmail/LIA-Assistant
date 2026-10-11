"""Sending requires explicit consent naming recipient, route, literal words and exact source."""

from src.domains.agents.application.email_share_send_schemas import EmailShareSendPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

EMAIL_SHARE_SEND_OPERATION = ApplicationOperationSpec(
    operation_id="email_share.send",
    tool_name="send_lia_email_share_tool",
    sections=("generated-assets",),
    input_model=EmailShareSendPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.EMAIL_SHARE,),
)
