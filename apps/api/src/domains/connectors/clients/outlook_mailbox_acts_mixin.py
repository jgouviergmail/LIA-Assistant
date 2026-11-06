"""Sorting an Outlook mailbox through Microsoft Graph (ADR-369, lot 4).

Beside the client, which keeps the reads and sends of received mail. A move is
Graph's own ``move``, one message at a time (there is no batch): it answers the
message at its new place, and that is its id from then on. A role is a well-known
folder name, which holds in every language; a folder of the person's own is found by
the path the pane names it by.

« For good » means the ``purges`` folder of the mailbox's dumpster: no mail client
reaches it, and the mailbox's retention deletes it. Nothing but a message of Deleted
Items goes there, whatever id a caller hands in: the folder is read first, because a
wrong id here cannot be undone.

A folder holding anything is never deleted. Measured on outlook.com (2026-11-05):
``DELETE`` answers 204 and what the folder held then reaches no folder the person can
open, Deleted Items included, whatever Outlook's own screen does with the same gesture.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.mail_folders import (
    MailFolder,
    MailFolderNotEmptyError,
    SystemFolderError,
)
from src.domains.connectors.clients.mail_moves import (
    MailPlace,
    MailPlaceRole,
    MessageElsewhereError,
    UnreadCounts,
    moved_result,
    settle_each,
)
from src.domains.connectors.clients.mail_read_state import read_state_result, unique_ids
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: What Graph calls each role, in every language of a mailbox.
_WELL_KNOWN: Final[dict[MailPlaceRole, str]] = {
    "inbox": "inbox",
    "archive": "archive",
    "spam": "junkemail",
    "trash": "deleteditems",
}
_TRASH_FOLDER: Final = "/me/mailFolders/deleteditems"


class _OutlookActsHost(Protocol):
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
        idempotent: bool | None = None,
    ) -> dict[str, Any]: ...

    async def _folder_id(self, name: str) -> str: ...

    async def list_folders(self) -> tuple[list[MailFolder], bool]: ...

    async def _patch_each(self, ids: list[str], change: dict[str, Any]) -> dict[str, Any]: ...

    async def _role_unread(self, role: MailPlaceRole) -> int | None: ...

    async def _delete_for_good(self, message_id: str) -> None: ...

    async def system_folder_ids(self) -> frozenset[str]: ...

    async def _own_folder_id(self, name: str) -> str: ...


class OutlookMailboxActsMixin:
    """Moves, star, deletion for good, unread figures and folders of an Outlook mailbox."""

    async def move_emails(
        self: _OutlookActsHost,
        message_ids: Sequence[str],
        place: MailPlace,
        origin: MailPlace | None = None,
    ) -> dict[str, Any]:
        """Send messages to a place; each one answers with its new id.

        Args:
            message_ids: The messages (each counted once).
            place: Where they go.
            origin: Unused: a Graph message is moved from wherever it is.

        Returns:
            ``mail_moves.moved_result``.
        """
        ids = unique_ids(message_ids)
        destination = (
            _WELL_KNOWN[place.role] if place.role else await self._folder_id(str(place.folder))
        )

        async def move(message_id: str) -> str | None:
            arrived = await self._make_request(
                "POST",
                f"/me/messages/{_segment(message_id)}/move",
                json_data={"destinationId": destination},
            )
            return str(arrived.get("id") or "") or None

        result = moved_result(*await settle_each(ids, move))
        logger.info(
            "outlook_messages_moved",
            user_id=str(self.user_id),
            moved=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result

    async def place_named(self: _OutlookActsHost, name: str) -> MailPlace:
        """A folder is found by its name when a move reads it."""
        return MailPlace(folder=name)

    async def set_starred(
        self: _OutlookActsHost, message_ids: Sequence[str], starred: bool
    ) -> dict[str, Any]:
        """Flag messages or clear their flag, and say which could not be.

        Args:
            message_ids: The messages (each counted once).
            starred: True to flag them.

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}`` (``mail_read_state``).
        """
        status = "flagged" if starred else "notFlagged"
        return await self._patch_each(unique_ids(message_ids), {"flag": {"flagStatus": status}})

    async def _patch_each(
        self: _OutlookActsHost, ids: list[str], change: dict[str, Any]
    ) -> dict[str, Any]:
        """One PATCH per message, a few at a time, each one answered.

        Setting a state twice leaves it set once: a lost answer may be resent.
        """

        async def patch(message_id: str) -> None:
            await self._make_request(
                "PATCH",
                f"/me/messages/{_segment(message_id)}",
                json_data=change,
                idempotent=True,
            )

        done, failed = await settle_each(ids, patch)
        return read_state_result(list(done), failed)

    async def delete_emails_forever(
        self: _OutlookActsHost, message_ids: Sequence[str]
    ) -> dict[str, Any]:
        """Delete messages of the trash for good; any other is refused alone.

        Args:
            message_ids: The messages (each counted once).

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}`` (``mail_read_state``).
        """
        trash = await self._make_request("GET", _TRASH_FOLDER, {"$select": "id"})

        async def delete(message_id: str) -> None:
            held = await self._make_request(
                "GET", f"/me/messages/{_segment(message_id)}", {"$select": "parentFolderId"}
            )
            if not held.get("parentFolderId") or held["parentFolderId"] != trash.get("id"):
                raise MessageElsewhereError
            await self._delete_for_good(message_id)

        done, failed = await settle_each(unique_ids(message_ids), delete)
        logger.info(
            "outlook_messages_deleted_for_good",
            user_id=str(self.user_id),
            deleted=len(done),
            failed=len(failed),
        )
        return read_state_result(list(done), failed)

    async def empty_trash(self: _OutlookActsHost, limit: int) -> dict[str, Any]:
        """Delete for good what the trash holds, within a bound.

        Args:
            limit: The messages deleted by one call at most.

        Returns:
            ``{"deleted": n, "remaining": bool}``: the trash holds more, or a message
            of it could not be deleted.
        """
        page = await self._make_request(
            "GET",
            f"{_TRASH_FOLDER}/messages",
            {"$select": "id", "$top": apply_max_items_limit(limit)},
        )
        ids = [str(item["id"]) for item in page.get("value", []) if item.get("id")]

        async def delete(message_id: str) -> None:
            await self._delete_for_good(message_id)

        done, failed = await settle_each(ids, delete)
        logger.info(
            "outlook_trash_emptied",
            user_id=str(self.user_id),
            deleted=len(done),
            failed=len(failed),
        )
        return {"deleted": len(done), "remaining": bool(page.get("@odata.nextLink") or failed)}

    async def unread_counts(self: _OutlookActsHost, folders_max: int) -> UnreadCounts:
        """What the mailbox leaves unread: the folder walk carries each folder's figure.

        Args:
            folders_max: Unused: the walk has its own bound, and costs one read a level
                whatever is kept of it.

        Returns:
            The figures, ``complete`` False when the walk was cut.
        """
        folders, complete = await self.list_folders()
        inbox, spam = await asyncio.gather(self._role_unread("inbox"), self._role_unread("spam"))
        roles = {"inbox": inbox, "spam": spam}
        return UnreadCounts(
            roles={role: count for role, count in roles.items() if count is not None},
            folders={item.path: item.unread for item in folders if item.unread is not None},
            complete=complete,
        )

    async def create_folder(self: _OutlookActsHost, name: str) -> str:
        """Create a folder of the person's own; « / » nests it, as a label's name does.

        Args:
            name: Its path; the parent must exist.

        Returns:
            The path the pane names it by.
        """
        parent, _, leaf = name.rpartition("/")
        endpoint = "/me/mailFolders"
        if parent:
            endpoint += f"/{_segment(await self._folder_id(parent))}/childFolders"
        await self._make_request("POST", endpoint, json_data={"displayName": leaf})
        return name

    async def rename_folder(self: _OutlookActsHost, folder: str, name: str) -> str:
        """Rename a folder of the person's own, in place.

        Args:
            folder: Its path.
            name: Its new own name, never a path.

        Returns:
            The path the pane names it by from now on.
        """
        target = await self._own_folder_id(folder)
        await self._make_request(
            "PATCH", f"/me/mailFolders/{_segment(target)}", json_data={"displayName": name}
        )
        parent = folder.rpartition("/")[0]
        return f"{parent}/{name}" if parent else name

    async def delete_folder(self: _OutlookActsHost, folder: str) -> None:
        """Delete a folder of the person's own that holds nothing.

        Args:
            folder: Its path.

        Raises:
            MailFolderNotEmptyError: It holds messages or folders.
        """
        target = await self._own_folder_id(folder)
        path = f"/me/mailFolders/{_segment(target)}"
        held = await self._make_request("GET", path, {"$select": "totalItemCount,childFolderCount"})
        if held.get("totalItemCount") or held.get("childFolderCount"):
            raise MailFolderNotEmptyError
        await self._make_request("DELETE", path)

    async def _own_folder_id(self: _OutlookActsHost, name: str) -> str:
        """The id of a folder of the person's own.

        Raises:
            SystemFolderError: It is one of the mailbox's own.
        """
        target = await self._folder_id(name)
        if target in await self.system_folder_ids():
            raise SystemFolderError
        return target

    async def _role_unread(self: _OutlookActsHost, role: MailPlaceRole) -> int | None:
        """A well-known folder's unread figure; None when the mailbox has no such folder."""
        try:
            folder = await self._make_request(
                "GET", f"/me/mailFolders/{_WELL_KNOWN[role]}", {"$select": "unreadItemCount"}
            )
        except ConnectorAPIError as refused:
            if refused.upstream_status_code == 404:
                return None
            raise
        return int(folder.get("unreadItemCount") or 0)

    async def _delete_for_good(self: _OutlookActsHost, message_id: str) -> None:
        await self._make_request("POST", f"/me/messages/{_segment(message_id)}/permanentDelete")


def _segment(graph_id: str) -> str:
    """An id handed in as ONE segment of a Graph URL path."""
    return path_segment(graph_id, connector_type=ConnectorType.MICROSOFT_OUTLOOK)


__all__ = ["OutlookMailboxActsMixin"]
