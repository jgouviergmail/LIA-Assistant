"""Who a file is shared with, by the person's own hand (ADR-369, lot 6).

The same acts on Google Drive and OneDrive: read, give a person access, open a link anyone can
follow, take an access back. Giving access reaches a third party, whom the drive tells: it runs
once per submission, and its answer lost stays unknown rather than sent twice. The address a
drive answers is shown as a link, so only an https one is. An owner's own access is not taken
back: the drive would refuse it, and the page never offers it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from src.domains.connectors.clients.protocols import FilesClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import INVALID_REQUEST, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.files import (
    FileShare,
    FileShareRemoval,
    FileSharing,
    SharedLink,
    SharedPerson,
)

_TOOL = WorkbenchTool.FILES
_OWNER = "owner"


def _link(raw: Mapping[str, Any]) -> SharedLink:
    """A link, its address kept only if it is a web address of the drive."""
    url = raw.get("url")
    readable = isinstance(url, str) and urlsplit(url).scheme == "https"
    return SharedLink(id=str(raw.get("id")), url=url if readable else None)


def _sharing(raw: Mapping[str, Any]) -> FileSharing:
    link = raw.get("link")
    return FileSharing(
        people=[SharedPerson(**person) for person in raw.get("people") or []],
        link=_link(link) if link else None,
    )


async def read_sharing(user_id: UUID, file_id: str) -> FileSharing:
    """Who reaches an item.

    Args:
        user_id: The account.
        file_id: The item.

    Returns:
        Who was given access, and the link anyone can follow, if it has one.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "read_sharing", act=False):
            return _sharing(await client.read_sharing(file_id))


async def share_file(user_id: UUID, request: FileShare) -> None:
    """Give a person access, once per submission: the drive tells them.

    Args:
        user_id: The account.
        request: The item, the person and what they may do.
    """

    async def share() -> None:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: FilesClientProtocol = opened.client
            async with provider_call(_TOOL, "share", act=True):
                await client.share_with(request.file_id, request.email, request.role)

    await run_once(user_id, request.idempotency_key, share, tool=_TOOL.value)


async def open_link(user_id: UUID, file_id: str) -> SharedLink:
    """Let anyone with the link read an item.

    Args:
        user_id: The account.
        file_id: The item.

    Returns:
        The link.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "open_link", act=True):
            return _link(await client.open_link(file_id))


async def remove_share(user_id: UUID, request: FileShareRemoval) -> None:
    """Take an access back; an owner's own stays.

    Args:
        user_id: The account.
        request: The item and the access.

    Raises:
        BaseAPIException: ``invalid_request`` for an owner's access.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "read_sharing", act=False):
            sharing = _sharing(await client.read_sharing(request.file_id))
        owners = {person.id for person in sharing.people if person.role == _OWNER}
        if request.permission_id in owners:
            refuse(INVALID_REQUEST)
        async with provider_call(_TOOL, "remove_share", act=True):
            await client.remove_share(request.file_id, request.permission_id)


__all__ = ["open_link", "read_sharing", "remove_share", "share_file"]
