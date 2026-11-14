"""What the e-mail vocabulary says of a message, read ONE way (ADR-287).

Every provider's normaliser speaks the same words (``EmailMessage``): system labels
(Gmail natively, Graph and IMAP from their own flags and folders) and an instant in
epoch milliseconds. Pure — no I/O, importable by any layer — so the readers of a
message's state share one reading instead of re-typing a label or a conversion.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

#: What the mailbox marks a message it holds unopened with.
UNREAD_LABEL: Final = "UNREAD"
#: What marks a message the mailbox's owner sent.
SENT_LABEL: Final = "SENT"
#: What marks the owner's unsent words.
DRAFT_LABEL: Final = "DRAFT"


def labels_of(message: Mapping[str, object]) -> tuple[str, ...]:
    """The labels a message carries; none when it carries no readable list.

    Args:
        message: A message in the ``EmailMessage`` vocabulary.

    Returns:
        Its labels, in the order it carries them.
    """
    labels = message.get("labelIds")
    if not isinstance(labels, list | tuple):
        return ()
    return tuple(label for label in labels if isinstance(label, str))


def is_unread(message: Mapping[str, object]) -> bool:
    """Whether the mailbox still marks ``message`` unread.

    A message carrying no labels is NOT unread: nothing vouches for its state,
    and a reader about to announce it must not assume it was never opened.

    Args:
        message: A message in the ``EmailMessage`` vocabulary.

    Returns:
        True when its labels hold the unread mark.
    """
    return UNREAD_LABEL in labels_of(message)


def instant_of(value: object) -> datetime | None:
    """Epoch milliseconds, as the normalisers carry them, as an aware UTC instant.

    Args:
        value: An ``internalDate``-shaped value: an integer or its decimal string.

    Returns:
        The instant; None when the value is absent, zero or absurd — never a date
        nobody stated.
    """
    try:
        millis = int(str(value))
        return datetime.fromtimestamp(millis / 1000, UTC) if millis > 0 else None
    except ValueError, OverflowError, OSError:
        return None


__all__ = [
    "DRAFT_LABEL",
    "SENT_LABEL",
    "UNREAD_LABEL",
    "instant_of",
    "is_unread",
    "labels_of",
]
