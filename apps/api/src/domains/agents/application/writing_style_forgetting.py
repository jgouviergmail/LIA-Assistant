"""Forgetting the writing style from the conversation removes the very record confirmed.

The card names the record — when it was learned, from how many e-mails — and the
execution removes that record only, in one conditioned statement: a style learned again
since the card is another record, kept, and the card answers a stale state. The switch
does not matter (ADR-280: it removes the capability, never the record), and the person's
e-mails are never touched.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.writing_style_queries import forget_scope
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleForgetPatch,
    WritingStyleForgetRequest,
)
from src.domains.agents.application.writing_style_spec import WRITING_STYLE_FORGET_OPERATION
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.writing_style.repository import WritingStyleRepository


async def prepare_writing_style_forgetting(
    db: AsyncSession,
    actor_id: UUID,
    request: WritingStyleForgetRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    """The card of a forgetting: the record it removes; nothing removed yet."""
    WritingStyleForgetRequest.model_validate(request.model_dump())
    record = await forget_scope(db, actor_id)
    return build_action_content(
        actor_id,
        WRITING_STYLE_FORGET_OPERATION,
        WritingStyleForgetPatch(writing_style_record=record),
        {"writing_style_record": record.model_dump(mode="json")},
        {"writing_style_record": None},
        command_id=command_id,
    )


def canonical_writing_style_forgetting(draft: ApplicationActionDraftContent) -> bool:
    """Whether the card says exactly what its intent binds (pure)."""
    record = WritingStyleForgetPatch.model_validate(draft.intent).writing_style_record
    return draft.before == {"writing_style_record": record.model_dump(mode="json")} and (
        draft.after == {"writing_style_record": None}
    )


async def execute_writing_style_forgetting(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    """Remove the confirmed record, and nothing learned since.

    Raises:
        CommandRejected: Not the actor's card, expired, or a commit whose outcome is unknown.
        ResourceConflictError: The record is no longer the one the card showed.
    """
    if (
        draft.actor_id != actor_id
        or draft.operation_id != WRITING_STYLE_FORGET_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_writing_style_forgetting(draft):
        raise CommandRejected("INVALID_INPUT")
    record = WritingStyleForgetPatch.model_validate(draft.intent).writing_style_record
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if await forget_scope(db, actor_id) != record:
        raise ResourceConflictError("writing_style", detail={"error_code": "STALE_STATE"})
    removed = await WritingStyleRepository(db).forget(
        actor_id, learned_at=datetime.fromisoformat(record.learned_at)
    )
    if not removed:
        raise ResourceConflictError("writing_style", detail={"error_code": "STALE_STATE"})
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {"writing_style_record": {**record.model_dump(mode="json"), "removed": True}}
