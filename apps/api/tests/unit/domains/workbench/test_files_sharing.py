"""Who a file is shared with, by the person's own hand (ADR-369, lot 6).

The same acts on both drives: read, tell a person, open a link, take an access back. A person
told once is told once, whatever is pressed twice. What the page never offers, the owner's own
access, the route refuses too.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import files_sharing, idempotency
from src.domains.workbench.schemas.files import FileShare, FileShareRemoval
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
KEY = "11111111-1111-4111-8111-111111111111"
SHARING = {
    "people": [
        {"id": "p0", "email": "me@x.org", "name": "Me", "role": "owner"},
        {"id": "p1", "email": "ana@x.org", "name": None, "role": "reader"},
    ],
    "link": {"id": "l1", "url": "https://d.example/f1"},
}
BOTH = [ConnectorType.GOOGLE_DRIVE, ConnectorType.MICROSOFT_ONEDRIVE]


@pytest.fixture(autouse=True)
def _redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_DRIVE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(files_sharing, "open_tool_client", opened)


def _client(**answers: Any) -> MagicMock:
    client = MagicMock(
        read_sharing=AsyncMock(return_value=SHARING),
        share_with=AsyncMock(return_value=None),
        open_link=AsyncMock(return_value=SHARING["link"]),
        remove_share=AsyncMock(return_value=None),
    )
    client.configure_mock(**answers)
    return client


class TestReading:
    @pytest.mark.parametrize("kind", BOTH)
    async def test_it_says_who_reads_and_writes(self, kind: ConnectorType) -> None:
        with _door(_client(), kind):
            sharing = await files_sharing.read_sharing(USER, "f1")

        assert [(person.id, person.role) for person in sharing.people] == [
            ("p0", "owner"),
            ("p1", "reader"),
        ]
        assert sharing.link is not None
        assert sharing.link.url == "https://d.example/f1"

    async def test_a_link_that_is_no_web_address_is_never_shown(self) -> None:
        answer = {**SHARING, "link": {"id": "l1", "url": "javascript:alert(1)"}}

        with _door(_client(read_sharing=AsyncMock(return_value=answer))):
            sharing = await files_sharing.read_sharing(USER, "f1")

        assert sharing.link is not None
        assert sharing.link.url is None


class TestTellingAPerson:
    REQUEST = FileShare(file_id="f1", email="ana@x.org", role="writer", idempotency_key=KEY)

    @pytest.mark.parametrize("kind", BOTH)
    async def test_it_reaches_the_drive(self, kind: ConnectorType) -> None:
        client = _client()

        with _door(client, kind):
            await files_sharing.share_file(USER, self.REQUEST)

        client.share_with.assert_awaited_once_with("f1", "ana@x.org", "writer")

    async def test_a_second_press_tells_nobody_twice(self) -> None:
        client = _client()

        with _door(client):
            await files_sharing.share_file(USER, self.REQUEST)
            with pytest.raises(BaseAPIException):
                await files_sharing.share_file(USER, self.REQUEST)

        client.share_with.assert_awaited_once()

    @pytest.mark.parametrize(
        "fields",
        [
            {"email": "not an address"},
            {"email": "ana@x.org\nbcc@x.org"},
            {"role": "owner"},
            {"file_id": "a b"},
        ],
    )
    def test_what_cannot_be_acted_on_is_refused(self, fields: dict[str, str]) -> None:
        request = {
            "file_id": "f1",
            "email": "ana@x.org",
            "role": "reader",
            "idempotency_key": KEY,
            **fields,
        }

        with pytest.raises(ValidationError):
            FileShare.model_validate(request)


class TestALink:
    @pytest.mark.parametrize("kind", BOTH)
    async def test_it_opens_and_says_its_address(self, kind: ConnectorType) -> None:
        with _door(_client(), kind):
            link = await files_sharing.open_link(USER, "f1")

        assert link.url == "https://d.example/f1"


class TestTakingBack:
    REMOVAL = FileShareRemoval(file_id="f1", permission_id="p1")

    async def test_it_reaches_the_drive(self) -> None:
        client = _client()

        with _door(client):
            await files_sharing.remove_share(USER, self.REMOVAL)

        client.remove_share.assert_awaited_once_with("f1", "p1")

    async def test_the_owner_s_own_access_is_never_taken_back(self) -> None:
        client = _client()

        with _door(client), pytest.raises(BaseAPIException) as caught:
            await files_sharing.remove_share(
                USER, FileShareRemoval(file_id="f1", permission_id="p0")
            )

        assert caught.value.detail["code"] == "invalid_request"
        client.remove_share.assert_not_awaited()
