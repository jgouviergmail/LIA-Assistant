"""OneDrive speaks the files contract (ADR-369, lot 6, A4).

Google's words are the vocabulary the normalisers speak, as for the calendars: an item has
a ``mimeType``, a folder Drive's folder type, ``parents``, ``owners``. A listing answers
``files`` and ``nextPageToken``; the token carries only Graph's skip value, never its link.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.normalizers.onedrive_normalizer import normalize_drive_item
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

GRAPH = "https://graph.microsoft.com/v1.0"
FILE = {
    "id": "f1",
    "name": "Budget.xlsx",
    "size": 2048,
    "file": {"mimeType": "application/vnd.ms-excel"},
    "webUrl": "https://onedrive.live.com/edit?id=f1",
    "lastModifiedDateTime": "2026-11-02T09:00:00Z",
    "createdDateTime": "2026-11-01T09:00:00Z",
    "parentReference": {"id": "p1", "driveId": "d1"},
    "createdBy": {"user": {"displayName": "Ana Lima"}},
    "description": "The budget",
}
FOLDER = {
    "id": "d1",
    "name": "Projects",
    "size": 4096,
    "folder": {"childCount": 3},
    "webUrl": "https://onedrive.live.com/?id=d1",
    "lastModifiedDateTime": "2026-11-02T09:00:00Z",
    "parentReference": {"id": "p1"},
}


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Any]] = []
        self.raw_bodies = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            body = request.content if self.raw_bodies else json.loads(request.content)
        self.calls.append((request.method, str(request.url), body))
        return self.answer(request)


async def _drive(
    client: Any, recorder: _Recorder, call: Callable[[], Any], *, raw_bodies: bool = False
) -> Any:
    recorder.raw_bodies = raw_bodies
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


@pytest.fixture
def client() -> MicrosoftOneDriveClient:
    return MicrosoftOneDriveClient(uuid4(), _credentials(), MagicMock())


class TestWhereAnItemLives:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/drive/root:/Documents/Factures", "Documents/Factures"),
            ("/drives/abc/root:/Mes%20photos/%C3%89t%C3%A9", "Mes photos/Été"),
            ("/drive/root:", ""),
        ],
    )
    def test_its_folders_are_read_from_the_top_of_the_drive(self, path: str, expected: str) -> None:
        item = {**FILE, "parentReference": {"id": "p1", "path": path}}

        assert normalize_drive_item(item)["folderPath"] == expected

    def test_a_feed_entry_says_none_and_none_is_claimed(self) -> None:
        assert normalize_drive_item(FILE)["folderPath"] is None

    async def test_a_listed_item_is_read_again_for_its_folders(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        located = {**FILE, "parentReference": {"id": "p1", "path": "/drive/root:/Docs"}}
        recorder = _Recorder(lambda request: httpx.Response(200, json=located))

        path = await _drive(client, recorder, lambda: client.folder_path({"id": "f1"}, {}))

        assert path == "Docs"
        assert "/me/drive/items/f1" in recorder.calls[0][1]


class TestTheVocabulary:
    def test_an_item_says_the_tag_a_write_is_conditioned_on(self) -> None:
        assert normalize_drive_item({**FILE, "eTag": "tag-1"})["eTag"] == "tag-1"

    def test_a_file_reads_in_drive_s_words(self) -> None:
        item = normalize_drive_item(FILE)

        assert item["id"] == "f1"
        assert item["mimeType"] == "application/vnd.ms-excel"
        assert item["size"] == 2048
        assert item["modifiedTime"] == "2026-11-02T09:00:00Z"
        assert item["createdTime"] == "2026-11-01T09:00:00Z"
        assert item["webViewLink"] == "https://onedrive.live.com/edit?id=f1"
        assert item["parents"] == ["p1"]
        assert item["owners"] == [{"displayName": "Ana Lima"}]
        assert item["description"] == "The budget"

    def test_a_folder_is_drive_s_folder_and_has_no_size_of_its_own(self) -> None:
        item = normalize_drive_item(FOLDER)

        assert item["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME
        assert "size" not in item

    def test_the_top_of_the_drive_has_no_parent(self) -> None:
        assert normalize_drive_item({"id": "root", "name": "root", "folder": {}})["parents"] == []

    def test_an_item_nobody_typed_is_a_plain_file(self) -> None:
        assert normalize_drive_item({"id": "x", "name": "x"})["mimeType"] == (
            "application/octet-stream"
        )


class TestAFolder:
    async def test_it_lists_its_children_folders_first_with_its_order(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"value": [FILE, FOLDER]}),
        )

        page = await _drive(
            client,
            recorder,
            lambda: client.list_files(
                folder_id="p1", max_results=25, content_type="all", order_by="folder,name"
            ),
        )

        assert [item["id"] for item in page["files"]] == ["d1", "f1"]
        assert page["nextPageToken"] is None
        method, url, _body = recorder.calls[0]
        assert method == "GET"
        assert url.startswith(f"{GRAPH}/me/drive/items/p1/children?")
        assert "orderby=name+asc" in url.replace("%24", "").replace("%20", "+")

    @pytest.mark.parametrize(
        ("drive_order", "graph_order"),
        [
            ("folder,modifiedTime desc", "lastModifiedDateTime+desc"),
            ("folder,quotaBytesUsed desc", "size+desc"),
        ],
    )
    async def test_each_of_drive_s_orders_has_graph_s_word(
        self, client: MicrosoftOneDriveClient, drive_order: str, graph_order: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": []}))

        await _drive(
            client, recorder, lambda: client.list_files(order_by=drive_order, content_type="all")
        )

        assert graph_order in recorder.calls[0][1].replace("%20", "+")

    async def test_the_top_is_named_root(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": []}))

        await _drive(client, recorder, lambda: client.list_files(content_type="all"))

        assert recorder.calls[0][1].startswith(f"{GRAPH}/me/drive/root/children?")

    @pytest.mark.parametrize(
        ("content_type", "expected"),
        [("files_only", ["f1"]), ("folders_only", ["d1"]), ("all", ["d1", "f1"])],
    )
    async def test_a_kind_is_kept_as_drive_keeps_it(
        self, client: MicrosoftOneDriveClient, content_type: str, expected: list[str]
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [FILE, FOLDER]}))

        page = await _drive(client, recorder, lambda: client.list_files(content_type=content_type))

        assert [item["id"] for item in page["files"]] == expected

    async def test_a_page_says_more_follow_by_a_value_never_by_a_link(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        link = f"{GRAPH}/me/drive/root/children?$skiptoken=abc"
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"value": [], "@odata.nextLink": link})
        )

        page = await _drive(client, recorder, lambda: client.list_files())

        assert page["nextPageToken"] == "$skiptoken=abc"

    async def test_the_next_page_is_asked_on_our_own_address(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": []}))

        await _drive(client, recorder, lambda: client.list_files(page_token="$skiptoken=abc"))

        assert "skiptoken=abc" in recorder.calls[0][1]
        assert recorder.calls[0][1].startswith(GRAPH)


class TestASearch:
    async def test_it_asks_the_whole_drive_with_the_words_quoted(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [FILE]}))

        await _drive(
            client,
            recorder,
            lambda: client.search_files(
                "l'été", max_results=25, content_type="all", search_mode="full_text"
            ),
        )

        url = recorder.calls[0][1]
        assert "/me/drive/root/search(q=" in url.replace("%28", "(").replace("%3D", "=")
        assert "l%27%27" in url or "l''" in url

    async def test_no_word_asks_for_everything_graph_refuses_an_empty_query(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [FILE]}))

        page = await _drive(client, recorder, lambda: client.search_files("", content_type="all"))

        assert "q='%2A'" in recorder.calls[0][1].replace("%27", "'")
        assert [item["id"] for item in page["files"]] == ["f1"]

    async def test_a_search_by_name_keeps_what_the_name_holds(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        other = {**FILE, "id": "f2", "name": "Notes.txt"}
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [FILE, other]}))

        page = await _drive(
            client,
            recorder,
            lambda: client.search_files("budget", content_type="all", search_mode="name_only"),
        )

        assert [item["id"] for item in page["files"]] == ["f1"]

    async def test_a_search_of_the_content_keeps_what_graph_found(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        other = {**FILE, "id": "f2", "name": "Notes.txt"}
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [FILE, other]}))

        page = await _drive(
            client,
            recorder,
            lambda: client.search_files("budget", content_type="all", search_mode="full_text"),
        )

        assert [item["id"] for item in page["files"]] == ["f1", "f2"]


class TestWhatChangedLast:
    async def test_it_answers_from_the_window_its_feed_fills(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        with patch(
            "src.domains.connectors.clients.microsoft_onedrive_client.recent_window",
            AsyncMock(return_value=[{"id": "f1"}]),
        ) as window:
            page = await client.recent_files(5)

        assert page == {"files": [{"id": "f1"}]}
        window.assert_awaited_once_with(client, 5)


class TestAWorkbooksHome:
    async def test_it_says_what_kind_of_drive_it_is(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"driveType": "personal"}))

        kind = await _drive(client, recorder, client.drive_type)

        assert kind == "personal"
        assert "/me/drive?%24select=driveType" in recorder.calls[0][1]

    async def test_a_workbook_is_reached_under_its_item(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"cellCount": 1}))

        answer = await _drive(
            client,
            recorder,
            lambda: client.workbook_request(
                "PATCH",
                "a/../b",
                "worksheets/S/range(address='A1:A1')",
                json_data={"values": [["1"]]},
            ),
        )

        method, url, body = recorder.calls[0]
        assert method == "PATCH"
        assert "/me/drive/items/a%2F..%2Fb/workbook/worksheets/S/range" in url
        assert body == {"values": [["1"]]}
        assert answer == {"cellCount": 1}


class TestAFileAsAPdf:
    """Measured on a personal drive, 2026-11-05: a 302 to a pre-authenticated ``svc.ms`` address."""

    ADDRESS = "https://east-mediap.svc.ms/transform/pdf?token=abc"

    def _converting(self, pdf: bytes = b"%PDF-1.7") -> _Recorder:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.host == "graph.microsoft.com":
                return httpx.Response(302, headers={"Location": self.ADDRESS})
            return httpx.Response(200, content=pdf)

        return _Recorder(answer)

    async def test_graph_is_asked_for_it_and_its_address_is_read(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._converting()

        data = await _drive(
            client, recorder, lambda: client.converted_to_pdf("f1", 1024), raw_bodies=True
        )

        assert data == b"%PDF-1.7"
        assert "/me/drive/items/f1/content?format=pdf" in recorder.calls[0][1]
        assert recorder.calls[1][1] == self.ADDRESS

    async def test_nothing_of_the_person_follows_to_that_address(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        seen: list[httpx.Request] = []
        converting = self._converting()

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return converting.answer(request)

        await _drive(
            client, _Recorder(answer), lambda: client.converted_to_pdf("f1", 1024), raw_bodies=True
        )

        assert "Authorization" in seen[0].headers
        assert "Authorization" not in seen[1].headers

    async def test_past_the_ceiling_it_is_none(self, client: MicrosoftOneDriveClient) -> None:
        recorder = self._converting(b"x" * 2048)

        data = await _drive(
            client, recorder, lambda: client.converted_to_pdf("f1", 1024), raw_bodies=True
        )

        assert data is None

    @pytest.mark.parametrize(
        "headers", [{}, {"Location": "http://east.svc.ms/plain"}, {"Location": "/relative"}]
    )
    async def test_an_answer_with_no_safe_address_reads_nothing(
        self, client: MicrosoftOneDriveClient, headers: dict[str, str]
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(302, headers=headers))

        with pytest.raises(ValueError):
            await _drive(
                client, recorder, lambda: client.converted_to_pdf("f1", 1024), raw_bodies=True
            )

        assert len(recorder.calls) == 1

    async def test_a_conversion_graph_refuses_is_its_answer(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(404, json={}))

        with pytest.raises(ConnectorAPIError):
            await _drive(
                client, recorder, lambda: client.converted_to_pdf("f1", 1024), raw_bodies=True
            )

    @pytest.mark.parametrize(
        ("name", "converts"),
        [
            ("Report.docx", True),
            ("REPORT.DOCX", True),
            ("Talk.pptx", True),
            ("Notes.md", True),
            ("Page.html", True),
            ("Budget.xlsx", True),
            ("Scan.pdf", False),
            ("Notes.txt", False),
            ("Data.csv", False),
            ("Data.json", False),
        ],
    )
    def test_what_converts_is_said_by_its_name(self, name: str, converts: bool) -> None:
        assert normalize_drive_item({**FILE, "name": name})["pdfConvertible"] is converts

    def test_a_folder_converts_to_nothing(self) -> None:
        item = {**FOLDER, "name": "Notes.docx"}

        assert normalize_drive_item(item)["pdfConvertible"] is False


class TestReplacingAFile:
    @staticmethod
    def _replace(client: MicrosoftOneDriveClient) -> Callable[[], Any]:
        return lambda: client.replace_content("f1", b"new bytes", "text/x-kind", "tag-1")

    async def test_it_is_conditioned_on_the_tag_it_was_read_at(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={**FILE, "eTag": "tag-2"})

        written = await _drive(client, _Recorder(answer), self._replace(client), raw_bodies=True)

        assert seen[0].method == "PUT"
        assert seen[0].url.path.endswith("/me/drive/items/f1/content")
        assert seen[0].headers["If-Match"] == "tag-1"
        assert seen[0].headers["Content-Type"] == "text/x-kind"
        assert seen[0].content == b"new bytes"
        assert written["eTag"] == "tag-2"

    async def test_the_written_item_speaks_the_files_vocabulary(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={**FILE, "eTag": "tag-2"}))

        written = await _drive(client, recorder, self._replace(client), raw_bodies=True)

        assert written["mimeType"] == "application/vnd.ms-excel"
        assert written["modifiedTime"] == "2026-11-02T09:00:00Z"

    @pytest.mark.parametrize(
        ("status_code", "refusal"),
        [(412, OfficeRefusal.CHANGED), (423, OfficeRefusal.LOCKED)],
    )
    async def test_a_file_someone_else_holds_is_refused_by_its_reason(
        self, client: MicrosoftOneDriveClient, status_code: int, refusal: OfficeRefusal
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(status_code, json={}))

        with pytest.raises(OfficeContentRefusedError) as refused:
            await _drive(client, recorder, self._replace(client), raw_bodies=True)

        assert refused.value.refusal is refusal
        assert len(recorder.calls) == 1

    async def test_an_answer_that_kept_the_old_tag_is_no_write(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"id": "f1", "eTag": "tag-1"})
        )

        with pytest.raises(OfficeContentRefusedError) as refused:
            await _drive(client, recorder, self._replace(client), raw_bodies=True)

        assert refused.value.refusal is OfficeRefusal.CHANGED


class TestOneItem:
    async def test_it_is_read_by_its_id(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=FILE))

        item = await _drive(client, recorder, lambda: client.get_file_metadata("f1"))

        assert item["id"] == "f1"
        assert recorder.calls[0][1].startswith(f"{GRAPH}/me/drive/items/f1")

    async def test_the_top_is_read_as_root(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "top", "folder": {}}))

        item = await _drive(client, recorder, lambda: client.get_file_metadata("root"))

        assert item["id"] == "top"
        assert recorder.calls[0][1].startswith(f"{GRAPH}/me/drive/root")

    async def test_trashing_is_graph_s_delete_which_keeps_it_in_the_recycle_bin(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        done = await _drive(client, recorder, lambda: client.delete_file("f1"))

        assert done is True
        assert recorder.calls == [("DELETE", f"{GRAPH}/me/drive/items/f1", None)]


class TestItsBytes:
    DOWNLOAD = "https://public.dm.files.1drv.com/f1?token=opaque"

    def _answer(self, *, body: bytes = b"content", size: int = 7) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(GRAPH):
                return httpx.Response(
                    200,
                    json={"id": "f1", "size": size, "@microsoft.graph.downloadUrl": self.DOWNLOAD},
                )
            assert "authorization" not in request.headers
            return httpx.Response(200, content=body)

        return answer

    async def test_they_leave_from_the_address_graph_gave_without_the_token(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(self._answer())

        data = await _drive(client, recorder, lambda: client.get_file_content("f1"))

        assert data == b"content"
        assert recorder.calls[-1][1] == self.DOWNLOAD

    async def test_a_listed_size_past_the_ceiling_reads_no_byte(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(self._answer(size=11))

        data = await _drive(
            client, recorder, lambda: client.get_file_content("f1", max_size_bytes=10)
        )

        assert data is None
        assert len(recorder.calls) == 1

    async def test_a_body_past_the_ceiling_stops_there(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(self._answer(body=b"x" * 11, size=3))

        data = await _drive(
            client, recorder, lambda: client.get_file_content("f1", max_size_bytes=10)
        )

        assert data is None

    async def test_what_has_no_bytes_is_refused(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "f1", "size": 1}))

        with pytest.raises(ValueError):
            await _drive(client, recorder, lambda: client.get_file_content("f1"))
