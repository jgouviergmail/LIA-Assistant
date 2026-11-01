"""One page at a time, with a token, for tasks and Graph contacts (ADR-369).

The « Tools » lists page with a cursor (``next_page_token``). Google Tasks pages
with ``pageToken``; Graph with ``@odata.nextLink`` — a full URL. A URL handed to
the browser and sent back would be a request the server makes to wherever the
browser says (SSRF), so the token carries only the skip VALUE, and the client
rebuilds the request on its own base URL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.microsoft_tasks_client import MicrosoftTasksClient
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_GRAPH = "https://graph.microsoft.com/v1.0"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
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


class TestTheGraphToken:
    @pytest.mark.parametrize(
        ("link", "token"),
        [
            (f"{_GRAPH}/me/contacts?$top=25&$skip=25", "$skip=25"),
            (f"{_GRAPH}/me/contacts?%24top=25&%24skiptoken=Abc%2B1%3D", "$skiptoken=Abc+1="),
            (None, None),
            (f"{_GRAPH}/me/contacts?$deltatoken=x", None),
        ],
    )
    def test_only_the_skip_value_leaves_the_server(
        self, link: str | None, token: str | None
    ) -> None:
        assert graph_page_token(link) == token

    def test_a_token_becomes_the_parameter_it_names(self) -> None:
        assert graph_page_params("$skiptoken=Abc+1=") == {"$skiptoken": "Abc+1="}
        assert graph_page_params(None) == {}

    @pytest.mark.parametrize(
        "forged",
        [
            "https://attacker.example/steal",
            "$filter=1 eq 1",
            "$skip=",
            "skip=25",
            "$skiptoken=a b",
            "$skiptoken=" + "x" * 5000,
        ],
    )
    def test_a_forged_token_is_refused(self, forged: str) -> None:
        with pytest.raises(ValueError):
            graph_page_params(forged)


class TestGoogleTasks:
    async def test_the_next_page_is_asked_and_its_token_published(self) -> None:
        client = GoogleTasksClient(uuid4(), _credentials(), MagicMock())
        recorder = _Recorder(
            lambda request: httpx.Response(
                200, json={"items": [{"id": "t3"}], "nextPageToken": "page-3"}
            )
        )

        page = await _drive(
            client, recorder, lambda: client.list_tasks("@default", page_token="page-2")
        )

        assert recorder.requests[0].url.params["pageToken"] == "page-2"
        assert page["next_page_token"] == "page-3"
        assert page["items"] == [{"id": "t3"}]

    async def test_the_last_page_publishes_no_token(self) -> None:
        client = GoogleTasksClient(uuid4(), _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"items": []}))
        page = await _drive(client, recorder, lambda: client.list_tasks("@default"))
        assert page["next_page_token"] is None


class TestMicrosoftTasks:
    async def test_the_skip_is_rebuilt_on_the_clients_own_url(self) -> None:
        client = MicrosoftTasksClient(uuid4(), _credentials(), MagicMock())

        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "t26", "title": "x", "status": "notStarted"}],
                    "@odata.nextLink": f"{_GRAPH}/me/todo/lists/list-1/tasks?$top=25&$skip=50",
                },
            )

        recorder = _Recorder(answer)
        with patch.object(client, "_resolve_list_id", AsyncMock(return_value="list-1")):
            page = await _drive(
                client, recorder, lambda: client.list_tasks("list-1", page_token="$skip=25")
            )

        sent = recorder.requests[0].url
        assert sent.host == "graph.microsoft.com"
        assert sent.params["$skip"] == "25"
        assert sent.params["$filter"] == "status ne 'completed'"
        assert page["next_page_token"] == "$skip=50"


class TestMicrosoftContacts:
    async def test_one_page_and_its_token(self) -> None:
        client = MicrosoftContactsClient(uuid4(), _credentials(), MagicMock())

        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "c26", "displayName": "Zoé"}],
                    "@odata.nextLink": f"{_GRAPH}/me/contacts?$top=25&$skip=50",
                },
            )

        recorder = _Recorder(answer)
        page = await _drive(
            client, recorder, lambda: client.list_connections(page_size=25, page_token="$skip=25")
        )

        assert len(recorder.requests) == 1, "one page per call: the cursor is the caller's"
        assert recorder.requests[0].url.params["$skip"] == "25"
        assert page["next_page_token"] == "$skip=50"
        assert [c["resourceName"] for c in page["connections"]] == ["people/c26"]
