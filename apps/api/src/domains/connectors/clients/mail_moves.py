"""Where a message goes, on every mail provider (ADR-369, lot 4).

A place is named by its ROLE, which each provider says in its own words, or is a
folder of the person's own: a Gmail label's id, a Graph path, an IMAP name. Three
shapes of one gesture: Gmail moves labels and the id stays; Graph moves the item and
answers its new id; IMAP moves the message to a folder where it has another UID.

The answer is ``mark_read``'s, with what each id became: each message moved, or
reported with why, never the whole selection lost to one that left the mailbox
meanwhile. What became of an id is None when the provider does not say: the message
moved, and only the way back is lost.

A failure of the mailbox itself (an authorisation, a throttle) is the act's own when
nothing was done yet, and is raised; after one message moved it leaves the rest
unanswered, because a refusal would hide what already moved.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

import structlog

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    READ_STATE_UNANSWERED,
    read_state_result,
)

logger = structlog.get_logger(__name__)

MailPlaceRole = Literal["inbox", "archive", "spam", "trash"]

#: Messages acted on at once where a provider has no batch: a mailbox answers a burst
#: with 429.
MOVE_CONCURRENCY: Final = 4
#: A provider's « this message is not here ».
_GONE: Final = frozenset({404, 410})


@dataclass(frozen=True, slots=True)
class MailPlace:
    """Where a message is or goes: a role, or a folder of the person's own.

    Attributes:
        role: What every provider has, whatever it calls it.
        folder: The folder as the pane names it (a Gmail label's id, a Graph path,
            an IMAP name).

    Raises:
        ValueError: Neither, or both.
    """

    role: MailPlaceRole | None = None
    folder: str | None = None

    def __post_init__(self) -> None:
        if (self.role is None) == (self.folder is None):
            raise ValueError("a mail place is a role or a folder, never both or neither")


@dataclass(frozen=True, slots=True)
class UnreadCounts:
    """What a mailbox leaves unread.

    Attributes:
        roles: Each role with a figure worth drawing (``inbox``, ``spam``).
        folders: Each folder read, as the pane names it.
        complete: False when a folder was left out, by the bound or by a refusal.
    """

    roles: dict[str, int]
    folders: dict[str, int]
    complete: bool


class MessageElsewhereError(Exception):
    """The message is not where the act allows it: refused alone, the rest still acted on."""


Moved = dict[str, str | None]
Failed = list[tuple[str, str]]


def moved_result(
    moved: Mapping[str, str | None], failed: Sequence[tuple[str, str]]
) -> dict[str, Any]:
    """The one answer: ``mark_read``'s, and ``{"moved": {old id: its id now, or None}}``."""
    return {**read_state_result(list(moved), failed), "moved": dict(moved)}


def in_selection_order(
    ids: Iterable[str], moved: Mapping[str, str | None], statuses: Mapping[str, str]
) -> tuple[Moved, Failed]:
    """What became of each id, in the selection's order whatever order they settled in."""
    ordered = list(ids)
    return (
        {message_id: moved[message_id] for message_id in ordered if message_id in moved},
        [(message_id, statuses[message_id]) for message_id in ordered if message_id in statuses],
    )


async def settle_each(
    ids: Sequence[str], act: Callable[[str], Awaitable[str | None]]
) -> tuple[Moved, Failed]:
    """Each message of a selection acted on, a few at a time, each one answered.

    Args:
        ids: The selection, each id once.
        act: What is done to one message; answers its id afterwards, when known.

    Returns:
        The messages done, with their id afterwards, and the others with why.

    Raises:
        Exception: The mailbox's own failure, when nothing was done.
    """
    gate = asyncio.Semaphore(MOVE_CONCURRENCY)
    done: Moved = {}
    statuses: dict[str, str] = {}
    stopped: list[Exception] = []

    async def one(message_id: str) -> None:
        async with gate:
            if stopped:
                statuses[message_id] = READ_STATE_UNANSWERED
                return
            try:
                done[message_id] = await act(message_id)
            except ConnectorAPIError as refused:
                gone = refused.upstream_status_code in _GONE
                statuses[message_id] = READ_STATE_NOT_FOUND if gone else READ_STATE_FAILED
            except MessageElsewhereError:
                statuses[message_id] = READ_STATE_FAILED
            except Exception as failure:
                stopped.append(failure)
                statuses[message_id] = READ_STATE_UNANSWERED

    await asyncio.gather(*(one(message_id) for message_id in ids))
    if stopped and not done:
        raise stopped[0]
    if stopped:
        logger.warning(
            "mail_act_interrupted",
            done=len(done),
            unanswered=len(ids) - len(done),
            error_type=type(stopped[0]).__name__,
        )
    return in_selection_order(ids, done, statuses)


__all__ = [
    "MOVE_CONCURRENCY",
    "Failed",
    "MailPlace",
    "MailPlaceRole",
    "MessageElsewhereError",
    "Moved",
    "UnreadCounts",
    "in_selection_order",
    "moved_result",
    "settle_each",
]
