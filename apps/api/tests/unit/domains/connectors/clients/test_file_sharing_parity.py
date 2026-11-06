"""Who a file is shared with, on Google Drive and OneDrive — one contract (ADR-369, lot 6).

Both drives answer a person's access and a link anyone can follow, in the same words: a person
reads or writes, and an owner stays. A person's access is told to them by the drive. Drive names
a link's address on the file, Graph on the permission; both come back as one ``url``.
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

from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "https://www.googleapis.com/drive/v3"


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

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, str(request.url), body))
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
    OWNER = {"id": "p0", "type": "user", "role": "owner", "emailAddress": "me@x.org"}
    READER = {
        "id": "p1",
        "type": "user",
        "role": "reader",
        "emailAddress": "ana@x.org",
        "displayName": "Ana",
    }
    COMMENTER = {"id": "p2", "type": "user", "role": "commenter", "emailAddress": "bob@x.org"}
    TEAM = {"id": "p3", "type": "domain", "role": "writer", "displayName": "x.org"}
    LINK = {"id": "anyoneWithLink", "type": "anyone", "role": "reader"}

    @pytest.fixture
    def client(self) -> GoogleDriveClient:
        return GoogleDriveClient(uuid4(), _credentials(), MagicMock())

    def _listing(self, *permissions: dict[str, Any]) -> _Recorder:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/permissions"):
                return httpx.Response(200, json={"permissions": list(permissions)})
            return httpx.Response(200, json={"id": "f1", "webViewLink": "https://d.example/f1"})

        return _Recorder(answer)

    async def test_who_reads_and_who_writes(self, client: GoogleDriveClient) -> None:
        recorder = self._listing(self.OWNER, self.READER, self.COMMENTER, self.TEAM)

        sharing = await _drive(client, recorder, lambda: client.read_sharing("f1"))

        assert sharing == {
            "people": [
                {"id": "p0", "email": "me@x.org", "name": None, "role": "owner"},
                {"id": "p1", "email": "ana@x.org", "name": "Ana", "role": "reader"},
                {"id": "p2", "email": "bob@x.org", "name": None, "role": "reader"},
                {"id": "p3", "email": None, "name": "x.org", "role": "writer"},
            ],
            "link": None,
        }
        assert "supportsAllDrives=true" in recorder.calls[0][1]
        assert [call[0] for call in recorder.calls] == ["GET"]

    async def test_a_link_anyone_can_follow_comes_back_with_its_address(
        self, client: GoogleDriveClient
    ) -> None:
        recorder = self._listing(self.OWNER, self.LINK)

        sharing = await _drive(client, recorder, lambda: client.read_sharing("f1"))

        assert sharing["link"] == {"id": "anyoneWithLink", "url": "https://d.example/f1"}
        assert len(sharing["people"]) == 1

    async def test_a_person_is_told_by_the_drive(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json=self.READER))

        await _drive(client, recorder, lambda: client.share_with("f1", "ana@x.org", "writer"))

        method, url, body = recorder.calls[0]
        assert method == "POST"
        assert url.startswith(f"{DRIVE}/files/f1/permissions?")
        assert "sendNotificationEmail=true" in url
        assert body == {"type": "user", "role": "writer", "emailAddress": "ana@x.org"}

    async def test_a_link_is_opened_to_anyone_with_it(self, client: GoogleDriveClient) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json=self.LINK)
            return httpx.Response(200, json={"id": "f1", "webViewLink": "https://d.example/f1"})

        recorder = _Recorder(answer)

        link = await _drive(client, recorder, lambda: client.open_link("f1"))

        assert link == {"id": "anyoneWithLink", "url": "https://d.example/f1"}
        assert recorder.calls[0][2] == {"type": "anyone", "role": "reader"}

    async def test_an_access_is_taken_back(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.remove_share("f1", "p1"))

        method, url, _body = recorder.calls[0]
        assert method == "DELETE"
        assert url.startswith(f"{DRIVE}/files/f1/permissions/p1")

    async def test_an_id_never_reshapes_the_address(self, client: GoogleDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.remove_share("f1", "a/../b"))

        assert "/permissions/a%2F..%2Fb" in recorder.calls[0][1]


class TestOneDrive:
    OWNER = {
        "id": "p0",
        "roles": ["owner"],
        "grantedToV2": {"user": {"displayName": "Me", "email": "me@x.org"}},
    }
    WRITER = {
        "id": "p1",
        "roles": ["write"],
        "grantedToV2": {"user": {"displayName": "Ana", "email": "ana@x.org"}},
    }
    READER = {
        "id": "p2",
        "roles": ["read"],
        "grantedToIdentitiesV2": [{"user": {"displayName": "Bob"}}],
    }
    LINK = {
        "id": "l1",
        "roles": ["read"],
        "link": {"scope": "anonymous", "type": "view", "webUrl": "https://1drv.ms/x"},
    }
    INNER_LINK = {
        "id": "l2",
        "roles": ["read"],
        "link": {"scope": "organization", "type": "view", "webUrl": "https://corp/x"},
    }

    @pytest.fixture
    def client(self) -> MicrosoftOneDriveClient:
        return MicrosoftOneDriveClient(uuid4(), _credentials(), MagicMock())

    async def test_who_reads_and_who_writes(self, client: MicrosoftOneDriveClient) -> None:
        answer = {"value": [self.OWNER, self.WRITER, self.READER]}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        sharing = await _drive(client, recorder, lambda: client.read_sharing("f1"))

        assert sharing == {
            "people": [
                {"id": "p0", "email": "me@x.org", "name": "Me", "role": "owner"},
                {"id": "p1", "email": "ana@x.org", "name": "Ana", "role": "writer"},
                {"id": "p2", "email": None, "name": "Bob", "role": "reader"},
            ],
            "link": None,
        }
        assert recorder.calls[0][1].startswith(f"{GRAPH}/me/drive/items/f1/permissions")

    async def test_a_link_anyone_can_follow_comes_back_with_its_address(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        answer = {"value": [self.OWNER, self.LINK]}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        sharing = await _drive(client, recorder, lambda: client.read_sharing("f1"))

        assert sharing["link"] == {"id": "l1", "url": "https://1drv.ms/x"}
        assert len(sharing["people"]) == 1

    async def test_a_link_inside_an_organisation_is_no_link_for_anyone(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        answer = {"value": [self.INNER_LINK]}
        recorder = _Recorder(lambda request: httpx.Response(200, json=answer))

        sharing = await _drive(client, recorder, lambda: client.read_sharing("f1"))

        assert sharing == {"people": [], "link": None}

    async def test_a_person_is_told_by_the_drive(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": [self.WRITER]}))

        await _drive(client, recorder, lambda: client.share_with("f1", "ana@x.org", "writer"))

        method, url, body = recorder.calls[0]
        assert (method, url) == ("POST", f"{GRAPH}/me/drive/items/f1/invite")
        assert body == {
            "recipients": [{"email": "ana@x.org"}],
            "roles": ["write"],
            "requireSignIn": True,
            "sendInvitation": True,
        }

    async def test_a_reader_stays_a_reader(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"value": []}))

        await _drive(client, recorder, lambda: client.share_with("f1", "ana@x.org", "reader"))

        assert recorder.calls[0][2]["roles"] == ["read"]

    async def test_a_link_is_opened_to_anyone_with_it(
        self, client: MicrosoftOneDriveClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(201, json=self.LINK))

        link = await _drive(client, recorder, lambda: client.open_link("f1"))

        assert link == {"id": "l1", "url": "https://1drv.ms/x"}
        method, url, body = recorder.calls[0]
        assert (method, url) == ("POST", f"{GRAPH}/me/drive/items/f1/createLink")
        assert body == {"type": "view", "scope": "anonymous"}

    async def test_an_access_is_taken_back(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.remove_share("f1", "p1"))

        assert recorder.calls[0][:2] == ("DELETE", f"{GRAPH}/me/drive/items/f1/permissions/p1")

    async def test_an_id_never_reshapes_the_address(self, client: MicrosoftOneDriveClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.remove_share("f1", "a/../b"))

        assert "/permissions/a%2F..%2Fb" in recorder.calls[0][1]
