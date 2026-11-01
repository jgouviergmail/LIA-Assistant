"""The Drive files of the « Tools » section (ADR-369, Task 8.1).

A folder lists its folders and files by cursor, a shortcut drawn as one; a
search is Drive-wide and pages by its cursor too (a page may be partial). A
file's breadcrumb walks up to My Drive under a bounded depth and says when it
stopped. A Google document downloads EXPORTED (Docs → PDF / DOCX, Sheets → XLSX,
Slides → PDF / PPTX), any other file as its bytes — never past the published
ceiling, which a listed size refuses before the body is read. A native type with
no export downloads nothing; a web link off Google is never handed on. The trash
answers each file.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import WORKBENCH_DRIVE_DETAIL_FIELDS, WORKBENCH_DRIVE_FIELDS
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import files_service
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.schemas.files import DownloadQuery, FileSelection, FilesQuery

pytestmark = pytest.mark.unit

USER = uuid4()
FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
SLIDES = "application/vnd.google-apps.presentation"
FORM = "application/vnd.google-apps.form"
SHORTCUT = "application/vnd.google-apps.shortcut"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_DRIVE, preferred_name=None
        )

    return patch.object(files_service, "open_tool_client", opened)


def _file(file_id: str, mime: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": file_id,
        "name": f"Item {file_id}",
        "mimeType": mime,
        "modifiedTime": "2026-10-30T09:15:00.000Z",
        "webViewLink": f"https://docs.google.com/d/{file_id}",
        **extra,
    }


def _refused(caught: pytest.ExceptionInfo[BaseAPIException]) -> Any:
    detail = caught.value.detail
    return detail["code"] if isinstance(detail, dict) else detail


class TestTheListing:
    async def test_a_folder_lists_its_folders_and_files_by_cursor(self) -> None:
        files = [
            _file("d1", FOLDER),
            _file("g1", DOC),
            _file("p1", "application/pdf", size="2048"),
            _file("s1", SHORTCUT, shortcutDetails={"targetId": "d9", "targetMimeType": FOLDER}),
            _file("x1", FORM),
        ]
        client = MagicMock(
            list_files=AsyncMock(return_value={"files": files, "nextPageToken": "n2"})
        )
        with _door(client):
            page = await files_service.list_files(USER, FilesQuery(folder_id="d0", page_token="n1"))

        client.list_files.assert_awaited_once_with(
            folder_id="d0",
            max_results=listing_page_size(),
            page_token="n1",
            fields=list(WORKBENCH_DRIVE_FIELDS),
            content_type="all",
        )
        shown = {item.id: item for item in page.items}
        assert [(item.id, item.kind) for item in page.items] == [
            ("d1", "folder"),
            ("g1", "file"),
            ("p1", "file"),
            ("s1", "shortcut"),
            ("x1", "file"),
        ]
        assert (shown["g1"].formats, shown["g1"].downloadable) == (["pdf", "docx"], True)
        assert (shown["p1"].formats, shown["p1"].downloadable, shown["p1"].size) == ([], True, 2048)
        assert (shown["s1"].target_id, shown["s1"].target_kind) == ("d9", "folder")
        assert (shown["x1"].downloadable, shown["d1"].downloadable) == (False, False)
        assert page.next_page_token == "n2"

    async def test_my_drive_is_listed_when_no_folder_is_named(self) -> None:
        client = MagicMock(list_files=AsyncMock(return_value={"files": []}))
        with _door(client):
            page = await files_service.list_files(USER, FilesQuery())

        assert client.list_files.await_args.kwargs["folder_id"] == "root"
        assert (page.items, page.next_page_token) == ([], None)

    @pytest.mark.parametrize(("full_text", "mode"), [(False, "name_only"), (True, "full_text")])
    async def test_a_search_is_drive_wide_and_pages_by_its_cursor(
        self, full_text: bool, mode: str
    ) -> None:
        # Drive may answer a partial page before the end: only its cursor says more.
        client = MagicMock(
            search_files=AsyncMock(
                return_value={"files": [_file("f1", "application/pdf")], "nextPageToken": "n2"}
            )
        )
        with _door(client):
            page = await files_service.list_files(
                USER, FilesQuery(q="budget", full_text=full_text, page_token="n1")
            )

        client.search_files.assert_awaited_once_with(
            "budget",
            max_results=listing_page_size(),
            fields=list(WORKBENCH_DRIVE_FIELDS),
            content_type="all",
            search_mode=mode,
            page_token="n1",
        )
        assert ([item.id for item in page.items], page.next_page_token) == (["f1"], "n2")

    def test_a_search_inside_a_folder_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            FilesQuery(q="budget", folder_id="d0")

    @pytest.mark.parametrize(
        ("link", "kept"),
        [
            ("https://docs.google.com/document/d/g1/edit", True),
            ("https://drive.google.com/file/d/p1/view", True),
            ("javascript:alert(1)", False),
            ("https://docs.google.com.evil.example/d/g1", False),
            ("http://docs.google.com/document/d/g1", False),
        ],
    )
    async def test_a_web_link_off_google_is_never_handed_on(self, link: str, kept: bool) -> None:
        client = MagicMock(
            list_files=AsyncMock(return_value={"files": [_file("g1", DOC, webViewLink=link)]})
        )
        with _door(client):
            page = await files_service.list_files(USER, FilesQuery())

        assert page.items[0].web_url == (link if kept else None)


class TestTheDetail:
    @staticmethod
    def _tree(chain: dict[str, list[str]]) -> AsyncMock:
        async def metadata(file_id: str, fields: list[str] | None = None) -> dict[str, Any]:
            if file_id == "root":
                return {"id": "R"}
            node = _file(file_id, FOLDER if file_id != "f1" else "application/pdf")
            return {**node, "parents": chain.get(file_id, [])}

        return AsyncMock(side_effect=metadata)

    async def test_a_file_s_breadcrumb_walks_up_to_my_drive(self) -> None:
        tree = self._tree({"f1": ["p2"], "p2": ["p1"], "p1": ["R"], "R": []})
        client = MagicMock(get_file_metadata=tree)
        with _door(client):
            detail = await files_service.read_file(USER, "f1")

        assert tree.await_args_list[0].args == ("f1",)
        assert tree.await_args_list[0].kwargs == {"fields": list(WORKBENCH_DRIVE_DETAIL_FIELDS)}
        assert [(item.id, item.name) for item in detail.ancestors] == [
            ("p1", "Item p1"),
            ("p2", "Item p2"),
        ]
        assert (detail.in_my_drive, detail.ancestors_truncated) == (True, False)

    async def test_a_breadcrumb_stops_at_its_depth_and_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(files_service, "WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH", 2)
        tree = self._tree({"f1": ["p4"], "p4": ["p3"], "p3": ["p2"], "p2": ["p1"], "p1": ["R"]})
        client = MagicMock(get_file_metadata=tree)
        with _door(client):
            detail = await files_service.read_file(USER, "f1")

        assert [item.id for item in detail.ancestors] == ["p3", "p4"]
        assert (detail.in_my_drive, detail.ancestors_truncated) == (False, True)
        # The file, two folders, and My Drive's own id: never the rest of the tree.
        assert tree.await_count == 4

    async def test_a_file_shared_with_me_has_no_trail_in_my_drive(self) -> None:
        client = MagicMock(get_file_metadata=self._tree({"f1": []}))
        with _door(client):
            detail = await files_service.read_file(USER, "f1")

        assert (detail.ancestors, detail.in_my_drive, detail.ancestors_truncated) == (
            [],
            False,
            False,
        )


class TestTheDownload:
    async def test_a_file_is_read_with_its_listed_size_under_the_ceiling(self) -> None:
        client = MagicMock(
            get_file_metadata=AsyncMock(
                return_value=_file("p1", "application/pdf", name="Budget.pdf", size="5")
            ),
            get_file_content=AsyncMock(return_value=b"%PDF-"),
        )
        with _door(client):
            got = await files_service.download_file(USER, DownloadQuery(id="p1"))

        client.get_file_content.assert_awaited_once_with(
            "p1", max_size_bytes=settings.workbench_download_max_bytes, known_size=5
        )
        assert (got.data, got.filename, got.mime_type) == (
            b"%PDF-",
            "Budget.pdf",
            "application/pdf",
        )

    async def test_a_file_past_the_ceiling_is_refused_before_it_is_read(self) -> None:
        listed = settings.workbench_download_max_bytes + 1
        client = MagicMock(
            get_file_metadata=AsyncMock(
                return_value=_file("p1", "application/pdf", size=str(listed))
            ),
            get_file_content=AsyncMock(),
        )
        with _door(client), pytest.raises(BaseAPIException) as caught:
            await files_service.download_file(USER, DownloadQuery(id="p1"))

        assert caught.value.detail == {
            "code": "too_large",
            "max_bytes": settings.workbench_download_max_bytes,
        }
        client.get_file_content.assert_not_awaited()

    @pytest.mark.parametrize(
        ("mime", "asked", "sent", "name"),
        [
            (DOC, "docx", DOCX, "Item g1.docx"),
            (DOC, None, "application/pdf", "Item g1.pdf"),
            (SHEET, "xlsx", XLSX, "Item g1.xlsx"),
            (SLIDES, "pptx", PPTX, "Item g1.pptx"),
            (SLIDES, "pdf", "application/pdf", "Item g1.pdf"),
        ],
    )
    async def test_a_google_document_is_exported_to_the_format_asked(
        self, mime: str, asked: str | None, sent: str, name: str
    ) -> None:
        client = MagicMock(
            get_file_metadata=AsyncMock(return_value=_file("g1", mime)),
            export_google_doc=AsyncMock(return_value=b"exported"),
        )
        with _door(client):
            got = await files_service.download_file(USER, DownloadQuery(id="g1", format=asked))

        client.export_google_doc.assert_awaited_once_with("g1", sent)
        assert (got.data, got.filename, got.mime_type) == (b"exported", name, sent)

    @pytest.mark.parametrize(
        ("mime", "asked"),
        [(SHEET, "docx"), (FORM, None), (FOLDER, None), (SHORTCUT, None), ("image/png", "pdf")],
    )
    async def test_what_a_file_cannot_become_is_refused_unsent(
        self, mime: str, asked: str | None
    ) -> None:
        client = MagicMock(
            get_file_metadata=AsyncMock(return_value=_file("x1", mime, size="3")),
            export_google_doc=AsyncMock(),
            get_file_content=AsyncMock(),
        )
        with _door(client), pytest.raises(BaseAPIException) as caught:
            await files_service.download_file(USER, DownloadQuery(id="x1", format=asked))

        assert _refused(caught) == "not_supported_by_provider"
        client.export_google_doc.assert_not_awaited()
        client.get_file_content.assert_not_awaited()

    async def test_an_export_past_the_ceiling_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "workbench_download_max_bytes", 4)
        client = MagicMock(
            get_file_metadata=AsyncMock(return_value=_file("g1", DOC)),
            export_google_doc=AsyncMock(return_value=b"12345"),
        )
        with _door(client), pytest.raises(BaseAPIException) as caught:
            await files_service.download_file(USER, DownloadQuery(id="g1"))

        assert caught.value.detail == {"code": "too_large", "max_bytes": 4}

    async def test_one_download_at_a_time_per_account(self) -> None:
        held: list[Any] = []

        @contextlib.asynccontextmanager
        async def claim(user_id: Any) -> AsyncIterator[None]:
            held.append(user_id)
            yield

        client = MagicMock(
            get_file_metadata=AsyncMock(return_value=_file("p1", "application/pdf", size="1")),
            get_file_content=AsyncMock(return_value=b"x"),
        )
        with _door(client), patch.object(files_service, "one_download", claim):
            await files_service.download_file(USER, DownloadQuery(id="p1"))

        assert held == [USER]


class TestTheTrash:
    async def test_each_file_is_answered(self) -> None:
        gone = ConnectorAPIError(connector_type="google_drive", status_code=404, detail="x")
        client = MagicMock(delete_file=AsyncMock(side_effect=[True, gone]))
        with _door(client):
            outcome = await files_service.trash_files(
                USER, FileSelection(file_ids=["f1", "f2", "f1"])
            )

        assert outcome.done == ["f1"]
        assert [(item.id, item.status) for item in outcome.failed] == [("f2", "not_found")]

    def test_a_selection_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            FileSelection(file_ids=[])
        with pytest.raises(ValidationError):
            FileSelection(file_ids=[f"f{i}" for i in range(settings.workbench_bulk_max_items + 1)])
