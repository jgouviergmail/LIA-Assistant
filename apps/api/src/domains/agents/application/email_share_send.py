"""A durable original command sends once; unknown preflight/provider acknowledgement never replays."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.email_share_read import _access
from src.domains.agents.application.email_share_send_schemas import (
    EmailShareSendInput,
    EmailShareSendPatch,
    EmailShareSnapshot,
    canonical_email_share,
)
from src.domains.agents.application.email_share_send_source import prepare_exact_email_source
from src.domains.agents.application.email_share_send_spec import EMAIL_SHARE_SEND_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.email_share.rate_limits import rate_limit_email_share
from src.domains.email_share.service import PreparedShare, StoredFile, deliver_share, resolve_route
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def _commit_preflight(db: AsyncSession) -> None:
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error


async def _observe(
    db: AsyncSession, actor_id: UUID, request: EmailShareSendInput, *, freeze: bool = False
) -> tuple[EmailShareSnapshot, PreparedShare]:
    actor = await _access(db, actor_id)
    await _commit_preflight(db)
    route = await resolve_route(actor)
    if freeze:
        actor = authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    prepared, digest, preview = await prepare_exact_email_source(
        db, actor, request, route, freeze=freeze
    )
    if freeze:
        prepared = replace(prepared, single_attempt=True)
    source = prepared.source
    name = source.filename if isinstance(source, StoredFile) else source.attachment.filename
    mime = source.mime_type if isinstance(source, StoredFile) else source.attachment.mime_type
    scope = EmailShareSnapshot(
        request=request,
        route=prepared.route.kind,
        connector_type=route.connector_type.value if route.connector_type is not None else None,
        recipients=tuple(prepared.recipients),
        filename=name,
        file_bytes=source.size,
        content_type=mime,
        answer_preview=preview,
        state_digest=payload_digest(
            {
                "source": digest,
                "route": {
                    "kind": route.kind,
                    "connector_type": str(route.connector_type),
                    "own_address": route.own_address,
                    "max_file_bytes": route.max_file_bytes,
                    "needs_reconnect": route.needs_reconnect,
                },
            }
        ),
    )
    await _access(db, actor_id)
    return scope, prepared


async def prepare_email_share(
    db: AsyncSession,
    actor_id: UUID,
    request: EmailShareSendInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = EmailShareSendInput.model_validate(request.model_dump())
    scope, _ = await _observe(db, actor_id, desired)
    return build_action_content(
        actor_id,
        EMAIL_SHARE_SEND_OPERATION,
        EmailShareSendPatch(email_to_send=scope),
        {"email_to_send": scope.public_scope()},
        {"email_to_send": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_email_share(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != EMAIL_SHARE_SEND_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_email_share(draft):
        raise CommandRejected("INVALID_INPUT")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    expected = EmailShareSendPatch.model_validate(draft.intent).email_to_send
    actor = await _access(db, actor_id)
    await _commit_preflight(db)
    await rate_limit_email_share(actor)
    observed, prepared = await _observe(db, actor_id, expected.request, freeze=True)
    if observed != expected:
        raise CommandRejected("STALE_STATE")
    await _access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    try:
        result = await deliver_share(actor_id, prepared)
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {
        "email_to_send": {
            **expected.public_scope(after=True),
            "provider_acknowledged": True,
            "recipient_delivery_confirmed": False,
            "result": result.model_dump(mode="json"),
        }
    }
