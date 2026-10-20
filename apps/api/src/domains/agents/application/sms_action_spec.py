"""SMS actions use the existing exact native-command identities."""

from pydantic import BaseModel

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.sms_action_schemas import (
    SmsErasePatch,
    SmsPreferencePatch,
    SmsSenderBlockPatch,
    SmsTokenCreatePatch,
    SmsTokenRevokePatch,
)
from src.domains.feature_switches.registry import PlatformCapability


def _spec(
    name: str, tool: str, model: type[BaseModel], *, device: bool = False
) -> ApplicationOperationSpec:
    return ApplicationOperationSpec(
        operation_id=name,
        tool_name=tool,
        sections=("sms",),
        input_model=model,
        output_model=ApplicationExecutionOutcome,
        kind=OperationKind.DEVICE if device else OperationKind.ACTION,
        required_capabilities=(PlatformCapability.SMS,),
    )


SMS_TOKEN_CREATE_OPERATION = _spec(
    "sms_token.create", "create_lia_sms_ingestion_token_tool", SmsTokenCreatePatch, device=True
)
SMS_TOKEN_REVOKE_OPERATION = _spec(
    "sms_token.revoke", "revoke_lia_sms_ingestion_token_tool", SmsTokenRevokePatch
)
SMS_PREFERENCE_OPERATION = _spec(
    "sms_preferences.update", "update_lia_sms_preferences_tool", SmsPreferencePatch
)
SMS_SENDER_BLOCK_OPERATION = _spec(
    "sms_sender_block.update", "set_lia_sms_sender_block_tool", SmsSenderBlockPatch
)
SMS_ERASE_OPERATION = _spec("sms_messages.delete", "delete_lia_sms_tool", SmsErasePatch)
SMS_NATIVE_OPERATIONS = (
    SMS_TOKEN_CREATE_OPERATION,
    SMS_TOKEN_REVOKE_OPERATION,
    SMS_PREFERENCE_OPERATION,
    SMS_SENDER_BLOCK_OPERATION,
    SMS_ERASE_OPERATION,
)
SMS_ACTION_SPECS = {spec.operation_id: spec for spec in SMS_NATIVE_OPERATIONS}
