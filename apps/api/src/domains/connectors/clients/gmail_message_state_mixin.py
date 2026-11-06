"""Where a Gmail message is, whether it was read and starred (ADR-369).

Trash, restore, moves, the star and the read state: the acts that change a
message's STATE without composing anything. Out of ``google_gmail_client.py``,
which is frozen at its audited size, and together because each of them must
make the client's caches forget the message (the cache generation, Task 2.2).

Each of them but the trash is a change of labels, moved for a whole selection in
one ``batchModify``. Gmail refuses the WHOLE batch when one id is unknown, so a
refused batch is retried message by message to say which one left the mailbox —
the rest of the selection is still changed (owner decision D2: the same contract
on the three providers).

A place is a label here (``mail_moves``): archiving takes ``INBOX`` off, a folder of
the person's own is a label put on, and the id never changes. Leaving the trash goes
through ``untrash``, whose effect on ``INBOX`` Google does not document: the message
is then placed by the same change of labels, whatever ``untrash`` left. Nothing here
deletes for good: ``messages.delete`` needs ``https://mail.google.com/``, a scope LIA
does not hold, and Gmail empties its trash itself after 30 days.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.mail_folders import MailFolder, find_mail_folder
from src.domains.connectors.clients.mail_moves import (
    MOVE_CONCURRENCY,
    MailPlace,
    UnreadCounts,
    moved_result,
    settle_each,
)
from src.domains.connectors.clients.mail_read_state import (
    GMAIL_UNREAD_LABEL,
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    read_state_result,
    unique_ids,
)
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: What a Gmail message id is made of; anything else never reaches a URL path.
_MESSAGE_ID: Final = re.compile(r"[A-Za-z0-9_-]+")
#: What Gmail answers for a batch naming an id it does not know.
_BATCH_REFUSALS: Final = frozenset({400, 404})
#: A message that is not there any more.
_GONE: Final = frozenset({404, 410})
#: The system labels a place is made of, and the one a star is.
_INBOX: Final = "INBOX"
_SPAM: Final = "SPAM"
_STARRED: Final = "STARRED"


class _GmailStateHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
        *,
        content: bytes | None = None,
        base_url: str | None = None,
        idempotent: bool | None = None,
    ) -> dict[str, Any]: ...

    async def batch_modify_labels(
        self,
        message_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool: ...

    async def modify_message_labels(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    async def _mark_each(
        self, message_ids: list[str], add: list[str] | None, remove: list[str] | None
    ) -> dict[str, Any]: ...

    async def _relabel(
        self, message_ids: Sequence[str], add: list[str] | None, remove: list[str] | None
    ) -> dict[str, Any]: ...

    async def trash_email(self, message_id: str) -> dict[str, Any]: ...

    async def untrash_email(self, message_id: str) -> dict[str, Any]: ...

    async def list_labels_full(self, use_cache: bool = True) -> list[dict[str, Any]]: ...

    def is_system_label(self, label_name: str) -> bool: ...


class GmailMessageStateMixin:
    """Trash, restore, moves, star and read state of Gmail messages."""

    async def trash_email(self: _GmailStateHost, message_id: str) -> dict[str, Any]:
        """Move an email to the trash, where it stays recoverable for 30 days.

        Args:
            message_id: Message ID to move to the trash.

        Returns:
            The trashed message's details (id, threadId, labelIds).
        """
        # Trashing a trashed message changes nothing: a lost answer may be resent (S1).
        response = await self._make_request(
            "POST", f"/users/me/messages/{_path_id(message_id)}/trash", idempotent=True
        )
        logger.info("gmail_email_trashed", user_id=str(self.user_id), message_id=message_id)
        return response

    async def untrash_email(self: _GmailStateHost, message_id: str) -> dict[str, Any]:
        """Restore an email from the trash to where it was.

        Args:
            message_id: Message ID to restore.

        Returns:
            The restored message's details (id, threadId, labelIds).
        """
        response = await self._make_request(
            "POST", f"/users/me/messages/{_path_id(message_id)}/untrash", idempotent=True
        )
        logger.info("gmail_email_untrashed", user_id=str(self.user_id), message_id=message_id)
        return response

    async def move_emails(
        self: _GmailStateHost,
        message_ids: Sequence[str],
        place: MailPlace,
        origin: MailPlace | None = None,
    ) -> dict[str, Any]:
        """Send messages to a place; their ids stay.

        Args:
            message_ids: The messages (each counted once).
            place: Where they go.
            origin: Where they are, when the caller knows: leaving the trash or a
                label of the person's own is part of the move.

        Returns:
            ``mail_moves.moved_result``.
        """
        ids = unique_ids(message_ids)
        add, remove = _label_change(place, origin)
        if any(self.is_system_label(label) for label in (place.folder, _left(origin)) if label):
            raise ValueError("a place of the person's own is a label of theirs")

        async def trashed(message_id: str) -> str:
            await self.trash_email(message_id)
            return message_id

        async def restored(message_id: str) -> str:
            await self.untrash_email(message_id)
            await self.modify_message_labels(message_id, add_label_ids=add, remove_label_ids=remove)
            return message_id

        if place.role == "trash":
            result = moved_result(*await settle_each(ids, trashed))
        elif origin is not None and origin.role == "trash":
            result = moved_result(*await settle_each(ids, restored))
        else:
            changed = await self._relabel(ids, add, remove)
            result = {
                **changed,
                "moved": {message_id: message_id for message_id in changed["updated"]},
            }
        logger.info(
            "gmail_messages_moved",
            user_id=str(self.user_id),
            moved=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result

    async def place_named(self: _GmailStateHost, name: str) -> MailPlace:
        """The label of the person's own a name answers to.

        Args:
            name: Its name or path, whatever its case.

        Returns:
            The place, by the label's id.

        Raises:
            MailFolderLookupError: No label, or several, answer to it.
        """
        labels = await self.list_labels_full()
        own = [
            MailFolder(str(label["id"]), str(label["name"]), str(label["name"]).rpartition("/")[2])
            for label in labels
            if label.get("type") == "user"
        ]
        return MailPlace(folder=find_mail_folder(own, name).folder_id)

    async def set_starred(
        self: _GmailStateHost, message_ids: Sequence[str], starred: bool
    ) -> dict[str, Any]:
        """Star messages or take their star off, and say which could not be.

        Args:
            message_ids: The messages (each counted once).
            starred: True to star them.

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}`` (``mail_read_state``).
        """
        add, remove = ([_STARRED], None) if starred else (None, [_STARRED])
        return await self._relabel(message_ids, add, remove)

    async def unread_counts(self: _GmailStateHost, folders_max: int) -> UnreadCounts:
        """What the inbox, the spam and the person's labels leave unread.

        ``labels.list`` carries no figure: each label is read on its own, a few at a
        time, and a label removed meanwhile simply has none.

        Args:
            folders_max: The labels of the person's own read at most.

        Returns:
            The figures, ``complete`` False when labels were left out.
        """
        labels = await self.list_labels_full(use_cache=False)
        own = [str(label["id"]) for label in labels if label.get("type") == "user"]
        read = own[:folders_max]
        gate = asyncio.Semaphore(MOVE_CONCURRENCY)

        async def figure(label_id: str) -> int | None:
            async with gate:
                try:
                    label = await self._make_request(
                        "GET", f"/users/me/labels/{_path_id(label_id)}"
                    )
                except ConnectorAPIError as refused:
                    if refused.upstream_status_code in _GONE:
                        return None
                    raise
            return int(label.get("messagesUnread") or 0)

        figures = await asyncio.gather(*(figure(name) for name in (_INBOX, _SPAM, *read)))
        inbox, spam, *folders = figures
        roles = {"inbox": inbox, "spam": spam}
        return UnreadCounts(
            roles={role: count for role, count in roles.items() if count is not None},
            folders={
                label: count
                for label, count in zip(read, folders, strict=True)
                if count is not None
            },
            complete=len(read) == len(own),
        )

    async def mark_read(
        self: _GmailStateHost, message_ids: Sequence[str], read: bool
    ) -> dict[str, Any]:
        """Mark messages read or unread, and say which could not be.

        Args:
            message_ids: The messages (each counted once).
            read: True to mark them read, False unread.

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}``
            (``mail_read_state``).
        """
        add, remove = (None, [GMAIL_UNREAD_LABEL]) if read else ([GMAIL_UNREAD_LABEL], None)
        result = await self._relabel(message_ids, add, remove)
        logger.info(
            "gmail_read_state_changed",
            user_id=str(self.user_id),
            read=read,
            updated=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result

    async def _relabel(
        self: _GmailStateHost,
        message_ids: Sequence[str],
        add: list[str] | None,
        remove: list[str] | None,
    ) -> dict[str, Any]:
        """One change of labels on a selection, each id answered."""
        ids = unique_ids(message_ids)
        malformed = [message_id for message_id in ids if not _MESSAGE_ID.fullmatch(message_id)]
        wanted = [message_id for message_id in ids if message_id not in malformed]
        result = read_state_result(wanted, [])
        if wanted:
            try:
                await self.batch_modify_labels(wanted, add_label_ids=add, remove_label_ids=remove)
            except ConnectorAPIError as refused:
                if refused.upstream_status_code not in _BATCH_REFUSALS:
                    raise
                result = await self._mark_each(wanted, add, remove)
        result["failed"] += [{"id": bad, "status": READ_STATE_NOT_FOUND} for bad in malformed]
        return result

    async def _mark_each(
        self: _GmailStateHost,
        message_ids: list[str],
        add: list[str] | None,
        remove: list[str] | None,
    ) -> dict[str, Any]:
        """The batch was refused: one message at a time, to name the one gone."""
        updated: list[str] = []
        failed: list[tuple[str, str]] = []
        for message_id in message_ids:
            try:
                await self.modify_message_labels(
                    message_id, add_label_ids=add, remove_label_ids=remove
                )
            except ConnectorAPIError as refused:
                gone = refused.upstream_status_code in _GONE | _BATCH_REFUSALS
                failed.append((message_id, READ_STATE_NOT_FOUND if gone else READ_STATE_FAILED))
                continue
            updated.append(message_id)
        return read_state_result(updated, failed)


def _label_change(place: MailPlace, origin: MailPlace | None) -> tuple[list[str], list[str]]:
    """The labels a move adds and removes: a place is a label here.

    Args:
        place: Where the messages go (the trash has its own act).
        origin: Where they are, when the caller knows.

    Returns:
        The labels to add, then the labels to remove.
    """
    if place.role == "inbox":
        add, remove = [_INBOX], [_SPAM]
    elif place.role == "spam":
        add, remove = [_SPAM], [_INBOX]
    elif place.folder is not None:
        add, remove = [place.folder], [_INBOX, _SPAM]
    else:
        add, remove = [], [_INBOX, _SPAM]
    left = _left(origin)
    if left is not None and left != place.folder:
        remove.append(left)
    return add, remove


def _left(origin: MailPlace | None) -> str | None:
    """The label of the person's own a move leaves, when it leaves one."""
    return origin.folder if origin is not None else None


def _path_id(message_id: str) -> str:
    """A message id fit for a URL path — anything else names no message, and asks nothing.

    The id comes from a browser or a model: interpolated raw, ``x/../drafts/y``
    would send the person's token to another endpoint of their mailbox.

    Raises:
        ConnectorAPIError: 404, the id names no message (never quoted back).
    """
    if not _MESSAGE_ID.fullmatch(message_id):
        raise ConnectorAPIError(
            connector_type=ConnectorType.GOOGLE_GMAIL.value,
            status_code=404,
            detail="google_gmail API error: no such message",
        )
    return message_id


__all__ = ["GmailMessageStateMixin"]
