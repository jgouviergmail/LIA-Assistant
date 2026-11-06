"""OneDrive through Microsoft Graph, on the files contract (ADR-369, lot 6, A4).

Implements ``FilesClientProtocol`` by structural typing, in Drive's words
(``normalizers/onedrive_normalizer``), so that a reader of files never asks which provider
answered. What OneDrive does differently stays here:

- Graph's folders do not sort first: a page is, and pages stay in Graph's order.
- Graph's search reads names, metadata and content at once; « by name » keeps, on each page,
  what the name holds, so a page may be partial before the end, as Drive's may.
- A file's bytes leave from the short-lived address Graph names beside its metadata, which
  takes no token: the person's token never reaches the storage host.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import quote, urlsplit

import httpx
import structlog
from fastapi import status

from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    ONEDRIVE_REFUSED_NAME_CHARACTERS,
    ONEDRIVE_SEARCH_EVERYTHING,
    WORKBENCH_UPLOAD_TIMEOUT_SECONDS,
)
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.files_management import (
    FileNameRefusedError,
    FileNameTakenError,
)
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
from src.domains.connectors.clients.normalizers.onedrive_normalizer import (
    DRIVE_ITEM_FIELDS,
    normalize_drive_item,
)
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.clients.onedrive_changes import OneDriveChangesMixin
from src.domains.connectors.clients.onedrive_recent import recent_window
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: The top of the drive, as Drive's alias names it.
_ROOT: Final = "root"
_REFUSED_NAME_CHARACTERS: Final = frozenset(ONEDRIVE_REFUSED_NAME_CHARACTERS)
#: A link anyone can follow; one limited to an organisation is no such link.
_ANONYMOUS: Final = "anonymous"
#: The contract's roles in Graph's words.
_GRAPH_ROLES: Final = {"reader": "read", "writer": "write"}
#: Drive's orders, as the workbench asks them, in Graph's words.
_ORDERS: Final[dict[str, str]] = {
    "folder,name": "name asc",
    "folder,modifiedTime desc": "lastModifiedDateTime desc",
    "folder,quotaBytesUsed desc": "size desc",
}
_DOWNLOAD_ADDRESS: Final = "@microsoft.graph.downloadUrl"
_CONVERSION_ADDRESS: Final = "address"
#: What a download reads at a time, so that a body past the ceiling stops there.
_DOWNLOAD_CHUNK_BYTES: Final = 64 * 1024
#: Why Graph refuses to replace a file someone else holds.
_HELD_ELSEWHERE: Final = {
    status.HTTP_412_PRECONDITION_FAILED: OfficeRefusal.CHANGED,
    status.HTTP_423_LOCKED: OfficeRefusal.LOCKED,
}


def _role_of(raw: dict[str, Any]) -> str:
    """A permission's role in the contract's words."""
    roles = raw.get("roles") or []
    if "owner" in roles:
        return "owner"
    return "writer" if "write" in roles else "reader"


def _identity_of(raw: dict[str, Any]) -> dict[str, Any]:
    """Who a permission names: one person, or the first of those it lists."""
    granted = raw.get("grantedToV2") or next(iter(raw.get("grantedToIdentitiesV2") or []), {})
    return granted.get("user") or {}


def _person_of(raw: dict[str, Any]) -> dict[str, Any]:
    identity = _identity_of(raw)
    return {
        "id": str(raw.get("id")),
        "email": identity.get("email"),
        "name": identity.get("displayName"),
        "role": _role_of(raw),
    }


def _link_of(raw: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(raw.get("id")), "url": (raw.get("link") or {}).get("webUrl")}


def _is_anyone_link(raw: dict[str, Any]) -> bool:
    return (raw.get("link") or {}).get("scope") == _ANONYMOUS


def _item_path(item_id: str) -> str:
    """An item's address: its id as ONE path segment, or the top of the drive."""
    if item_id == _ROOT:
        return "/me/drive/root"
    return (
        f"/me/drive/items/{path_segment(item_id, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)}"
    )


