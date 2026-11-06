"""Organising a drive, on Google Drive and OneDrive — one contract (ADR-369, lot 6).

A new folder, a rename, a move, a copy. Drive keeps several items under one name; Graph
refuses one with a conflict, said as a name taken. A move on Drive names the parents it
leaves. A copy on Graph is the provider's own work, answered at once and finished later:
the contract says so by answering no item, never by waiting.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME, ONEDRIVE_REFUSED_NAME_CHARACTERS
from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.domains.connectors.clients.files_management import (
    FileNameRefusedError,
    FileNameTakenError,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOADS = "https://www.googleapis.com/upload/drive/v3"


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
        self.headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        raw = request.content
        is_json = request.headers.get("content-type") == "application/json"
        body = json.loads(raw) if raw and is_json else raw or None
        self.calls.append((request.method, str(request.url), body))
        self.headers.append(request.headers)
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


class TestGoogleDrive:
    @pytest.fixture
    def client(self) -> Iterator[GoogleDriveClient]:
        yield GoogleDriveClient(uuid4(), _credentials(), MagicMock())

    @staticmethod
    def _revised(revision: str = "rev-1") -> _Recorder:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json={"headRevisionId": revision})
            return httpx.Response(200, json={"id": "f1", "headRevisionId": "rev-2"})

        return _Recorder(answer)

    @staticmethod
    def _replace(client: GoogleDriveClient) -> Callable[[], Any]:
        return lambda: client.replace_content("f1", b"new", "text/plain", "rev-1")

    async def test_a_file_is_replaced_on_the_revision_it_was_read_at(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = self._revised()

        written = await _drive(client, recorder, self._replace(client))

        checking, sending = recorder.calls
        assert checking[0] == "GET"
        assert "headRevisionId" in checking[1]
        assert sending[0] == "PATCH"
        assert sending[1].startswith(f"{UPLOADS}/files/f1?")
        assert "uploadType=media" in sending[1]
        assert sending[2] == b"new"
        assert recorder.headers[1]["Content-Type"] == "text/plain"
        assert written["id"] == "f1"

    async def test_a_revision_that_moved_refuses_before_a_byte_leaves(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = self._revised("rev-9")

        with pytest.raises(OfficeContentRefusedError) as refused:
            await _drive(client, recorder, self._replace(client))

        assert refused.value.refusal is OfficeRefusal.CHANGED
        assert [call[0] for call in recorder.calls] == ["GET"]

    async def test_a_replacement_whose_answer_is_lost_is_never_sent_twice(
        self, client: GoogleDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json={"headRevisionId": "rev-1"})
            raise httpx.ReadTimeout("lost")

        recorder = _Recorder(answer)

        with pytest.raises(ExternalServiceError):
            await _drive(client, recorder, self._replace(client))

        assert [call[0] for call in recorder.calls] == ["GET", "PATCH"]

    async def test_a_folder_is_created_where_it_is_asked(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "d1"}))

        made = await _drive(client, recorder, lambda: client.create_folder("Trips", "p1"))

        assert made["id"] == "d1"
        method, url, body = recorder.calls[0]
        assert method == "POST"
        assert url.startswith(f"{DRIVE}/files?")
        assert body == {"name": "Trips", "mimeType": GOOGLE_DRIVE_FOLDER_MIME, "parents": ["p1"]}

    async def test_a_rename_changes_the_name_alone(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "f1"}))

        await _drive(client, recorder, lambda: client.rename_file("f1", "Notes.txt"))

        method, url, body = recorder.calls[0]
        assert (method, body) == ("PATCH", {"name": "Notes.txt"})
        assert url.startswith(f"{DRIVE}/files/f1")

    async def test_a_move_names_the_parents_it_leaves(self, client: GoogleDriveClient) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json={"id": "f1", "parents": ["a", "b"]})
            return httpx.Response(200, json={"id": "f1", "parents": ["c"]})

        recorder = _Recorder(answer)

        await _drive(client, recorder, lambda: client.move_file("f1", "c"))

        method, url, _body = recorder.calls[-1]
        assert method == "PATCH"
        assert "addParents=c" in url
        assert "removeParents=a%2Cb" in url

    async def test_a_move_to_where_it_sits_leaves_nothing(self, client: GoogleDriveClient) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json={"id": "f1", "parents": ["a", "b"]})
            return httpx.Response(200, json={"id": "f1", "parents": ["a"]})

        recorder = _Recorder(answer)

        await _drive(client, recorder, lambda: client.move_file("f1", "a"))

        _method, url, _body = recorder.calls[-1]
        assert "addParents=a" in url
        assert "removeParents=b" in url
        assert "removeParents=a" not in url

    async def test_a_move_to_the_top_it_already_sits_at_keeps_it_there(
        self, client: GoogleDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and "/files/root" in str(request.url):
                return httpx.Response(200, json={"id": "top"})
            if request.method == "GET":
                return httpx.Response(200, json={"id": "f1", "parents": ["top"]})
            return httpx.Response(200, json={"id": "f1", "parents": ["top"]})

        recorder = _Recorder(answer)

        await _drive(client, recorder, lambda: client.move_file("f1", "root"))

        _method, url, _body = recorder.calls[-1]
        assert "addParents=top" in url
        assert "removeParents" not in url

    @pytest.mark.parametrize(
        ("view", "term", "order"),
        [
            ("recent", "mimeType+%21%3D", "viewedByMeTime+desc"),
            ("starred", "starred+%3D+true", "folder%2Cname"),
            ("shared", "sharedWithMe+%3D+true", "sharedWithMeTime+desc"),
        ],
    )
    async def test_a_view_asks_drive_what_it_holds(
        self, client: GoogleDriveClient, view: str, term: str, order: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"files": [{"id": "f1"}]}))

        page = await _drive(
            client,
            recorder,
            lambda: client.list_view(view, max_results=5, page_token="p2", fields=["id"]),
        )

        assert page["files"] == [{"id": "f1"}]
        _method, url, _body = recorder.calls[0]
        assert url.startswith(f"{DRIVE}/files?")
        assert term in url
        assert "trashed+%3D+false" in url
        assert f"orderBy={order}" in url
        assert "pageToken=p2" in url
        assert "pageSize=5" in url

    async def test_the_trash_shows_what_was_put_there_not_what_it_held(
        self, client: GoogleDriveClient
    ) -> None:
        kept = {"id": "f1", "explicitlyTrashed": True}
        held = {"id": "f2", "explicitlyTrashed": False}
        recorder = _Recorder(lambda request: httpx.Response(200, json={"files": [kept, held]}))

        page = await _drive(
            client,
            recorder,
            lambda: client.list_view("trash", max_results=5, page_token=None, fields=["id"]),
        )

        assert [item["id"] for item in page["files"]] == ["f1"]
        url = recorder.calls[0][1]
        assert "trashed+%3D+true" in url
        assert "explicitlyTrashed" in url

    async def test_a_restore_takes_it_out_of_the_trash(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "f1"}))

        await _drive(client, recorder, lambda: client.restore_file("f1"))

        method, url, body = recorder.calls[0]
        assert (method, body) == ("PATCH", {"trashed": False})
        assert url.startswith(f"{DRIVE}/files/f1")

    async def test_a_file_deleted_for_good_goes_by_a_delete(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.delete_file_forever("f1"))

        method, url, _body = recorder.calls[0]
        assert method == "DELETE"
        assert url.startswith(f"{DRIVE}/files/f1")

    async def test_the_trash_is_emptied_in_one_call(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.empty_trash())

        assert recorder.calls[0][:2] == ("DELETE", f"{DRIVE}/files/trash")

    async def test_the_quota_says_what_is_used_of_what(self, client: GoogleDriveClient) -> None:
        answer = {"storageQuota": {"usage": "3", "limit": "10"}}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        quota = await _drive(client, recorder, lambda: client.storage_quota())

        assert quota == {"used": 3, "total": 10}
        assert recorder.calls[0][1].startswith(f"{DRIVE}/about?")
        assert "storageQuota" in recorder.calls[0][1]

    async def test_an_unlimited_account_has_no_total(self, client: GoogleDriveClient) -> None:
        answer = {"storageQuota": {"usage": "3"}}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        quota = await _drive(client, recorder, lambda: client.storage_quota())

        assert quota == {"used": 3, "total": None}

    async def test_a_shared_drive_is_listed_as_a_folder(self, client: GoogleDriveClient) -> None:
        answer = {"drives": [{"id": "s1", "name": "Team"}], "nextPageToken": "n"}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        page = await _drive(
            client,
            recorder,
            lambda: client.list_view("drives", max_results=5, page_token="p", fields=["id"]),
        )

        assert page == {
            "files": [{"id": "s1", "name": "Team", "mimeType": GOOGLE_DRIVE_FOLDER_MIME}],
            "nextPageToken": "n",
        }
        url = recorder.calls[0][1]
        assert url.startswith(f"{DRIVE}/drives?")
        assert "pageToken=p" in url

    @pytest.mark.parametrize(
        "act",
        [
            lambda client: client.list_files("d1"),
            lambda client: client.search_files("budget"),
            lambda client: client.get_file_metadata("f1"),
            lambda client: client.rename_file("f1", "x"),
            lambda client: client.delete_file("f1"),
            lambda client: client.delete_file_forever("f1"),
            lambda client: client.restore_file("f1"),
            lambda client: client.set_starred("f1", True),
            lambda client: client.create_folder("x", "d1"),
            lambda client: client.copy_file("f1"),
        ],
    )
    async def test_every_call_reaches_a_shared_drive_s_items(
        self, client: GoogleDriveClient, act: Callable[[GoogleDriveClient], Any]
    ) -> None:
        """Drive answers 404 for such an item to a call that does not say it can read them."""
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "f1", "files": []}))

        await _drive(client, recorder, lambda: act(client))

        assert all("supportsAllDrives=true" in call[1] for call in recorder.calls)

    @pytest.mark.parametrize(
        "act",
        [
            lambda client: client.list_files("d1"),
            lambda client: client.search_files("budget"),
        ],
    )
    async def test_every_listing_holds_a_shared_drive_s_items(
        self, client: GoogleDriveClient, act: Callable[[GoogleDriveClient], Any]
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"files": []}))

        await _drive(client, recorder, lambda: act(client))

        assert "includeItemsFromAllDrives=true" in recorder.calls[0][1]

    async def test_a_star_changes_the_star_alone(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "f1"}))

        await _drive(client, recorder, lambda: client.set_starred("f1", True))

        method, url, body = recorder.calls[0]
        assert method == "PATCH"
        assert url.startswith(f"{DRIVE}/files/f1")
        assert "starred" in url
        assert body == {"starred": True}

    def _uploading(self, *, session: str = f"{UPLOADS}/files?upload_id=s1") -> _Recorder:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, headers={"Location": session})
            return httpx.Response(200, json={"id": "u1", "name": "Notes.txt"})

        return _Recorder(answer)

    async def test_a_file_goes_through_a_session_of_its_own(
        self, client: GoogleDriveClient
    ) -> None:
        """Drive keeps one-shot bodies for 5 MB; a session takes any size the page accepts."""
        recorder = self._uploading()

        item = await _drive(
            client, recorder, lambda: client.upload_file("Notes.txt", b"data", "text/plain", "d1")
        )

        assert item["id"] == "u1"
        opening, sending = recorder.calls
        assert opening[0] == "POST"
        assert opening[1].startswith(f"{UPLOADS}/files?")
        assert "uploadType=resumable" in opening[1]
        assert opening[2] == {"name": "Notes.txt", "parents": ["d1"]}
        assert recorder.headers[0]["X-Upload-Content-Length"] == "4"
        assert recorder.headers[0]["X-Upload-Content-Type"] == "text/plain"
        assert sending == ("PUT", f"{UPLOADS}/files?upload_id=s1", b"data")
        assert recorder.headers[1]["Content-Type"] == "text/plain"

    async def test_the_top_of_the_drive_takes_a_file(self, client: GoogleDriveClient) -> None:
        recorder = self._uploading()

        await _drive(client, recorder, lambda: client.upload_file("a", b"x", "text/plain"))

        assert recorder.calls[0][2]["parents"] == ["root"]

    async def test_a_session_elsewhere_never_receives_the_token(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = self._uploading(session="https://elsewhere.example/upload")

        with pytest.raises(ConnectorAPIError):
            await _drive(client, recorder, lambda: client.upload_file("a", b"x", "text/plain"))

        assert [call[0] for call in recorder.calls] == ["POST"]

    async def test_an_answer_lost_on_the_bytes_is_never_sent_twice(
        self, client: GoogleDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, headers={"Location": f"{UPLOADS}/files?upload_id=s1"})
            raise httpx.ReadTimeout("lost")

        recorder = _Recorder(answer)

        with pytest.raises(ExternalServiceError):
            await _drive(client, recorder, lambda: client.upload_file("a", b"x", "text/plain"))

        assert [call[0] for call in recorder.calls] == ["POST", "PUT"]

    async def test_a_copy_answers_the_new_item(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "copy"}))

        made = await _drive(client, recorder, lambda: client.copy_file("f1", "p2"))

        assert made["id"] == "copy"
        method, url, body = recorder.calls[0]
        assert (method, body) == ("POST", {"parents": ["p2"]})
        assert url.startswith(f"{DRIVE}/files/f1/copy")

    async def test_a_copy_beside_the_original_names_no_parent(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "copy"}))

        await _drive(client, recorder, lambda: client.copy_file("f1"))

        assert recorder.calls[0][2] == {}


class TestOneDrive:
    ITEM = {"id": "f1", "name": "Notes.txt", "file": {"mimeType": "text/plain"}}

    @pytest.fixture
    def client(self) -> MicrosoftOneDriveClient:
        return MicrosoftOneDriveClient(uuid4(), _credentials(), MagicMock())

    async def test_a_folder_refuses_a_name_rather_than_rename_itself(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(
            lambda request: httpx.Response(201, json={"id": "d1", "name": "Trips", "folder": {}})
        )

        made = await _drive(client, recorder, lambda: client.create_folder("Trips", "p1"))

        assert made["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME
        assert recorder.calls[0] == (
            "POST",
            f"{GRAPH}/me/drive/items/p1/children",
            {"name": "Trips", "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        )

    async def test_the_top_takes_a_folder_too(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(201, json={"id": "d1", "folder": {}}))

        await _drive(client, recorder, lambda: client.create_folder("Trips"))

        assert recorder.calls[0][1] == f"{GRAPH}/me/drive/root/children"

    async def test_a_name_taken_is_said(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(409, json={"error": {}}))

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.create_folder("Trips"))

    @pytest.mark.parametrize("character", list(ONEDRIVE_REFUSED_NAME_CHARACTERS))
    async def test_a_name_graph_refuses_never_leaves(
        self, client: MicrosoftOneDriveClient, character: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=self.ITEM))
        name = f"Meeting {character} notes"

        with pytest.raises(FileNameRefusedError):
            await _drive(client, recorder, lambda: client.create_folder(name))
        with pytest.raises(FileNameRefusedError):
            await _drive(client, recorder, lambda: client.rename_file("f1", name))
        with pytest.raises(FileNameRefusedError):
            await _drive(client, recorder, lambda: client.copy_file("f1", "p2", name))

        assert recorder.calls == []

    async def test_a_rename_taken_is_said_too(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(409, json={"error": {}}))

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.rename_file("f1", "Notes.txt"))

    async def test_a_rename_changes_the_name_alone(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=self.ITEM))

        await _drive(client, recorder, lambda: client.rename_file("f1", "Notes.txt"))

        assert recorder.calls[0] == (
            "PATCH",
            f"{GRAPH}/me/drive/items/f1",
            {"name": "Notes.txt"},
        )

    async def test_a_move_names_the_new_parent(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=self.ITEM))

        await _drive(client, recorder, lambda: client.move_file("f1", "p2"))

        assert recorder.calls[0] == (
            "PATCH",
            f"{GRAPH}/me/drive/items/f1",
            {"parentReference": {"id": "p2"}},
        )

    async def test_a_move_to_the_top_names_its_real_id(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json={"id": "top", "folder": {}})
            return httpx.Response(200, json=self.ITEM)

        recorder = _Recorder(answer)

        await _drive(client, recorder, lambda: client.move_file("f1", "root"))

        assert recorder.calls[-1][2] == {"parentReference": {"id": "top"}}

    async def test_the_quota_says_what_is_used_of_what(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        answer = {"quota": {"used": 3, "total": 10, "remaining": 7}}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        quota = await _drive(client, recorder, lambda: client.storage_quota())

        assert quota == {"used": 3, "total": 10}
        assert recorder.calls[0][1].startswith(f"{GRAPH}/me/drive?")

    async def test_a_restore_is_graph_s_own_call_and_answers_the_item(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=self.ITEM))

        item = await _drive(client, recorder, lambda: client.restore_file("f1"))

        assert item["id"] == "f1"
        assert recorder.calls[0][:2] == ("POST", f"{GRAPH}/me/drive/items/f1/restore")

    def _uploading(self, *, name_held: bool = False, accepted: int = 201) -> _Recorder:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "PUT":
                return httpx.Response(accepted, json={**self.ITEM, "error": {}})
            return httpx.Response(200 if name_held else 404, json={"id": "taken", "error": {}})

        return _Recorder(answer)

    async def test_a_file_goes_where_it_is_asked_and_refuses_to_replace(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._uploading()

        item = await _drive(
            client, recorder, lambda: client.upload_file("Q3 #1.txt", b"data", "text/plain", "d1")
        )

        assert item["id"] == "f1"
        method, url, body = recorder.calls[-1]
        assert method == "PUT"
        assert url.startswith(f"{GRAPH}/me/drive/items/d1:/Q3%20%231.txt:/content?")
        assert "conflictBehavior=fail" in url
        assert body == b"data"
        assert recorder.headers[-1]["Content-Type"] == "text/plain"

    async def test_the_top_of_the_drive_takes_a_file(self, client: MicrosoftOneDriveClient) -> None:
        recorder = self._uploading()

        await _drive(client, recorder, lambda: client.upload_file("a.txt", b"x", "text/plain"))

        assert recorder.calls[-1][1].startswith(f"{GRAPH}/me/drive/root:/a.txt:/content")

    async def test_a_file_never_replaces_the_one_a_folder_holds(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        """A PUT on a path REPLACES what is there: its own conflict rule is not relied on."""
        recorder = self._uploading(name_held=True)

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.upload_file("a.txt", b"x", "text/plain"))

        assert [call[0] for call in recorder.calls] == ["GET"]

    async def test_a_conflict_on_the_bytes_is_a_name_taken(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._uploading(accepted=409)

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.upload_file("a.txt", b"x", "text/plain"))

    async def test_a_name_graph_refuses_sends_nothing(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._uploading()

        with pytest.raises(FileNameRefusedError):
            await _drive(client, recorder, lambda: client.upload_file("a:b", b"x", "text/plain"))

        assert recorder.calls == []

    async def test_an_answer_lost_on_the_bytes_is_never_sent_twice(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "PUT":
                raise httpx.ReadTimeout("lost")
            return httpx.Response(404, json={"error": {}})

        recorder = _Recorder(answer)

        with pytest.raises(ExternalServiceError):
            await _drive(client, recorder, lambda: client.upload_file("a.txt", b"x", "text/plain"))

        assert [call[0] for call in recorder.calls] == ["GET", "PUT"]

    def _copying(self, *, name_held: bool = False, accepted: int = 202) -> _Recorder:
        """Graph answering a copy: the source, what the folder holds, then the copy itself."""

        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(accepted, json={"error": {}})
            if ":/" in request.url.path:
                return httpx.Response(200 if name_held else 404, json={"id": "taken", "error": {}})
            if request.url.path.endswith("/me/drive/root"):
                return httpx.Response(200, json={"id": "top"})
            return httpx.Response(
                200, json={**self.ITEM, "parentReference": {"id": "p1", "driveId": "D"}}
            )

        return _Recorder(answer)

    async def test_a_copy_onto_a_name_held_never_leaves(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        """Graph would answer 202 and fail later (`nameAlreadyExists`), heard by nobody."""
        recorder = self._copying(name_held=True)

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.copy_file("f1", "p2"))

        assert [call[0] for call in recorder.calls] == ["GET", "GET"]

    async def test_a_copy_beside_the_original_needs_a_name_of_its_own(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._copying(name_held=True)

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.copy_file("f1"))

        assert recorder.calls[1][1].startswith(f"{GRAPH}/me/drive/items/p1:/Notes.txt")

    async def test_the_name_is_read_in_the_folder_the_copy_goes_to(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._copying()

        await _drive(client, recorder, lambda: client.copy_file("f1", "root", "Q3 #1 (final).txt"))

        assert recorder.calls[2][1].startswith(
            f"{GRAPH}/me/drive/items/top:/Q3%20%231%20%28final%29.txt"
        )

    async def test_a_name_refused_on_acceptance_is_said_too(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._copying(accepted=409)

        with pytest.raises(FileNameTakenError):
            await _drive(client, recorder, lambda: client.copy_file("f1", "p2"))

    async def test_a_folder_that_cannot_be_read_stops_the_copy(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if ":/" in request.url.path:
                return httpx.Response(403, json={"error": {}})
            return httpx.Response(
                200, json={**self.ITEM, "parentReference": {"id": "p1", "driveId": "D"}}
            )

        recorder = _Recorder(answer)

        with pytest.raises(ConnectorAPIError):
            await _drive(client, recorder, lambda: client.copy_file("f1", "p2"))

        assert all(call[0] == "GET" for call in recorder.calls)

    async def test_a_copy_is_graph_s_own_work_and_answers_no_item(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._copying()

        made = await _drive(client, recorder, lambda: client.copy_file("f1", "p2"))

        assert made is None
        method, url, body = recorder.calls[-1]
        assert (method, url) == ("POST", f"{GRAPH}/me/drive/items/f1/copy")
        assert body == {"parentReference": {"driveId": "D", "id": "p2"}}

    async def test_a_copy_beside_the_original_stays_in_its_folder(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = self._copying()

        await _drive(client, recorder, lambda: client.copy_file("f1", name="Notes (copy).txt"))

        assert recorder.calls[-1][2] == {
            "parentReference": {"driveId": "D", "id": "p1"},
            "name": "Notes (copy).txt",
        }
