"""Exact invitation semantics precede source conditional claims and post-commit notices."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    raise_invalid_input,
    raise_not_found_or_unauthorized,
)
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_notifications import notify_saved_peer_action
from src.domains.agents.application.peer_request_schemas import (
    PeerRequestInput,
    PeerRequestPatch,
    PeerRequestSelection,
)
from src.domains.agents.application.peer_request_spec import PEER_REQUEST_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.discovery import mask_email
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.peers.notifications import dispatch_peer_events
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _request_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _request_selection(
    db: AsyncSession, actor_id: UUID, request: PeerRequestInput, *, lock: bool = False
) -> PeerRequestSelection:
    service = PeersService(db)
    target = await _selected_discoverable_target(service, actor_id, request.peer_id)
    pair = await service.repo.get_pair(actor_id, request.peer_id)
    if pair is not None and pair.status == "accepted":
        raise_invalid_input("peers_already_connected")
    if pair is not None and service._declined_cooldown_active(pair, actor_id, datetime.now(UTC)):
        raise_not_found_or_unauthorized("peer", request.peer_id)
    lo, hi = canonical_pair(actor_id, request.peer_id)
    statement = select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
        PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi
    )
    if lock:
        statement = statement.with_for_update()
    stored = await db.scalar(statement)
    before = PeerConnectionStatus(pair.status).value if pair is not None else "absent"
    no_op = before == "pending" and pair is not None and pair.requested_by_id == actor_id
    after = "accepted" if before == "pending" and not no_op else "pending"
    return PeerRequestSelection(
        request=request,
        display_name=(target.full_name or "").strip(),
        email_hint=mask_email(target.email),
        before_status=before,
        after_status=after,
        no_op=no_op,
        state_digest=payload_digest(
            {
                "pair": stored,
                "target": {
                    "id": str(target.id),
                    "name": target.full_name,
                    "email": target.email,
                    "active": target.is_active,
                    "discovery": target.discovery_enabled,
                },
            }
        ),
    )


async def _selected_discoverable_target(
    service: PeersService, actor_id: UUID, peer_id: UUID
) -> User:
    if actor_id == peer_id:
        raise_invalid_input("peers_self_request")
    target = await service._get_discoverable_user(peer_id)
    if (
        target is None
        or not fold_name(target.full_name or "")
        or await service.repo.has_block_between(actor_id, peer_id)
    ):
        raise_not_found_or_unauthorized("peer", peer_id)
    assert target is not None
    return target


async def prepare_peer_request(
    db: AsyncSession, actor_id: UUID, request: PeerRequestInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerRequestInput.model_validate(request.model_dump())
    await _request_access(db, actor_id)
    scope = await _request_selection(db, actor_id, selected)
    await _request_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_REQUEST_OPERATION,
        PeerRequestPatch(peer_request=scope),
        {"peer_request": scope.public_scope()},
        {"peer_request": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_request(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerRequestPatch.model_validate(draft.intent).peer_request
    return draft.before == {"peer_request": scope.public_scope()} and draft.after == {
        "peer_request": scope.public_scope(after=True)
    }


async def _verify_request_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerRequestSelection
) -> None:
    try:
        current = await _request_selection(db, actor_id, expected.request, lock=True)
    except ResourceNotFoundError as exc:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED") from exc
    except DomainValidationError as exc:
        raise ResourceConflictError("peer_request", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_request", detail={"error_code": "STALE_STATE"})


async def execute_peer_request(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if actor_id != draft.actor_id or draft.operation_id != "peer_connection.request":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_request(draft):
        raise ValueError("Invitation requires exact approved target and source state")
    expected = PeerRequestPatch.model_validate(draft.intent).peer_request

    async def check() -> None:
        await _request_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.request.peer_id)
    await check()
    await _verify_request_selection(db, actor_id, expected)
    if expected.no_op:
        receipt.committed = True
        receipt.no_op = True
        return
    service = PeersService(db)
    actual = await service.request_connection(
        actor_id, expected.request.peer_id, expected.request.context_message, _retry_allowed=False
    )
    pair = await service.repo.get_pair(actor_id, expected.request.peer_id)
    if (
        pair is None
        or actual.id != pair.id
        or actual.status != expected.after_status
        or pair.status != expected.after_status
    ):
        raise ValueError("Source invitation postcondition differs from approved result")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    public: dict[str, JsonValue] = {
        **expected.public_scope(after=True),
        "connection_id": str(actual.id),
        "notification_status": "attempted",
    }
    receipt.values = {"peer_request": public}
    await notify_saved_peer_action(service.pending_events, dispatch_peer_events, public)
