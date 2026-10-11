"""Source-predicted updates execute under the same fences, exact consent and acknowledged commit."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_not_found_or_unauthorized
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_comment import _pending_preview
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.application.workboard_update_schemas import (
    WorkboardUpdateInput,
    WorkboardUpdatePatch,
    WorkboardUpdateSelection,
    canonical_workboard_update,
)
from src.domains.agents.application.workboard_update_spec import WORKBOARD_UPDATE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.answers import Answer
from src.domains.workboard.assignment_notifications import (
    AssignmentNotice,
    dispatch_assignment_notices,
)
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.mutation_fence import lock_mutation_ticket
from src.domains.workboard.mutation_preview import (
    apply_ticket_mutation,
    mutation_event_value,
    preview_ticket_mutation,
    read_mutation_columns,
)
from src.domains.workboard.schemas import TicketRow
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context

_CHANGE_CLOCKS = {"updated_at", "status_changed_at"}


def _result_digest(raw: dict[str, JsonValue], columns: list[dict[str, JsonValue]]) -> str:
    return payload_digest(
        {
            "ticket": {key: value for key, value in raw.items() if key not in _CHANGE_CLOCKS},
            "columns": columns,
        }
    )


def _affected_statuses(status: str, request: WorkboardUpdateInput) -> tuple[str, ...]:
    values = {status}
    if request.status is not None:
        values.add(request.status)
    if request.move is not None:
        values.add(request.move.status)
    if request.run_now:
        values.add("todo")
    return tuple(sorted(values))


async def _peer_update_context(
    db: AsyncSession,
    owner_id: UUID,
    prospective_holder: UUID | None,
    peer_ids: set[UUID],
    *,
    requires_peers: bool,
) -> dict[str, JsonValue]:
    if requires_peers:
        await require_capability_fresh(db, PlatformCapability.PEERS)
    pairs: list[JsonValue] = []
    peers: list[JsonValue] = []
    for identity in sorted(peer_ids):
        lo, hi = canonical_pair(owner_id, identity)
        pair = await db.scalar(
            select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
                PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi
            )
        )
        if identity == prospective_holder and (
            not isinstance(pair, dict) or pair.get("status") != PeerConnectionStatus.ACCEPTED.value
        ):
            raise_not_found_or_unauthorized("peer", identity)
        pairs.append(pair)
        peer = await db.get(User, identity, populate_existing=True)
        if peer is None:
            raise_not_found_or_unauthorized("peer", identity)
        if identity == prospective_holder and (not peer.is_active or peer.deleted_at is not None):
            raise_not_found_or_unauthorized("peer", identity)
        peers.append(
            {
                "id": str(identity),
                "name": peer.full_name,
                "active": peer.is_active,
                "deleted": peer.deleted_at.isoformat() if peer.deleted_at else None,
            }
        )
    return {"pairs": pairs, "peers": peers, "requires_peers": requires_peers}


async def _update_context(
    db: AsyncSession, actor_id: UUID, request: WorkboardUpdateInput, statuses: tuple[str, ...]
) -> tuple[WorkboardTicket, dict[str, JsonValue]]:
    await creation_access(db, actor_id)
    ticket = await WorkboardService(db).repo.get_visible(request.ticket_id, actor_id)
    if ticket is None:
        raise_not_found_or_unauthorized("ticket", request.ticket_id)
    peer_ids = {
        identity
        for identity in (ticket.assignee_user_id, request.assignee_user_id, actor_id)
        if identity is not None and identity != ticket.owner_user_id
    }
    prospective = request.assignee_user_id
    if actor_id != ticket.owner_user_id and prospective not in {None, ticket.owner_user_id}:
        raise_not_found_or_unauthorized("peer", prospective)
    requires_peers = actor_id != ticket.owner_user_id or (
        prospective is not None and prospective != ticket.owner_user_id
    )
    peer_context = await _peer_update_context(
        db, ticket.owner_user_id, prospective, peer_ids, requires_peers=requires_peers
    )
    raw = await db.scalar(
        select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
            WorkboardTicket.id == ticket.id
        )
    )
    if not isinstance(raw, dict):
        raise ValueError("Source mutation context is unavailable")
    notes = await WorkboardService(db).repo.owner_notes_since(
        ticket.id, ticket.owner_user_id, since=ticket.last_run_at, limit=1
    )
    columns: list[JsonValue] = list(await read_mutation_columns(db, ticket.owner_user_id, statuses))
    state: dict[str, JsonValue] = {
        "ticket": raw,
        "columns": columns,
        **peer_context,
        "note": notes[-1].body if notes else None,
        "max_runs": settings.workboard_max_runs_per_ticket,
        "events": int(
            await db.scalar(
                select(func.count(WorkboardTicketEvent.id)).where(
                    WorkboardTicketEvent.ticket_id == request.ticket_id
                )
            )
            or 0
        ),
    }
    if len(json.dumps(state, ensure_ascii=False).encode("utf-8")) > 65536:
        raise ValueError("Source mutation exceeds the exact native confirmation bound")
    return ticket, state


def _answer_update_preview(
    ticket: WorkboardTicket,
    actor_id: UUID,
    request: WorkboardUpdateInput,
    state: dict[str, JsonValue],
    language: str,
    timezone: str,
) -> tuple[list[str], str | None, Answer | None]:
    previews = (
        _pending_preview(ticket.pending_action, language=language, timezone=timezone)
        if ticket.pending_action and ticket.owner_user_id == actor_id
        else []
    )
    answering = (
        ticket.status == "confirming"
        and bool(ticket.pending_action)
        and request.assignee == "lia"
        and ticket.owner_user_id == actor_id
    )
    if not answering:
        return previews, None, None
    note = state["note"]
    answer = WorkboardService.validate_answer(ticket, note) if isinstance(note, str) else None
    return previews, note if isinstance(note, str) else None, answer


def _pending_update_flags(raw: dict[str, JsonValue]) -> tuple[bool, bool]:
    pending = raw.get("pending_action")
    return bool(pending), isinstance(pending, dict) and pending.get("approved") is True


async def prepare_workboard_update(
    db: AsyncSession,
    actor_id: UUID,
    request: WorkboardUpdateInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = WorkboardUpdateInput.model_validate(request.model_dump(exclude_none=True))
    actor = await creation_access(db, actor_id)
    language, timezone = actor.language, actor.timezone
    ticket = await WorkboardService(db).repo.get_visible(request.ticket_id, actor_id)
    if ticket is None:
        raise_not_found_or_unauthorized("ticket", request.ticket_id)
    statuses = _affected_statuses(ticket.status, request)
    ticket, state = await _update_context(db, actor_id, request, statuses)
    owner_id = ticket.owner_user_id
    pending_before = bool(ticket.pending_action)
    pending, answer_note, answer = _answer_update_preview(
        ticket, actor_id, request, state, language, timezone
    )
    before = TicketRow.model_validate(ticket).model_dump(mode="json", exclude=_CHANGE_CLOCKS)
    events_before = int(
        await db.scalar(
            select(func.count(WorkboardTicketEvent.id)).where(
                WorkboardTicketEvent.ticket_id == request.ticket_id
            )
        )
        or 0
    )
    holder_name = None
    if request.assignee_user_id is not None:
        peer = await db.get(User, request.assignee_user_id, populate_existing=True)
        holder_name = peer.full_name if peer else None
    predicted = await preview_ticket_mutation(
        db,
        actor_id,
        request.ticket_id,
        request.source_changes(),
        move=request.move,
        run_now=request.run_now,
        statuses=statuses,
    )
    after = {key: value for key, value in predicted.ticket.items() if key not in _CHANGE_CLOCKS}
    pending_after, pending_approved = _pending_update_flags(predicted.raw)
    if before == after and not predicted.events:
        raise ValueError("Select an actual source change")
    selection = WorkboardUpdateSelection(
        request=request,
        before=before,
        after=after,
        pending_preview=pending,
        answer_note=answer_note,
        answer=answer,
        pending_before=pending_before,
        pending_after=pending_after,
        pending_approved=pending_approved,
        holder_name=holder_name,
        owner_id=owner_id,
        requires_peers=bool(state["requires_peers"]),
        statuses=statuses,
        events_before=events_before,
        expected_events=predicted.events,
        state_digest=payload_digest(state),
        result_digest=_result_digest(predicted.raw, predicted.columns),
    )
    _, fresh = await _update_context(db, actor_id, request, statuses)
    if payload_digest(fresh) != selection.state_digest:
        raise ResourceConflictError("workboard_update", detail={"error_code": "STALE_STATE"})
    if (
        len(json.dumps(selection.public_scope(after=True), ensure_ascii=False).encode("utf-8"))
        > 65536
    ):
        raise ValueError("Source update preview exceeds the exact bound")
    return build_action_content(
        actor_id,
        WORKBOARD_UPDATE_OPERATION,
        WorkboardUpdatePatch(workboard_update=selection),
        {"workboard_update": selection.public_scope()},
        {"workboard_update": selection.public_scope(after=True)},
        command_id=command_id,
    )


async def _verify_update(
    db: AsyncSession, expected: WorkboardUpdateSelection, events: list[WorkboardTicketEvent]
) -> TicketRow:
    ticket = await db.scalar(
        select(WorkboardTicket)
        .where(WorkboardTicket.id == expected.request.ticket_id)
        .execution_options(populate_existing=True)
    )
    raw = await db.scalar(
        select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
            WorkboardTicket.id == expected.request.ticket_id
        )
    )
    if ticket is None or not isinstance(raw, dict):
        raise ValueError("Source did not persist the confirmed update")
    columns = await read_mutation_columns(db, expected.owner_id, expected.statuses)
    if _result_digest(raw, columns) != expected.result_digest:
        raise ValueError("Source persisted a different update")
    actual_events: list[dict[str, JsonValue]] = []
    for event in events:
        actual = await db.get(WorkboardTicketEvent, event.id, populate_existing=True)
        if actual is None or actual.ticket_id != expected.request.ticket_id:
            raise ValueError("Source must persist its mutation history")
        actual_events.append(mutation_event_value(actual))
    total = await db.scalar(
        select(func.count(WorkboardTicketEvent.id)).where(
            WorkboardTicketEvent.ticket_id == expected.request.ticket_id
        )
    )
    if actual_events != expected.expected_events or total != expected.events_before + len(
        expected.expected_events
    ):
        raise ValueError("Source mutation history differs from the approved change")
    return TicketRow.model_validate(ticket)


async def _notify_update(notices: list[AssignmentNotice], public: dict[str, JsonValue]) -> None:
    if not notices:
        return
    try:
        async with get_db_context() as db:
            delivered = await dispatch_assignment_notices(db, notices)
        public["notification_status"] = "delivered" if delivered else "failed"
    except Exception:
        public["notification_status"] = "failed"


async def execute_workboard_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != WORKBOARD_UPDATE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_workboard_update(draft):
        raise ValueError("Update requires exact canonical consent")
    expected = WorkboardUpdatePatch.model_validate(draft.intent).workboard_update
    await creation_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    await lock_mutation_ticket(
        db, actor_id, expected.request.ticket_id, expected.request.assignee_user_id
    )
    _, current = await _update_context(db, actor_id, expected.request, expected.statuses)
    if payload_digest(current) != expected.state_digest:
        raise ResourceConflictError("workboard_update", detail={"error_code": "STALE_STATE"})
    actor = await creation_access(db, actor_id)
    notices: list[AssignmentNotice] = []
    events: list[WorkboardTicketEvent] = []
    await apply_ticket_mutation(
        db,
        actor,
        expected.request.ticket_id,
        expected.request.source_changes(),
        move=expected.request.move,
        run_now=expected.request.run_now,
        notices=notices,
        events=events,
    )
    actual = await _verify_update(db, expected, events)
    await creation_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if expected.requires_peers:
        await require_capability_fresh(db, PlatformCapability.PEERS)
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    public = {**expected.public_scope(after=True), "ticket": actual.model_dump(mode="json")}
    receipt.committed = True
    receipt.values = {"workboard_update": public}
    await _notify_update(notices, public)
