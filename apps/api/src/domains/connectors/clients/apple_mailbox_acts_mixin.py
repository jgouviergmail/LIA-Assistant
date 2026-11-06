"""Sorting an iCloud mailbox over IMAP, and managing its folders (ADR-369, lot 4).

Out of ``apple_email_client.py``, which is close to its size cap. One session serves
a whole selection, each folder selected once: a login per message would be the first
thing a mail server throttles. A UID names a message within ONE folder, so a message
moved to another has another id. It is found there by its ``Message-ID``, read before
the move: one hit makes its id, anything else leaves it unknown, and the message has
still moved. That header is the sender's: nothing but a plain ``<…>`` is ever searched.

A session that fails after a folder moved leaves the rest unanswered instead of
raising, because a refusal would hide the messages already moved; and nothing is
replayed, since a failure after COPY may have stored a copy.

« For good » is ``\\Deleted`` and a targeted EXPUNGE, on messages of the trash alone,
whatever id a caller hands in: its folder is read first, because a wrong id here
cannot be undone.

A folder holding anything is never deleted: IMAP's DELETE destroys its messages, and
RFC 3501 leaves the folders below it in place under a name nothing draws. A folder of
the mailbox's own is never touched, found by its flag or its name.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from uuid import UUID

import structlog
from imap_tools import AND, Header, MailBox
from imap_tools.errors import UnexpectedCommandStatusError

from src.domains.connectors.clients.apple_imap import (
    ARCHIVE_ROLE,
    DRAFTS_ROLE,
    JUNK_ROLE,
    ROLE_FOLDER_NAMES,
    SENT_ROLE,
    TRASH_ROLE,
    authenticated_imap_mailbox,
    mailbox_scope,
    move_messages,
    remove_messages,
    search_folder,
    select_message_folder,
    special_folder,
)
from src.domains.connectors.clients.apple_mail_state_mixin import (
    Group,
    by_folder,
    forget_cached,
)
from src.domains.connectors.clients.mail_folders import (
    MailFolderNameTakenError,
    MailFolderNotEmptyError,
    SystemFolderError,
)
from src.domains.connectors.clients.mail_moves import (
    MailPlace,
    MailPlaceRole,
    Moved,
    UnreadCounts,
    in_selection_order,
    moved_result,
)
from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    READ_STATE_UNANSWERED,
    read_state_result,
    unique_ids,
)
from src.domains.connectors.clients.mailbox_drafts import MailboxFolderUnavailableError
from src.domains.connectors.clients.normalizers.imap_handles import INBOX, message_handle
from src.domains.connectors.schemas import AppleCredentials

logger = structlog.get_logger(__name__)

#: Each role but the inbox, found by what the server flags it with.
_ROLE_FOLDERS: Final[dict[MailPlaceRole, str]] = {
    "archive": ARCHIVE_ROLE,
    "spam": JUNK_ROLE,
    "trash": TRASH_ROLE,
}
#: A ``Message-ID`` fit for a quoted search: no space, no quote, no backslash.
_PLAIN_MESSAGE_ID: Final = re.compile(r"<[!#-\[\]-~]+>")
_NOT_SELECTABLE: Final = "\\noselect"
#: The roles a server flags its own folders with.
_SYSTEM_FLAGS: Final = frozenset(
    flag.casefold() for flag in (ARCHIVE_ROLE, DRAFTS_ROLE, JUNK_ROLE, SENT_ROLE, TRASH_ROLE)
)


@dataclass
class _Settled:
    """What became of a selection, folder by folder."""

    done: Moved = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)

    def mark(self, ids: Sequence[str], status: str) -> None:
        self.statuses.update(dict.fromkeys(ids, status))


class _AppleActsHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID
    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _in_session(self, act: Callable[[MailBox], Any]) -> Any: ...

    async def _move_emails_impl(self, ids: list[str], place: MailPlace) -> dict[str, Any]: ...

    async def _delete_forever_impl(self, ids: list[str]) -> dict[str, Any]: ...

    async def _empty_trash_impl(self, limit: int) -> dict[str, Any]: ...

    async def _unread_counts_impl(self, folders_max: int) -> UnreadCounts: ...


class AppleMailboxActsMixin:
    """Moves, deletion for good and unread figures of an iCloud mailbox."""

    async def move_emails(
        self: _AppleActsHost,
        message_ids: Sequence[str],
        place: MailPlace,
        origin: MailPlace | None = None,
    ) -> dict[str, Any]:
        """Send messages to a place; each one answers with its new id, when found.

        Args:
            message_ids: The messages (each counted once).
            place: Where they go.
            origin: Unused: an id names its own folder.

        Returns:
            ``mail_moves.moved_result``.
        """
        return await self._execute_with_retry(
            "move_emails", self._move_emails_impl, unique_ids(message_ids), place, max_retries=0
        )

    async def place_named(self: _AppleActsHost, name: str) -> MailPlace:
        """A folder is found by its name when a move reads it."""
        return MailPlace(folder=name)

    async def delete_emails_forever(
        self: _AppleActsHost, message_ids: Sequence[str]
    ) -> dict[str, Any]:
        """Delete messages of the trash for good; any other is refused alone.

        Args:
            message_ids: The messages (each counted once).

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}`` (``mail_read_state``).
        """
        return await self._execute_with_retry(
            "delete_emails_forever",
            self._delete_forever_impl,
            unique_ids(message_ids),
            max_retries=0,
        )

    async def empty_trash(self: _AppleActsHost, limit: int) -> dict[str, Any]:
        """Delete for good what the trash holds, within a bound.

        Args:
            limit: The messages deleted by one call at most.

        Returns:
            ``{"deleted": n, "remaining": bool}``.
        """
        return await self._execute_with_retry(
            "empty_trash", self._empty_trash_impl, limit, max_retries=0
        )

    async def unread_counts(self: _AppleActsHost, folders_max: int) -> UnreadCounts:
        """What the inbox, the spam and the person's folders leave unread, in one session.

        Args:
            folders_max: The folders of the person's own read at most.

        Returns:
            The figures, ``complete`` False when a folder was left out.
        """
        return await self._execute_with_retry(
            "unread_counts", self._unread_counts_impl, folders_max
        )

    async def create_folder(self: _AppleActsHost, name: str) -> str:
        """Create a folder of the person's own; « / » nests it, as a label's name does.

        Args:
            name: Its path.

        Returns:
            The name the pane finds it by.
        """

        def create(mailbox: MailBox) -> str:
            target = name.replace("/", _delimiter(mailbox))
            _refuse_taken(mailbox, target)
            mailbox.folder.create(target)
            return target

        created: str = await self._in_session(create)
        return created

    async def rename_folder(self: _AppleActsHost, folder: str, name: str) -> str:
        """Rename a folder of the person's own, in place.

        Args:
            folder: Its name.
            name: Its new own name, never a path.

        Returns:
            The name the pane finds it by from now on.
        """

        def rename(mailbox: MailBox) -> str:
            current = _own_folder(mailbox, folder)
            delimiter = _delimiter(mailbox)
            parent, separator, _ = current.rpartition(delimiter)
            target = f"{parent}{separator}{name}"
            _refuse_taken(mailbox, target)
            mailbox.folder.rename(current, target)
            return target

        renamed: str = await self._in_session(rename)
        return renamed

    async def delete_folder(self: _AppleActsHost, folder: str) -> None:
        """Delete a folder of the person's own that holds nothing.

        Args:
            folder: Its name.

        Raises:
            MailFolderNotEmptyError: It holds messages or folders.
        """

        def delete(mailbox: MailBox) -> None:
            current = _own_folder(mailbox, folder)
            below = f"{current}{_delimiter(mailbox)}"
            mailbox.folder.set(current)
            held = mailbox.uids("ALL")
            if held or any(info.name.startswith(below) for info in mailbox.folder.list()):
                raise MailFolderNotEmptyError
            # A server may refuse to delete the folder a session has selected.
            mailbox.folder.set(INBOX)
            mailbox.folder.delete(current)

        await self._in_session(delete)

    async def _in_session(self: _AppleActsHost, act: Callable[[MailBox], Any]) -> Any:
        """``act`` on one authenticated session, off the event loop."""

        def run() -> Any:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    return act(mailbox)
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(run)

    async def _move_emails_impl(
        self: _AppleActsHost, ids: list[str], place: MailPlace
    ) -> dict[str, Any]:
        groups, unreadable = by_folder(ids)
        principal = self.credentials.apple_id

        def move_each_folder(mailbox: MailBox) -> _Settled:
            destination = _destination(mailbox, place)
            return _settle_folders(
                groups.values(),
                lambda members, settled: _move_one_folder(
                    mailbox, members, destination, principal, settled
                ),
            )

        settled = await self._in_session(move_each_folder)
        settled.mark(unreadable, READ_STATE_NOT_FOUND)
        await forget_cached(self, list(settled.done))
        result = moved_result(*in_selection_order(ids, settled.done, settled.statuses))
        logger.info(
            "apple_messages_moved",
            user_id=str(self.user_id),
            moved=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result

    async def _delete_forever_impl(self: _AppleActsHost, ids: list[str]) -> dict[str, Any]:
        groups, unreadable = by_folder(ids)
        principal = self.credentials.apple_id

        def delete_in_the_trash(mailbox: MailBox) -> _Settled:
            trash = special_folder(mailbox, TRASH_ROLE)
            return _settle_folders(
                groups.values(),
                lambda members, settled: _delete_one_folder(
                    mailbox, members, trash, principal, settled
                ),
            )

        settled = await self._in_session(delete_in_the_trash)
        settled.mark(unreadable, READ_STATE_NOT_FOUND)
        await forget_cached(self, list(settled.done))
        done, failed = in_selection_order(ids, settled.done, settled.statuses)
        logger.info(
            "apple_messages_deleted_for_good",
            user_id=str(self.user_id),
            deleted=len(done),
            failed=len(failed),
        )
        return read_state_result(list(done), failed)

    async def _empty_trash_impl(self: _AppleActsHost, limit: int) -> dict[str, Any]:
        def empty(mailbox: MailBox) -> dict[str, Any]:
            mailbox.folder.set(special_folder(mailbox, TRASH_ROLE))
            held = mailbox.uids("ALL")
            kept_for_later = held[limit:]
            remove_messages(mailbox, held[:limit])
            return {"deleted": len(held) - len(kept_for_later), "remaining": bool(kept_for_later)}

        result: dict[str, Any] = await self._in_session(empty)
        logger.info("apple_trash_emptied", user_id=str(self.user_id), deleted=result["deleted"])
        return result

    async def _unread_counts_impl(self: _AppleActsHost, folders_max: int) -> UnreadCounts:
        def count(mailbox: MailBox) -> UnreadCounts:
            listed = [
                info
                for info in mailbox.folder.list()
                if _NOT_SELECTABLE not in {flag.casefold() for flag in info.flags}
            ]
            own = [info.name for info in listed if info.name not in ROLE_FOLDER_NAMES]
            read = own[:folders_max]
            roles = {"inbox": _unseen(mailbox, INBOX), "spam": _junk_unseen(mailbox)}
            folders = {name: _unseen(mailbox, name) for name in read}
            return UnreadCounts(
                roles={role: unseen for role, unseen in roles.items() if unseen is not None},
                folders={name: unseen for name, unseen in folders.items() if unseen is not None},
                complete=len(read) == len(own) and None not in folders.values(),
            )

        counted: UnreadCounts = await self._in_session(count)
        return counted


def _delimiter(mailbox: MailBox) -> str:
    """The server's own separator of a folder's path."""
    return next((info.delim for info in mailbox.folder.list() if info.delim), "/")


def _refuse_taken(mailbox: MailBox, name: str) -> None:
    """A name the mailbox already holds, whatever its case, is said (iCloud folds it)."""
    wanted = name.casefold()
    if any(info.name.casefold() == wanted for info in mailbox.folder.list()):
        raise MailFolderNameTakenError


def _own_folder(mailbox: MailBox, folder: str) -> str:
    """The name of a folder of the person's own.

    Raises:
        SystemFolderError: It is one of the mailbox's own.
    """
    found = search_folder(mailbox, folder)
    flags = next((info.flags for info in mailbox.folder.list() if info.name == found), ())
    if found in ROLE_FOLDER_NAMES or _SYSTEM_FLAGS & {flag.casefold() for flag in flags}:
        raise SystemFolderError
    return found


def _destination(mailbox: MailBox, place: MailPlace) -> str:
    """The folder a place is on this server."""
    if place.folder is not None:
        return search_folder(mailbox, place.folder)
    if place.role == "inbox" or place.role is None:
        return INBOX
    return special_folder(mailbox, _ROLE_FOLDERS[place.role])


def _settle_folders(groups: Any, act: Callable[[Group, _Settled], None]) -> _Settled:
    """Each folder's messages acted on in turn; a failure after one was done stops there."""
    settled = _Settled()
    stopped = False
    for members in groups:
        ids = [message_id for message_id, _ in members]
        if stopped:
            settled.mark(ids, READ_STATE_UNANSWERED)
            continue
        try:
            act(members, settled)
        except Exception as failure:
            if not settled.done:
                raise
            stopped = True
            settled.mark(ids, READ_STATE_UNANSWERED)
            logger.warning(
                "apple_mail_act_interrupted",
                done=len(settled.done),
                error_type=type(failure).__name__,
            )
    return settled


