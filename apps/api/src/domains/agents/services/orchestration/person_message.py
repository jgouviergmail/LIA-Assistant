"""The person's message as it enters a turn's state (lot 17).

It carries the instant it was written (``message_view.WRITTEN_AT_KEY``), so every
later turn reads it with that instant instead of as if it had just been said —
measured on three families, the difference between « the dentist tomorrow » being
ahead or long past. Every place a turn adds the person's words goes through here:
the turn's message, the answer to a question, the reformulation of an edit.
"""

from datetime import UTC, datetime

from langchain_core.messages import HumanMessage

from src.infrastructure.llm.message_view import stamped_now


def person_message(text: str) -> HumanMessage:
    """The person's words, stamped with the instant they reach the turn.

    Args:
        text: What the person said (or the reformulation standing for it).

    Returns:
        A ``HumanMessage`` carrying its write instant.
    """
    return stamped_now(HumanMessage(content=text), datetime.now(UTC))
