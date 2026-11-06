"""A text file changed by the person's own hand (ADR-369, lot 14).

Words a drive holds as plain bytes, read whole and written back whole, on the version they were
read at (``drive_text``): an edit made elsewhere meanwhile answers ``conflict``, and the words
typed stay on the page. An Office file or a Google document is changed where it lives, behind
« Open in … ». A click is its own confirmation, and nothing here reaches a model or a register.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.domains.connectors.clients.drive_text import read_text_file, rewrite_text_file
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.files_service import drive_item
from src.domains.workbench.schemas.files import DriveItem, FileText, FileTextChange

_TOOL = WorkbenchTool.FILES


async def read_text(user_id: UUID, file_id: str) -> FileText:
    """A text file's words, and the version a change must name.

    Raises:
        BaseAPIException: ``not_supported_by_provider`` when it cannot be edited here;
            ``too_large`` past the bound.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: Any = opened.client
        async with provider_call(_TOOL, "read_text", act=False):
            read = await read_text_file(client, file_id)
    return FileText(text=read.text, tag=read.tag)


async def write_text(user_id: UUID, change: FileTextChange) -> DriveItem:
    """Write a text file's words back.

    Raises:
        BaseAPIException: ``conflict`` when it changed since it was read; ``file_locked`` while
            someone holds it; ``too_large`` past the bound; ``outcome_unknown`` for a lost answer.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: Any = opened.client
        async with provider_call(_TOOL, "write_text", act=True):
            written = await rewrite_text_file(client, change.id, change.text, change.tag)
    return drive_item(written)


__all__ = ["read_text", "write_text"]
