"""What an e-mail card says of its reply state: only what stays true (ADR-379).

A card is archived HTML, replayed weeks later and exported without the turn that made
it. « Answered » and « a reply came » are facts and stay true: they are drawn. « No
reply yet » and « an answer is drafted » are the reading of a moment: drawn, they would
lie as soon as the person answers — a model is told those, at show time, by the
projection (``core/annotation_projection``); a card never is.
"""

from __future__ import annotations

from typing import Final

from src.core.i18n_cards import CardLabel, card_label
from src.core.mail_reply_state import DURABLE_STATUSES, ReplyStatus, read_reply_state
from src.domains.agents.display.components.card_chips import render_chip
from src.domains.agents.display.icons import Icons

#: The label of each status that stays true once observed.
_DURABLE_LABELS: Final[dict[ReplyStatus, CardLabel]] = {
    "answered": "email_answered",
    "reply_received": "email_reply_received",
}


def reply_state_chips(value: object, language: str) -> list[str]:
    """The chip of a durable reply state, in words; nothing for any other value.

    Args:
        value: The stored annotation (its JSON form or the model).
        language: The reader's language.

    Returns:
        One chip for « answered » or « reply received », else an empty list.
    """
    state = read_reply_state(value)
    if state is None or state.status not in DURABLE_STATUSES:
        return []
    return [render_chip(card_label(_DURABLE_LABELS[state.status], language), "green", Icons.REPLY)]


def is_answered(value: object) -> bool:
    """Whether the mailbox said the person answered this message."""
    state = read_reply_state(value)
    return state is not None and state.status == "answered"


def conversation_size(value: object) -> int | None:
    """How many messages the conversation held when the mailbox was read, when it told."""
    state = read_reply_state(value)
    return state.conversation_size if state is not None else None


__all__ = ["conversation_size", "is_answered", "reply_state_chips"]
