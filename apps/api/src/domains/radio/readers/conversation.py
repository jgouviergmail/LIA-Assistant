"""The conversation under way, as a draft for the personal corner.

What the listener last asked LIA — if they asked it in the last few hours —
lets the station pick up the thread (« earlier you were asking about… »). The
question is read through the conversation repository's own « last user message »
(visible rows only: a run's synthetic question is not the person speaking), and
only the question is quoted: LIA's answer is hers, already said.

The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from typing import Final
from uuid import UUID

from src.domains.conversations.repository import ConversationRepository
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import PersonalDraft
from src.domains.radio.readers.messages import MessageRow, excerpt
from src.infrastructure.database.session import get_db_context

#: How long a question still belongs to « the conversation under way ».
CONVERSATION_RECENT_HOURS: Final[int] = 3


def conversation_drafts(
    message: MessageRow | None, *, since: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The listener's last question as a draft, when it is recent and says something.

    Args:
        message: Their last visible message, if any.
        since: The oldest instant still « under way ».
        tz: The listener's timezone.

    Returns:
        One draft, or none.
    """
    if message is None or message.role != "user" or message.created_at < since:
        return []
    quoted = excerpt(message.content)
    if not quoted:
        return []
    when = local_time_text(message.created_at.astimezone(tz))
    return [
        PersonalDraft(
            FactKind.CONVERSATION,
            f'On {when}, the listener asked LIA: "{quoted}"',
            f"conversation:{message.id}",
            Sensitivity.PERSONAL,
        )
    ]


async def read_conversation(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The conversation under way, read from the listener's last visible question.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft, or none.
    """
    async with get_db_context() as db:
        repository = ConversationRepository(db)
        conversation = await repository.get_active_for_user(user_id)
        if conversation is None:
            return []
        message = await repository.get_last_user_message(conversation.id)
        return conversation_drafts(
            message, since=now - timedelta(hours=CONVERSATION_RECENT_HOURS), tz=tz
        )


__all__ = ["CONVERSATION_RECENT_HOURS", "conversation_drafts", "read_conversation"]
