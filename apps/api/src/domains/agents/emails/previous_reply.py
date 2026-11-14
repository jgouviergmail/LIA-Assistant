"""What the person already answered to an e-mail they are answering again (ADR-379).

Answering a message twice is the person's right — a follow-up, a correction — but never
blind: the confirmation card says the message was already answered, and a reply LIA
writes reads what the person said, so it continues from it instead of repeating or
contradicting it. The fact comes from the one door (``connectors/mail_reply_states``),
which fails open: a mailbox that cannot tell says nothing, and the reply goes on as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from src.core.field_names import FIELD_BODY
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.mail_reply_states import reply_states_of

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreviousReply:
    """The person's earlier answer to a message.

    Attributes:
        at: When it was sent, in the account's zone; None when only the mailbox's own
            mark says the message was answered and it dates nothing.
        words: The answer's own words; empty when the answer itself was not found in
            the conversation.
    """

    at: datetime | None
    words: str


async def _own_words(client: EmailClientProtocol, message_id: str) -> str:
    """The answer's clean body; empty when it cannot be read again."""
    try:
        message = await client.get_message(message_id, use_cache=False)
    except Exception as error:
        # The excerpt the conversation read already holds stands in: writing a reply
        # is worth more than re-reading the previous one.
        logger.warning("previous_reply_unread", error_type=type(error).__name__)
        return ""
    return str(message.get(FIELD_BODY) or "").strip()


async def previous_reply_of(
    client: EmailClientProtocol,
    original: Mapping[str, Any],
    *,
    user_timezone: str | None,
    with_words: bool = False,
) -> PreviousReply | None:
    """What the person already answered to ``original``, when its mailbox says they did.

    Args:
        client: The mailbox's client.
        original: The message about to be answered, in the ``EmailMessage`` vocabulary.
        user_timezone: The account's zone, for the instant of the earlier answer.
        with_words: Read the earlier answer whole (one more read): a reply LIA writes
            needs its words, a card needs its instant alone.

    Returns:
        The earlier answer; None when the message is not known to be answered.
    """
    states = await reply_states_of(client, [original], user_timezone=user_timezone)
    state = states.get(str(original.get("id") or ""))
    if state is None or state.status != "answered":
        return None
    reply = state.message
    if reply is None:
        return PreviousReply(at=state.marked_at, words="")
    words = (await _own_words(client, reply.message_id) if with_words else "") or reply.excerpt
    return PreviousReply(at=reply.at, words=words)


def answered_fields(previous: PreviousReply | None) -> dict[str, Any]:
    """What a reply's confirmation card carries of an earlier answer (``EmailReplyDraftInput``).

    Args:
        previous: The earlier answer, or None when the message is not known answered.

    Returns:
        ``already_answered`` and ``answered_at`` (an ISO instant, None when undated).
    """
    at = previous.at if previous is not None else None
    return {
        "already_answered": previous is not None,
        "answered_at": at.isoformat() if at is not None else None,
    }


__all__ = ["PreviousReply", "answered_fields", "previous_reply_of"]
