"""Editable source requests exclude approval, tenant identity and comparison digests."""

from pydantic import BaseModel, JsonValue

from src.domains.agents.application.sms_action_schemas import (
    SmsErasePatch,
    SmsPreferencePatch,
    SmsSenderBlockPatch,
    SmsTokenCreatePatch,
    SmsTokenCreateRequest,
    SmsTokenRevokePatch,
    SmsTokenRevokeRequest,
)
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.sender_commands import SmsSenderBlockRequest

SMS_EDITOR_MODELS = (
    SmsTokenCreatePatch,
    SmsTokenRevokePatch,
    SmsPreferencePatch,
    SmsSenderBlockPatch,
    SmsErasePatch,
)


def sms_editor_request(
    model: type[BaseModel], intent: dict[str, JsonValue]
) -> tuple[type[BaseModel], dict[str, JsonValue]]:
    if model is SmsTokenCreatePatch:
        return SmsTokenCreateRequest, SmsTokenCreatePatch.model_validate(
            intent
        ).ingestion_token_to_create.model_dump(mode="json")
    if model is SmsTokenRevokePatch:
        return SmsTokenRevokeRequest, {
            "token_id": str(
                SmsTokenRevokePatch.model_validate(intent).ingestion_token_to_revoke.token.id
            )
        }
    if model is SmsPreferencePatch:
        return SmsPreferences, SmsPreferencePatch.model_validate(intent).sms_preferences.model_dump(
            mode="json"
        )
    if model is SmsSenderBlockPatch:
        selected = SmsSenderBlockPatch.model_validate(intent).sms_sender_block
        return SmsSenderBlockRequest, {"sender": selected.sender, "blocked": selected.blocked}
    if model is SmsErasePatch:
        return SmsEraseRequest, SmsErasePatch.model_validate(
            intent
        ).sms_messages_to_delete.request.model_dump(mode="json", exclude_none=True)
    raise ValueError("Unsupported SMS editor")
