"""Acts on a selection of messages, by the person's own hand (ADR-369).

Each act rides one contract of the three clients (D2), on a selection within the
published bulk bound: the read state, the star, a move. These are state SETS: done
twice they leave the message as once, so a lost answer is « try again », never
« outcome unknown ». Deleting for good is not, and is an act of its own, offered
where the provider's scopes allow it.

None is all-or-nothing: each message is done or said with why — gone since it was
listed, refused alone, or never answered because the mailbox stopped mid-way. A
mailbox failure before ANY message was done is the act's own (reconnect, wait,
unavailable) and leaves as a refusal; after one, the rest are « unavailable »,
because a refusal would hide the messages already moved.

A place travels as the pane names it. Only a role every provider has, or a folder of
the person's own, is one a message goes to; a view (the starred, the sent, all mail)
is where it is LISTED, which says nothing of where it is.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Final, cast, get_args
from uuid import UUID

import structlog

from src.core.constants import WORKBENCH_MAIL_EMPTY_TRASH_MAX
from src.domains.connectors.clients.mail_moves import MailPlace, MailPlaceRole
from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
)
from src.domains.connectors.clients.protocols import EmailClientProtocol, MailTrashClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import INVALID_REQUEST, NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.schemas.acts import ActFailure, ActOutcome, ActStatus
from src.domains.workbench.schemas.mail import (
    SYSTEM_FOLDER_PREFIX,
    MessageSelection,
    MovedMessage,
    MoveOutcome,
    MoveRequest,
    ReadStateChange,
    StarChange,
    TrashEmptied,
)
from src.domains.workbench.selection_acts import UNAVAILABLE

logger = structlog.get_logger(__name__)

_TOOL = WorkbenchTool.MAIL
#: The roles a message can be sent to, whatever the provider calls them.
_PLACE_ROLES: Final[frozenset[str]] = frozenset(get_args(MailPlaceRole))


async def set_read_state(user_id: UUID, change: ReadStateChange) -> ActOutcome:
    """Mark a selection read or unread; each message answered."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_state", act=False):
            raw = await client.mark_read(change.message_ids, change.read)
    return _answered(raw)


async def set_star(user_id: UUID, change: StarChange) -> ActOutcome:
    """Star a selection or take its star off; each message answered."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "star", act=False):
            raw = await client.set_starred(change.message_ids, change.starred)
    return _answered(raw)


async def move_messages(user_id: UUID, request: MoveRequest) -> MoveOutcome:
    """Send a selection to a place; each message answered, with its id from now on."""
    place = _place_of(request.to)
    origin = _origin_of(request.origin)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "move", act=False):
            raw = await client.move_emails(request.message_ids, place, origin)
    answered = _answered(raw)
    return MoveOutcome(
        done=answered.done,
        failed=answered.failed,
        moved=[
            MovedMessage(id=str(old), new_id=str(new) if new else None)
            for old, new in (raw.get("moved") or {}).items()
        ],
    )


async def delete_forever(user_id: UUID, selection: MessageSelection) -> ActOutcome:
    """Delete messages of the trash for good; each message answered."""
    async with _trash_client(user_id) as client:
        async with provider_call(_TOOL, "delete_forever", act=True):
            raw = await client.delete_emails_forever(selection.message_ids)
    return _answered(raw)


async def empty_trash(user_id: UUID) -> TrashEmptied:
    """Delete for good what the trash holds, within the bound; what remains is said."""
    async with _trash_client(user_id) as client:
        async with provider_call(_TOOL, "empty_trash", act=True):
            raw = await client.empty_trash(WORKBENCH_MAIL_EMPTY_TRASH_MAX)
    return TrashEmptied(deleted=int(raw["deleted"]), remaining=bool(raw["remaining"]))


@asynccontextmanager
async def _trash_client(user_id: UUID) -> AsyncIterator[MailTrashClientProtocol]:
    """The account's mail client, refused unsent when its provider cannot delete for good."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if WorkbenchFeature.PERMANENT_DELETE not in PROVIDER_FEATURES[opened.connector_type]:
            refuse(NOT_SUPPORTED_BY_PROVIDER)
        client: MailTrashClientProtocol = opened.client
        yield client


def _place_of(folder: str) -> MailPlace:
    """Where a message is sent; a view of the pane is no place to send one."""
    role = folder.removeprefix(SYSTEM_FOLDER_PREFIX)
    if role == folder:
        return MailPlace(folder=folder)
    if role not in _PLACE_ROLES:
        refuse(INVALID_REQUEST)
    return MailPlace(role=cast(MailPlaceRole, role))


def _origin_of(folder: str | None) -> MailPlace | None:
    """Where a selection is listed, when that says where it is."""
    if folder is None:
        return None
    role = folder.removeprefix(SYSTEM_FOLDER_PREFIX)
    if role == folder:
        return MailPlace(folder=folder)
    return MailPlace(role=cast(MailPlaceRole, role)) if role in _PLACE_ROLES else None


def _answered(raw: Mapping[str, Any]) -> ActOutcome:
    """The clients' one answer, as the act's vocabulary says it."""
    return ActOutcome(
        done=list(raw.get("updated") or []),
        failed=[
            ActFailure(id=str(item["id"]), status=_read_state_status(item.get("status")))
            for item in raw.get("failed") or []
        ],
    )


def _read_state_status(status: object) -> ActStatus:
    """``mail_read_state``'s two statuses, as the act's vocabulary says them."""
    if status == READ_STATE_NOT_FOUND:
        return "not_found"
    if status == READ_STATE_FAILED:
        return "failed"
    return UNAVAILABLE
