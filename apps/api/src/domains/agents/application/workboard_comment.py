"""Source comments and pending answers run only after an exact short-transaction confirmation."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_not_found_or_unauthorized
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.workboard_comment_schemas import (
    WorkboardCommentInput,
    WorkboardCommentPatch,
    WorkboardCommentSelection,
    canonical_workboard_comment,
)
from src.domains.agents.application.workboard_comment_spec import WORKBOARD_COMMENT_OPERATION
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.effects.digest import payload_digest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.answers import Answer
from src.domains.workboard.comment_fence import lock_comment_ticket
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.schemas import CommentCreate
from src.domains.workboard.service import WorkboardService


def _pending_preview(pending: dict[str, object], *, language: str, timezone: str) -> list[str]:
    from src.domains.agents.drafts.preview_renderer import render_detailed_preview

    batch = pending.get("batch")
    items = batch if isinstance(batch, list) and batch else [pending]
    previews: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("draft_content"), dict):
            raise ValueError("Pending action is not a source draft")
        draft = Draft(type=DraftType(item.get("draft_type")), content=item["draft_content"])
        previews.append(render_detailed_preview(draft, language, timezone))
    return previews


async def _comment_selection(
    db: AsyncSession, actor_id: UUID, request: WorkboardCommentInput
) -> WorkboardCommentSelection:
    actor = await creation_access(db, actor_id)
    service = WorkboardService(db)
    ticket = await service.repo.get_visible(request.ticket_id, actor_id)
    if ticket is None:
        raise_not_found_or_unauthorized("ticket", request.ticket_id)
    body = service.clean_comment(request.body)
    raw = await db.scalar(
        select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
            WorkboardTicket.id == ticket.id
        )
    )
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > 65536:
        raise ValueError("Ticket exceeds the complete native confirmation bound")
    pending = ticket.pending_action or {}
    answer = service.comment_answer(ticket, actor, body)
    previews = (
        _pending_preview(pending, language=actor.language, timezone=actor.timezone)
        if answer is not None
        else []
    )
    selection = WorkboardCommentSelection(
        request=WorkboardCommentInput(ticket_id=ticket.id, body=body),
        title=ticket.title,
        owner_id=ticket.owner_user_id,
        status=ticket.status,
        assignee_kind=ticket.assignee_kind,
        holder_id=ticket.effective_assignee_id,
        answer=answer,
        pending_preview=previews,
        max_comment_chars=settings.workboard_comment_max_chars,
        max_runs=settings.workboard_max_runs_per_ticket,
        state_digest=payload_digest(raw),
    )
    if len(json.dumps(selection.public_scope(), ensure_ascii=False).encode("utf-8")) > 65536:
        raise ValueError("Comment preview exceeds the complete native confirmation bound")
    return selection


async def prepare_workboard_comment(
    db: AsyncSession,
    actor_id: UUID,
    request: WorkboardCommentInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = WorkboardCommentInput.model_validate(request.model_dump())
    scope = await _comment_selection(db, actor_id, selected)
    await creation_access(db, actor_id)
    return build_action_content(
        actor_id,
        WORKBOARD_COMMENT_OPERATION,
        WorkboardCommentPatch(workboard_comment=scope),
        {"workboard_comment": scope.public_scope()},
        {"workboard_comment": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_workboard_comment(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != WORKBOARD_COMMENT_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_workboard_comment(draft):
        raise ValueError("Comment requires exact canonical consent")
    expected = WorkboardCommentPatch.model_validate(draft.intent).workboard_comment

    async def check() -> User:
        actor = await creation_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        return actor

    await check()
    await lock_comment_ticket(db, actor_id, expected.request.ticket_id)
    actor = await check()
    if await _comment_selection(db, actor_id, expected.request) != expected:
        raise ResourceConflictError("workboard_comment", detail={"error_code": "STALE_STATE"})
    before = await _raw_ticket(db, expected.request.ticket_id)
    posted = await WorkboardService(db).comment(
        actor,
        expected.request.ticket_id,
        CommentCreate(body=expected.request.body),
        comment_id=draft.command_id,
    )
    await db.flush()
    actual = await _verify_comment(db, actor_id, draft.command_id, posted, expected)
    await _verify_answer(db, expected, before)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {
        "workboard_comment": {**expected.public_scope(after=True), "comment_id": str(actual.id)}
    }


async def _raw_ticket(db: AsyncSession, identity: UUID) -> dict[str, object]:
    raw: dict[str, object] | None = await db.scalar(
        select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
            WorkboardTicket.id == identity
        )
    )
    if not isinstance(raw, dict):
        raise ValueError("Persisted ticket is unavailable")
    return raw


async def _verify_comment(
    db: AsyncSession,
    actor_id: UUID,
    identity: UUID,
    posted: WorkboardComment,
    expected: WorkboardCommentSelection,
) -> WorkboardComment:
    actual = await db.scalar(
        select(WorkboardComment)
        .where(WorkboardComment.id == identity)
        .execution_options(populate_existing=True)
    )
    if actual is None or posted.id != identity:
        raise ValueError("Source must persist the approved comment identity")
    wanted = {
        "ticket_id": expected.request.ticket_id,
        "body": expected.request.body,
        "author_user_id": actor_id,
        "author_kind": "user" if expected.owner_id == actor_id else "peer",
    }
    if any(getattr(actual, key) != value for key, value in wanted.items()):
        raise ValueError("Source must persist the exact approved comment")
    return actual


async def _verify_answer(
    db: AsyncSession, expected: WorkboardCommentSelection, before: dict[str, object]
) -> None:
    after = await _raw_ticket(db, expected.request.ticket_id)
    if expected.answer is None:
        if after != before:
            raise ValueError("An ordinary comment must not change the ticket")
        return
    status = "done" if expected.answer == Answer.REFUSE else "todo"
    pending = before.get("pending_action")
    desired_pending = (
        {**pending, "approved": True}
        if isinstance(pending, dict) and expected.answer == Answer.APPROVE
        else None
    )
    if after.get("status") != status or after.get("pending_action") != desired_pending:
        raise ValueError("Source must persist the exact displayed pending answer")
    changed = {"status", "pending_action", "status_changed_at", "position", "updated_at"}
    if expected.answer != Answer.REFUSE:
        desired = {
            "assignee_kind": "lia",
            "assignee_user_id": None,
            "follow_assignee": False,
            "run_attempts": 0,
            "run_not_before": None,
        }
        if any(after.get(key) != value for key, value in desired.items()):
            raise ValueError("Source must persist the exact displayed LIA handover")
        changed.update(desired)
    if any(after.get(key) != value for key, value in before.items() if key not in changed):
        raise ValueError("Comment changed an unrelated ticket field")
