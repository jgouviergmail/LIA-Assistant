"""Prepare source-owned snapshots; exact confirmation precedes every SMS write."""

from enum import Enum
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.sms_action_schemas import (
    SmsErasePatch,
    SmsPreferencePatch,
    SmsSenderBlockPatch,
    SmsTokenCreatePatch,
    SmsTokenCreateRequest,
    SmsTokenRevokePatch,
    SmsTokenRevokeRequest,
)
from src.domains.agents.application.sms_action_spec import SMS_ACTION_SPECS
from src.domains.ingestion.registry import IngestionResource
from src.domains.ingestion.token_commands import read_owned_token
from src.domains.sms.management_commands import prepare_sms_erasure
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.reads import require_read
from src.domains.sms.sender_commands import SmsSenderBlockRequest, prepare_sender_block

_T = TypeVar("_T", bound=BaseModel)
_JSON = TypeAdapter(dict[str, JsonValue])


def _request(model: type[_T], payload: dict[str, JsonValue]) -> _T:
    # Materialise defaults before build_action_content excludes unset fields.
    return model.model_validate(model.model_validate(payload).model_dump())


def _json(value: BaseModel) -> dict[str, JsonValue]:
    return _JSON.validate_python(value.model_dump(mode="json"))


class SmsManagementAudience(Enum):
    """Trusted adapter identity; never an HTTP/tool parameter or draft field."""

    ASSISTANT = "assistant"
    SETTINGS = "settings"


async def authorize_sms_management(
    db: AsyncSession,
    owner: UUID,
    origin: ApplicationOrigin | None = None,
    *,
    browser: bool = False,
    audience: SmsManagementAudience = SmsManagementAudience.ASSISTANT,
) -> None:
    if audience is not SmsManagementAudience.SETTINGS:
        await require_application_tools(db)
    await require_read(db, owner, assistant=False)
    if browser or audience is SmsManagementAudience.SETTINGS:
        if origin is None:
            raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
        await origin.require_session(owner, expected_binding=origin.binding_id)
        await require_read(db, owner, assistant=False)


async def prepare_sms_action(
    db: AsyncSession,
    owner: UUID,
    operation: str,
    payload: dict[str, JsonValue],
    *,
    origin: ApplicationOrigin | None = None,
    command_id: UUID | None = None,
    audience: SmsManagementAudience = SmsManagementAudience.ASSISTANT,
) -> ApplicationActionDraftContent:
    spec = SMS_ACTION_SPECS.get(operation)
    if spec is None:
        raise CommandRejected("UNKNOWN_OPERATION")
    await authorize_sms_management(
        db, owner, origin, browser=operation == "sms_token.create", audience=audience
    )
    if operation == "sms_token.create":
        create_request = _request(SmsTokenCreateRequest, payload)
        patch: BaseModel = SmsTokenCreatePatch(ingestion_token_to_create=create_request)
        before: dict[str, JsonValue] = {"ingestion_token_to_create": None}
        after = _json(patch)
    elif operation == "sms_token.revoke":
        selected = await read_owned_token(
            db, owner, _request(SmsTokenRevokeRequest, payload).token_id
        )
        if selected.token.resource != IngestionResource.SMS:
            raise CommandRejected("FORBIDDEN")
        patch = SmsTokenRevokePatch(ingestion_token_to_revoke=selected)
        before = {"ingestion_token_to_revoke": selected.public_scope()}
        after = {"ingestion_token_to_revoke": {**selected.public_scope(), "revoked": True}}
    elif operation == "sms_preferences.update":
        actor = await require_read(db, owner, assistant=False)
        patch = SmsPreferencePatch(sms_preferences=_request(SmsPreferences, payload))
        before = {"sms_preferences": _json(SmsPreferences.from_stored(actor.sms_preferences))}
        after = _json(patch)
    elif operation == "sms_sender_block.update":
        block_request = _request(SmsSenderBlockRequest, payload)
        block = await prepare_sender_block(
            db, owner, block_request.sender, blocked=block_request.blocked
        )
        patch = SmsSenderBlockPatch(sms_sender_block=block)
        before = {"sms_sender_block": {"sender": block.sender, "blocked": block.previously_blocked}}
        after = {"sms_sender_block": {"sender": block.sender, "blocked": block.blocked}}
    else:
        selection = await prepare_sms_erasure(db, owner, _request(SmsEraseRequest, payload))
        patch = SmsErasePatch(sms_messages_to_delete=selection)
        before = {"sms_messages_to_delete": _JSON.validate_python(selection.public_scope())}
        after = {"sms_messages_to_delete": None}
    return build_action_content(owner, spec, patch, before, after, command_id=command_id)


def canonical_sms_action(draft: ApplicationActionDraftContent) -> bool:
    spec = SMS_ACTION_SPECS.get(draft.operation_id)
    if spec is None:
        return False
    patch = spec.input_model.model_validate(draft.intent)
    if isinstance(patch, SmsTokenCreatePatch):
        return draft.before == {"ingestion_token_to_create": None} and draft.after == _json(patch)
    if isinstance(patch, SmsTokenRevokePatch):
        public = patch.ingestion_token_to_revoke.public_scope()
        return draft.before == {"ingestion_token_to_revoke": public} and draft.after == {
            "ingestion_token_to_revoke": {**public, "revoked": True}
        }
    if isinstance(patch, SmsPreferencePatch):
        previous = SmsPreferencePatch.model_validate(draft.before)
        return draft.before == _json(previous) and draft.after == _json(patch)
    if isinstance(patch, SmsSenderBlockPatch):
        block = patch.sms_sender_block
        return draft.before == {
            "sms_sender_block": {"sender": block.sender, "blocked": block.previously_blocked}
        } and draft.after == {
            "sms_sender_block": {"sender": block.sender, "blocked": block.blocked}
        }
    if isinstance(patch, SmsErasePatch):
        return draft.before == {
            "sms_messages_to_delete": patch.sms_messages_to_delete.public_scope()
        } and draft.after == {"sms_messages_to_delete": None}
    return False