def _present(
    mailbox: MailBox, members: Group, principal: str, settled: _Settled
) -> tuple[str | None, Group]:
    """Select the members' folder: its name and the members it still holds.

    The others are marked gone; no folder answers for the whole group.
    """
    folder = select_message_folder(mailbox, members[0][1], principal=principal)
    if folder is None:
        settled.mark([message_id for message_id, _ in members], READ_STATE_NOT_FOUND)
        return None, []
    held = set(mailbox.uids(AND(uid=[location.uid for _, location in members])))
    settled.mark(
        [message_id for message_id, location in members if location.uid not in held],
        READ_STATE_NOT_FOUND,
    )
    return folder, [member for member in members if member[1].uid in held]


def _move_one_folder(
    mailbox: MailBox, members: Group, destination: str, principal: str, settled: _Settled
) -> None:
    """Move what one folder still holds, then read what each message is called there."""
    source, found = _present(mailbox, members, principal, settled)
    if source is None or not found:
        return
    if source == destination:
        settled.done.update({message_id: message_id for message_id, _ in found})
        return
    uids = [location.uid for _, location in found]
    own_ids = _own_ids(mailbox, uids)
    move_messages(mailbox, uids, destination)
    settled.done.update(_new_ids(mailbox, found, own_ids, destination, principal))