def _kept(files: list[dict[str, Any]], content_type: str | None) -> list[dict[str, Any]]:
    """The kinds asked for, folders first, as Drive's listings read."""
    folders = [item for item in files if item["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME]
    others = [item for item in files if item["mimeType"] != GOOGLE_DRIVE_FOLDER_MIME]
    if content_type == "files_only":
        return others
    if content_type == "folders_only":
        return folders
    return [*folders, *others]


def _name_must_be_accepted(name: str) -> None:
    """Refuse what Graph would answer with a bare 400, before anything leaves.

    Raises:
        FileNameRefusedError: The name holds a character OneDrive refuses.
    """
    if _REFUSED_NAME_CHARACTERS.intersection(name):
        raise FileNameRefusedError


@contextmanager
def _name_must_be_free() -> Iterator[None]:
    """Graph's conflict on a name, in the contract's words."""
    try:
        yield
    except ConnectorAPIError as error:
        if error.upstream_status_code == status.HTTP_409_CONFLICT:
            raise FileNameTakenError from error
        raise


def _conversion_address(response: httpx.Response) -> dict[str, Any]:
    """Where Graph put a conversion: short-lived, and nothing of the person travels with it."""
    address = response.headers.get("Location") or ""
    if urlsplit(address).scheme != "https":
        raise ValueError("Graph named no address for this conversion.")
    return {_CONVERSION_ADDRESS: address}


class MicrosoftOneDriveClient(OneDriveChangesMixin, BaseMicrosoftClient):
    """OneDrive, personal or business, through Graph's ``/me/drive``."""

    connector_type = ConnectorType.MICROSOFT_ONEDRIVE

    async def list_files(
        self,
        folder_id: str = _ROOT,
        max_results: int = 20,
        page_token: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        order_by: str = "folder,name",
    ) -> dict[str, Any]:
        """One page of a folder.

        Args:
            folder_id: The folder, ``root`` for the top of the drive.
            max_results: The page's size, within the connectors' ceiling.
            page_token: The next page's token, from a previous answer.
            fields: Unused: kept for the contract (Graph is asked ``_SELECT``).
            content_type: ``files_only``, ``folders_only``, or anything else for both.
            order_by: One of Drive's orders; an unknown one is Graph's own order.

        Returns:
            ``files`` and ``nextPageToken``.
        """
        params: dict[str, Any] = {
            "$top": apply_max_items_limit(max_results),
            "$select": DRIVE_ITEM_FIELDS,
            **graph_page_params(page_token),
        }
        if order_by in _ORDERS:
            params["$orderby"] = _ORDERS[order_by]
        raw = await self._make_request("GET", f"{_item_path(folder_id)}/children", params)
        return self._page(raw, content_type)

    async def search_files(
        self,
        query: str,
        max_results: int = 10,
        mime_type: str | None = None,
        folder_id: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        search_mode: str = "name_only",
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Words looked for across the drive.

        Args:
            query: The words.
            max_results: The page's size, within the connectors' ceiling.
            mime_type: Keeps that type alone.
            folder_id: Unused: Graph searches a whole drive.
            fields: Unused: kept for the contract.
            content_type: ``files_only``, ``folders_only``, or anything else for both.
            search_mode: ``name_only`` keeps what the name holds; ``full_text`` what Graph found.
            page_token: The next page's token, from a previous answer.

        Returns:
            ``files`` and ``nextPageToken``; a page may be partial before the end.
        """
        words = quote((query or ONEDRIVE_SEARCH_EVERYTHING).replace("'", "''"), safe="")
        params: dict[str, Any] = {
            "$top": apply_max_items_limit(max_results),
            "$select": DRIVE_ITEM_FIELDS,
            **graph_page_params(page_token),
        }
        raw = await self._make_request("GET", f"/me/drive/root/search(q='{words}')", params)
        page = self._page(raw, content_type)
        if search_mode == "name_only":
            wanted = query.casefold()
            page["files"] = [item for item in page["files"] if wanted in item["name"].casefold()]
        if mime_type:
            page["files"] = [item for item in page["files"] if item["mimeType"] == mime_type]
        return page

    async def recent_files(self, max_results: int) -> dict[str, Any]:
        """The files changed last, as far as the drive's feed has told (``onedrive_recent``).

        Args:
            max_results: How many files to keep.

        Returns:
            ``files``, newest first; never a folder.
        """
        return {"files": await recent_window(self, max_results)}

    async def folder_path(self, file: Mapping[str, Any], known: dict[str, Any]) -> str | None:
        """An item's folders from the top of the drive: Graph says them on the item itself.

        Args:
            file: The item; a listing from the feed does not carry its path.
            known: Unused: kept for the contract (a read answers the whole path).

        Returns:
            The path, empty at the top of the drive.
        """
        return (await self.get_file_metadata(str(file["id"])))["folderPath"]

    async def get_file_metadata(
        self, file_id: str, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """One item.

        Args:
            file_id: The item, ``root`` for the top of the drive.
            fields: Unused: kept for the contract.

        Returns:
            The item.
        """
        return normalize_drive_item(await self._make_request("GET", _item_path(file_id)))

    async def get_file_content(
        self,
        file_id: str,
        max_size_bytes: int = 10 * 1024 * 1024,
        known_size: int | None = None,
    ) -> bytes | None:
        """A file's bytes, never past the ceiling.

        Args:
            file_id: The file.
            max_size_bytes: The most that is read.
            known_size: Unused: the address is read with the size beside it.

        Returns:
            Its bytes; None when it is larger than the ceiling.

        Raises:
            ValueError: It has no bytes (a OneNote package, a folder).
        """
        raw = await self._make_request("GET", _item_path(file_id))
        if int(raw.get("size") or 0) > max_size_bytes:
            return None
        address = raw.get(_DOWNLOAD_ADDRESS)
        if not isinstance(address, str) or urlsplit(address).scheme != "https":
            raise ValueError("This item has no content to download.")
        return await self._read_bounded(address, max_size_bytes)

    async def converted_to_pdf(self, file_id: str, max_size_bytes: int) -> bytes | None:
        """A file as Graph renders it to a PDF, never past the ceiling.

        Args:
            file_id: The file: one the normaliser says converts.
            max_size_bytes: The most that is read.

        Returns:
            The PDF; None when it passes the ceiling.

        Raises:
            ValueError: Graph named no address to read it from.
        """
        located = await self._make_request(
            "GET",
            f"{_item_path(file_id)}/content",
            {"format": "pdf"},
            answer=_conversion_address,
        )
        return await self._read_bounded(located[_CONVERSION_ADDRESS], max_size_bytes)

    async def drive_type(self) -> str:
        """What this drive is: ``personal``, ``business`` or ``documentLibrary``.

        Returns:
            Graph's word for it.
        """
        return str(
            (await self._make_request("GET", "/me/drive", {"$select": "driveType"}))["driveType"]
        )

    async def workbook_request(
        self,
        method: str,
        file_id: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """A call of Graph's Excel API, which a work drive alone holds.

        Args:
            method: The HTTP method.
            file_id: The workbook.
            path: What follows ``workbook/``, each of its values already one path segment.
            params: The query.
            json_data: The body.

        Returns:
            Graph's answer.
        """
        endpoint = f"{_item_path(file_id)}/workbook/{path}"
        return await self._make_request(method, endpoint, params, json_data)

    async def replace_content(
        self, file_id: str, data: bytes, mime_type: str, expected_tag: str
    ) -> dict[str, Any]:
        """Replace a file's bytes, only as it was when read.

        Sent once: a lost answer leaves the file unknown, and the tag it was read at would refuse
        a second try anyway.

        Args:
            file_id: The file.
            data: Its new bytes (Graph takes up to 250 MB in one call).
            mime_type: Its type.
            expected_tag: The ``eTag`` it was read at.

        Returns:
            The item as it now is.

        Raises:
            OfficeContentRefusedError: It changed since, or someone holds it locked. An answer
                that keeps the tag wrote nothing, whatever its status says.
        """
        try:
            written = await self._make_request(
                "PUT",
                f"{_item_path(file_id)}/content",
                max_retries=1,
                extra_headers={"Content-Type": mime_type, "If-Match": expected_tag},
                content=data,
                timeout=httpx.Timeout(WORKBENCH_UPLOAD_TIMEOUT_SECONDS),
            )
        except ConnectorAPIError as error:
            refusal = _HELD_ELSEWHERE.get(error.upstream_status_code)
            if refusal is None:
                raise
            raise OfficeContentRefusedError(refusal) from error
        if written.get("eTag") == expected_tag:
            raise OfficeContentRefusedError(OfficeRefusal.CHANGED)
        return normalize_drive_item(written)

    async def delete_file(self, file_id: str) -> bool:
        """Move a file to the recycle bin: Graph's delete keeps it there.

        Args:
            file_id: The file.

        Returns:
            True once done.
        """
        await self._make_request("DELETE", _item_path(file_id))
        logger.info("onedrive_file_deleted", user_id=str(self.user_id), file_id=file_id)
        return True

    async def read_sharing(self, file_id: str) -> dict[str, Any]:
        """Who reaches an item, and the link anyone can follow, if it has one.

        A link kept to an organisation is neither: it names nobody, and anyone cannot follow it.

        Args:
            file_id: The item.

        Returns:
            ``people`` and ``link``.
        """
        answer = await self._make_request("GET", f"{_item_path(file_id)}/permissions")
        permissions = answer.get("value") or []
        anyone = next((raw for raw in permissions if _is_anyone_link(raw)), None)
        return {
            "people": [_person_of(raw) for raw in permissions if not raw.get("link")],
            "link": _link_of(anyone) if anyone else None,
        }

    async def share_with(self, file_id: str, email: str, role: str) -> None:
        """Give a person access; Graph tells them.

        Args:
            file_id: The item.
            email: Their address.
            role: ``reader`` or ``writer``.
        """
        await self._make_request(
            "POST",
            f"{_item_path(file_id)}/invite",
            json_data={
                "recipients": [{"email": email}],
                "roles": [_GRAPH_ROLES[role]],
                "requireSignIn": True,
                "sendInvitation": True,
            },
            max_retries=1,
        )

    async def open_link(self, file_id: str) -> dict[str, Any]:
        """Let anyone with the link read an item.

        Args:
            file_id: The item.

        Returns:
            The link: its ``id`` and its ``url``.
        """
        raw = await self._make_request(
            "POST",
            f"{_item_path(file_id)}/createLink",
            json_data={"type": "view", "scope": _ANONYMOUS},
            max_retries=1,
        )
        return _link_of(raw)

    async def remove_share(self, file_id: str, permission_id: str) -> None:
        """Take an access back.

        Args:
            file_id: The item.
            permission_id: The access.
        """
        segment = path_segment(permission_id, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)
        await self._make_request("DELETE", f"{_item_path(file_id)}/permissions/{segment}")

    async def storage_quota(self) -> dict[str, int | None]:
        """What the account uses of what it has.

        Returns:
            ``used`` and ``total``, in bytes.
        """
        answer = await self._make_request("GET", "/me/drive", {"$select": "quota"})
        quota = answer.get("quota") or {}
        total = quota.get("total")
        return {"used": int(quota.get("used") or 0), "total": int(total) if total else None}

    async def restore_file(self, file_id: str) -> dict[str, Any]:
        """Take an item out of the recycle bin: a call of OneDrive Personal alone.

        Args:
            file_id: The item.

        Returns:
            The item.
        """
        raw = await self._make_request("POST", f"{_item_path(file_id)}/restore", json_data={})
        return normalize_drive_item(raw)

    async def create_folder(self, name: str, parent_id: str = _ROOT) -> dict[str, Any]:
        """Create a folder; a name taken is refused, never turned into another.

        Args:
            name: Its name.
            parent_id: Its parent, ``root`` for the top of the drive.

        Returns:
            The folder.

        Raises:
            FileNameRefusedError: OneDrive takes no such name.
            FileNameTakenError: The parent holds an item of that name.
        """
        _name_must_be_accepted(name)
        body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        with _name_must_be_free():
            raw = await self._make_request(
                "POST", f"{_item_path(parent_id)}/children", json_data=body
            )
        return normalize_drive_item(raw)

    async def rename_file(self, file_id: str, name: str) -> dict[str, Any]:
        """Give an item another name.

        Args:
            file_id: The item.
            name: Its new name.

        Returns:
            The item.

        Raises:
            FileNameRefusedError: OneDrive takes no such name.
            FileNameTakenError: Its folder holds an item of that name.
        """
        _name_must_be_accepted(name)
        with _name_must_be_free():
            raw = await self._make_request("PATCH", _item_path(file_id), json_data={"name": name})
        return normalize_drive_item(raw)

    async def move_file(self, file_id: str, parent_id: str) -> dict[str, Any]:
        """Move an item.

        Args:
            file_id: The item.
            parent_id: Its new parent, ``root`` for the top of the drive.

        Returns:
            The item.

        Raises:
            FileNameTakenError: The new folder holds an item of that name.
        """
        target = await self._real_id(parent_id)
        with _name_must_be_free():
            raw = await self._make_request(
                "PATCH", _item_path(file_id), json_data={"parentReference": {"id": target}}
            )
        return normalize_drive_item(raw)

    async def upload_file(
        self, name: str, data: bytes, mime_type: str, parent_id: str = _ROOT
    ) -> dict[str, Any]:
        """Add a file to a folder, never over one it holds.

        A PUT on a path replaces what is there, and its conflict rule is not documented on
        this call: what the folder holds is read first. The bytes are sent once, a lost
        answer leaving the file unknown rather than a name taken by the first try.

        Args:
            name: Its name.
            data: Its bytes (Graph takes up to 250 MB in one call).
            mime_type: Its type.
            parent_id: Its folder, ``root`` for the top of the drive.

        Returns:
            The file.

        Raises:
            FileNameRefusedError: OneDrive takes no such name.
            FileNameTakenError: The folder holds an item of that name.
        """
        _name_must_be_accepted(name)
        await self._name_must_be_unused(parent_id, name)
        segment = path_segment(name, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)
        with _name_must_be_free():
            raw = await self._make_request(
                "PUT",
                f"{_item_path(parent_id)}:/{segment}:/content",
                {"@microsoft.graph.conflictBehavior": "fail"},
                max_retries=1,
                extra_headers={"Content-Type": mime_type},
                content=data,
                timeout=httpx.Timeout(WORKBENCH_UPLOAD_TIMEOUT_SECONDS),
            )
        return normalize_drive_item(raw)

    async def copy_file(
        self, file_id: str, parent_id: str | None = None, name: str | None = None
    ) -> dict[str, Any] | None:
        """Ask Graph to copy a file: its own work, finished after it answers.

        Args:
            file_id: The file.
            parent_id: The folder it goes to; left out, beside the original.
            name: Its name; a copy beside the original needs one.

        Returns:
            None: Graph has only accepted; the copy appears in its folder when done.

        Raises:
            FileNameRefusedError: OneDrive takes no such name.
            FileNameTakenError: The folder it goes to holds an item of that name.
        """
        if name:
            _name_must_be_accepted(name)
        source = await self._make_request("GET", _item_path(file_id))
        reference = source.get("parentReference") or {}
        target = await self._real_id(parent_id) if parent_id else str(reference.get("id"))
        await self._name_must_be_unused(target, name or str(source.get("name")))
        body: dict[str, Any] = {
            "parentReference": {"driveId": reference.get("driveId"), "id": target}
        }
        if name:
            body["name"] = name
        with _name_must_be_free():
            await self._make_request("POST", f"{_item_path(file_id)}/copy", json_data=body)
        return None

    async def _name_must_be_unused(self, folder_id: str, name: str) -> None:
        """Refuse a copy Graph would accept, then fail where nobody hears it.

        Graph answers 202 and finds the conflict in its own time, and OneDrive Consumer takes
        no ``conflictBehavior``: the only moment to say it is before asking.

        Args:
            folder_id: The folder the copy goes to.
            name: The name it would take there.

        Raises:
            FileNameTakenError: The folder holds an item of that name.
        """
        segment = path_segment(name, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)
        try:
            await self._make_request(
                "GET", f"{_item_path(folder_id)}:/{segment}", {"$select": "id"}
            )
        except ConnectorAPIError as error:
            if error.upstream_status_code == status.HTTP_404_NOT_FOUND:
                return
            raise
        raise FileNameTakenError

    async def _real_id(self, item_id: str) -> str:
        """An id Graph takes in a reference: ``root`` is an address, never an id."""
        if item_id != _ROOT:
            return item_id
        return str((await self._make_request("GET", _item_path(_ROOT))).get("id"))

    def _page(self, raw: dict[str, Any], content_type: str | None) -> dict[str, Any]:
        """A Graph answer as the contract's page."""
        files = [normalize_drive_item(item) for item in raw.get("value", [])]
        return {
            "files": _kept(files, content_type),
            "nextPageToken": graph_page_token(raw.get("@odata.nextLink")),
        }

    async def _read_bounded(self, address: str, ceiling: int) -> bytes | None:
        """The body at ``address``; None the moment it passes the ceiling.

        The address is Graph's, short-lived and pre-authenticated: nothing of the person
        travels with it.
        """
        client = await self._get_client()
        read = bytearray()
        async with client.stream("GET", address) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_BYTES):
                read.extend(chunk)
                if len(read) > ceiling:
                    return None
        return bytes(read)


__all__ = ["MicrosoftOneDriveClient"]
