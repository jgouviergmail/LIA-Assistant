"""What a read-state change reports, on every mail provider (ADR-369, owner decision D2).

``mark_read`` exists on the three mail clients with one contract: each id of a
selection is updated, or reported with why it was not — never the whole
selection lost to one message that left the mailbox in the meantime.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final

#: The message is not in the mailbox any more (or the id cannot be one).
READ_STATE_NOT_FOUND: Final = "not_found"
#: The provider refused or failed for this message alone.
READ_STATE_FAILED: Final = "failed"
READ_STATE_FAILURE_STATUSES: Final = frozenset({READ_STATE_NOT_FOUND, READ_STATE_FAILED})

#: The system label Gmail marks an unread message with.
GMAIL_UNREAD_LABEL: Final = "UNREAD"


def unique_ids(message_ids: Iterable[str]) -> list[str]:
    """The selection in order, each id once, empty ids dropped."""
    return list(dict.fromkeys(message_id for message_id in message_ids if message_id))


def read_state_result(updated: Sequence[str], failed: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """The one answer shape: ``{"updated": [ids], "failed": [{"id", "status"}]}``."""
    return {
        "updated": list(updated),
        "failed": [{"id": message_id, "status": status} for message_id, status in failed],
    }


__all__ = [
    "GMAIL_UNREAD_LABEL",
    "READ_STATE_FAILED",
    "READ_STATE_FAILURE_STATUSES",
    "READ_STATE_NOT_FOUND",
    "read_state_result",
    "unique_ids",
]
