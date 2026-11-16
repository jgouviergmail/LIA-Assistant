"""Which discussion a run's bill belongs to — named by the door writing its words.

A run is billed on one ``message_token_summary`` row (unique on ``run_id``).
The history shows a bill under the bubble of the run's words when both name
the same discussion, a bill naming none under Main alone (the legacy rule of
``message_reads.history_with_tokens``); a discussion's totals sum the bills
naming it (``ConversationRepository.get_token_totals``).

The first writer of a bill sets its discussion and no later writer changes it
(``ChatRepository.create_or_update_token_summary``). A run whose spend starts
outside any discussion — a call's lookups during the call and its synthesis
after it, a meeting's processing — is therefore billed with none. Since the
return of an act begun in an annex is written there (ADR-378 amendment
2026-11-14), its bubble showed no cost, and no discussion's totals ever
counted it (Main's included). The door writing a run's words into a
discussion names the bill's discussion here: the notification dispatcher's
archive and the voice relay's turn.

Only a bill naming no discussion is named. A bill already attached keeps its
discussion; a bill a reset detached (``ConversationLifecycle``) is named again
only when its words are written again. Nothing past is rewritten: a bill
naming no discussion may be legacy or detached, and the two cannot be told
apart.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation


async def attach_run_bill(
    db: AsyncSession,
    *,
    owner_id: UUID,
    run_id: str,
    conversation_id: UUID,
    revision: int | None = None,
) -> bool:
    """Name the discussion of a run's bill when no writer named one.

    Runs on the caller's session, in the transaction that writes the run's
    words (or decides where they go), so the bill and the words name the same
    generation.

    Args:
        db: The caller's session.
        owner_id: The account the run belongs to; another account's bill is
            never touched.
        run_id: The run whose bill is named.
        conversation_id: The discussion the run's words are written in.
        revision: The generation of an annex the words go to, decided before
            this write: the bill is named only while that generation lives.
            None when the words were just written in the same transaction.

    Returns:
        Whether a bill was named.
    """
    stmt = (
        update(MessageTokenSummary)
        .where(
            MessageTokenSummary.user_id == owner_id,
            MessageTokenSummary.run_id == run_id,
            MessageTokenSummary.conversation_id.is_(None),
        )
        .values(conversation_id=conversation_id, updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    if revision is not None:
        stmt = stmt.where(
            exists().where(
                Conversation.id == conversation_id,
                Conversation.user_id == owner_id,
                Conversation.revision == revision,
                Conversation.deleted_at.is_(None),
            )
        )
    result = await db.execute(stmt)
    # ``execute`` is typed ``Result[Any]``; an UPDATE yields the concrete
    # ``CursorResult`` carrying ``rowcount``: ``getattr`` keeps it typed without
    # a cast (the idiom of ``ConversationRepository.delete_messages_for_conversation``).
    return bool(getattr(result, "rowcount", 0))


__all__ = ["attach_run_bill"]
