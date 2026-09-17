"""A fake Google Drive for the tree tests: folders hold children, one level per call."""

from __future__ import annotations

from typing import Any

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME

PDF = "application/pdf"


def drive_file(file_id: str, mime: str = PDF, **extra: Any) -> dict[str, Any]:
    """One Drive file resource as ``files.list`` returns it."""
    return {
        "id": file_id,
        "name": f"{file_id}.bin",
        "mimeType": mime,
        "modifiedTime": "2026-09-17T10:00:00Z",
        **extra,
    }


class FakeDriveClient:
    """``list_files`` honours one level, the content-type filter and paging."""

    def __init__(
        self,
        tree: dict[str, list[dict[str, Any]]],
        *,
        unreadable: set[str] | None = None,
        page_size: int = 100,
    ) -> None:
        self.tree = tree
        self.unreadable = unreadable or set()
        self.page_size = page_size
        self.calls: list[tuple[str, str | None]] = []

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 20,
        page_token: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
    ) -> dict[str, Any]:
        self.calls.append((folder_id, content_type))
        if folder_id in self.unreadable:
            raise RuntimeError("403 insufficient permissions")
        children = self.tree.get(folder_id, [])
        if content_type == "files_only":
            children = [c for c in children if c["mimeType"] != GOOGLE_DRIVE_FOLDER_MIME]
        elif content_type == "folders_only":
            children = [c for c in children if c["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME]
        start = int(page_token or 0)
        size = min(max_results, self.page_size)
        page = children[start : start + size]
        next_token = str(start + size) if start + size < len(children) else None
        return {"files": page, "nextPageToken": next_token}

    async def get_file_content(self, file_id: str, max_size_bytes: int = 0) -> bytes:
        return f"bytes-of-{file_id}".encode()

    async def export_google_doc(self, file_id: str, export_mime: str) -> bytes:
        return f"export-of-{file_id}".encode()

    async def close(self) -> None:
        return None