def _own_ids(mailbox: MailBox, uids: list[str]) -> dict[str, str]:
    """Each UID's ``Message-ID``, when it is one a search can carry."""
    found: dict[str, str] = {}
    for message in mailbox.fetch(AND(uid=uids), mark_seen=False, headers_only=True):
        values = message.headers.get("message-id") or ()
        own_id = str(values[0]).strip() if values else ""
        if _PLAIN_MESSAGE_ID.fullmatch(own_id) and message.uid:
            found[message.uid] = own_id
    return found


def _new_ids(
    mailbox: MailBox, found: Group, own_ids: dict[str, str], destination: str, principal: str
) -> Moved:
    """What each moved message is called now; a failure here costs the way back alone."""
    moved: Moved = dict.fromkeys((message_id for message_id, _ in found), None)
    try:
        mailbox.folder.set(destination)
        scope = mailbox_scope(mailbox, destination, principal)
        for message_id, location in found:
            own_id = own_ids.get(location.uid)
            hits = mailbox.uids(AND(header=Header("Message-ID", own_id))) if own_id else []
            if len(hits) == 1:
                moved[message_id] = message_handle(destination, hits[0], scope=scope)
    except Exception as failure:
        logger.info("apple_moved_ids_not_read", error_type=type(failure).__name__)
    return moved


def _delete_one_folder(
    mailbox: MailBox, members: Group, trash: str, principal: str, settled: _Settled
) -> None:
    """Delete for good what the trash holds of a group; another folder's are refused."""
    folder, found = _present(mailbox, members, principal, settled)
    if folder is None or not found:
        return
    ids = [message_id for message_id, _ in found]
    if folder != trash:
        settled.mark(ids, READ_STATE_FAILED)
        return
    remove_messages(mailbox, [location.uid for _, location in found])
    settled.done.update(dict.fromkeys(ids))


def _unseen(mailbox: MailBox, folder: str) -> int | None:
    """A folder's unread figure; None when the server refuses to say."""
    try:
        return int(mailbox.folder.status(folder, ["UNSEEN"])["UNSEEN"])
    except (UnexpectedCommandStatusError, KeyError, ValueError) as refused:
        logger.debug("apple_unread_count_refused", error_type=type(refused).__name__)
        return None


def _junk_unseen(mailbox: MailBox) -> int | None:
    try:
        return _unseen(mailbox, special_folder(mailbox, JUNK_ROLE))
    except MailboxFolderUnavailableError:
        return None


__all__ = ["AppleMailboxActsMixin"]
