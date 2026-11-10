"""The tasks clients' contract, Google Tasks and Microsoft To Do alike (ADR-369).

Four things the « Tools » section needs, every one of them reaching the
assistant's tools through the same clients (D2):

- an id from a browser or a model is ONE path segment: quoted, and a segment
  the HTTP client would fold away (``.``, ``..`` — httpx removes dot segments,
  measured) names nothing and asks nothing;
- the lists of lists page like the lists of tasks (a cut is never the whole);
- a due date can be REMOVED (``clear_due``), not only replaced;
- editing a completed Google task keeps its completion date (the update is a
  full PUT: a field left out is a field rewritten).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.microsoft_tasks_client import MicrosoftTasksClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_GRAPH = "https://graph.microsoft.com/v1.0"
_HOSTILE = ("a/../../users/@me/lists/x", "x?showDeleted=true", "x#y", "%2e%2e")


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


def _google() -> GoogleTasksClient:
    return GoogleTasksClient(uuid4(), _credentials(), MagicMock())


def _microsoft() -> MicrosoftTasksClient:
    return MicrosoftTasksClient(uuid4(), _credentials(), MagicMock())


def _ok(body: dict[str, Any] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=body if body is not None else {"id": "t1"})


#: Every call of each client that puts a list id or a task id in a path.
_GOOGLE_ACTS: dict[str, Callable[[GoogleTasksClient, str], Any]] = {
    "get_task_list": lambda c, i: c.get_task_list(i),
    "delete_task_list": lambda c, i: c.delete_task_list(i),
    "list_tasks": lambda c, i: c.list_tasks(i),
    "get_task": lambda c, i: c.get_task("l1", i),
    "create_task": lambda c, i: c.create_task(i, title="t"),
    "update_task": lambda c, i: c.update_task("l1", i, title="t"),
    "delete_task": lambda c, i: c.delete_task("l1", i),
}
_MICROSOFT_ACTS: dict[str, Callable[[MicrosoftTasksClient, str], Any]] = {
    "get_task_list": lambda c, i: c.get_task_list(i),
    "delete_task_list": lambda c, i: c.delete_task_list(i),
    "list_tasks": lambda c, i: c.list_tasks(i),
    "get_task": lambda c, i: c.get_task("l1", i),
    "create_task": lambda c, i: c.create_task(i, title="t"),
    "update_task": lambda c, i: c.update_task("l1", i, title="t"),
    "delete_task": lambda c, i: c.delete_task("l1", i),
}


class TestAnIdIsOnePathSegment:
    @pytest.mark.parametrize("act", sorted(_GOOGLE_ACTS))
    @pytest.mark.parametrize("hostile", _HOSTILE)
    async def test_google_quotes_it(self, act: str, hostile: str) -> None:
        client, recorder = _google(), _Recorder(_ok())
        await _drive(client, recorder, lambda: _GOOGLE_ACTS[act](client, hostile))

        path = recorder.requests[0].url.raw_path.decode().split("?")[0]
        assert hostile in [unquote(segment) for segment in path.split("/")]
        assert path.startswith("/tasks/v1/")

    @pytest.mark.parametrize("act", sorted(_MICROSOFT_ACTS))
    @pytest.mark.parametrize("hostile", _HOSTILE)
    async def test_microsoft_quotes_it(self, act: str, hostile: str) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"id": "t1", "value": []}))
        await _drive(client, recorder, lambda: _MICROSOFT_ACTS[act](client, hostile))

        path = recorder.requests[0].url.raw_path.decode().split("?")[0]
        assert hostile in [unquote(segment) for segment in path.split("/")]
        assert path.startswith("/v1.0/me/todo/lists/")

    @pytest.mark.parametrize("act", sorted(_GOOGLE_ACTS))
    @pytest.mark.parametrize("folded", [".", "..", ""])
    async def test_google_asks_nothing_for_a_segment_that_would_fold(
        self, act: str, folded: str
    ) -> None:
        client, recorder = _google(), _Recorder(_ok())
        with pytest.raises(ConnectorAPIError) as refused:
            await _drive(client, recorder, lambda: _GOOGLE_ACTS[act](client, folded))
        assert refused.value.upstream_status_code == 404
        assert recorder.requests == []

    @pytest.mark.parametrize("act", sorted(_MICROSOFT_ACTS))
    @pytest.mark.parametrize("folded", [".", "..", ""])
    async def test_microsoft_asks_nothing_for_a_segment_that_would_fold(
        self, act: str, folded: str
    ) -> None:
        client, recorder = _microsoft(), _Recorder(_ok())
        with pytest.raises(ConnectorAPIError) as refused:
            await _drive(client, recorder, lambda: _MICROSOFT_ACTS[act](client, folded))
        assert refused.value.upstream_status_code == 404
        assert recorder.requests == []

    async def test_google_s_default_list_keeps_its_name(self) -> None:
        client, recorder = _google(), _Recorder(_ok({"items": []}))
        await _drive(client, recorder, lambda: client.list_tasks("@default"))
        assert recorder.requests[0].url.raw_path.decode().startswith("/tasks/v1/lists/@default/")


class TestTheListsOfListsPage:
    async def test_google_asks_the_next_page_and_publishes_its_token(self) -> None:
        client = _google()
        recorder = _Recorder(_ok({"items": [{"id": "l3"}], "nextPageToken": "p3"}))

        page = await _drive(client, recorder, lambda: client.list_task_lists(page_token="p2"))

        assert recorder.requests[0].url.params["pageToken"] == "p2"
        assert page["next_page_token"] == "p3"
        assert page["items"] == [{"id": "l3"}]

    async def test_google_s_last_page_publishes_no_token(self) -> None:
        client = _google()
        page = await _drive(client, _Recorder(_ok({"items": []})), client.list_task_lists)
        assert page["next_page_token"] is None

    async def test_microsoft_continues_on_its_own_host(self) -> None:
        client = _microsoft()
        recorder = _Recorder(
            _ok(
                {
                    "value": [{"id": "l3", "displayName": "Three"}],
                    "@odata.nextLink": f"{_GRAPH}/me/todo/lists?$top=25&$skip=50",
                }
            )
        )

        page = await _drive(client, recorder, lambda: client.list_task_lists(page_token="$skip=25"))

        sent = recorder.requests[0].url
        assert (sent.host, sent.params["$skip"]) == ("graph.microsoft.com", "25")
        assert page["next_page_token"] == "$skip=50"
        assert [item["id"] for item in page["items"]] == ["l3"]

    async def test_microsoft_refuses_a_token_it_did_not_produce(self) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"value": []}))
        with pytest.raises(ValueError):
            await _drive(
                client,
                recorder,
                lambda: client.list_task_lists(page_token="https://attacker.example/x"),
            )
        assert recorder.requests == []


class TestADueDateCanBeRemoved:
    async def test_google_writes_the_task_back_without_it(self) -> None:
        client = _google()
        existing = {"id": "t1", "title": "Pay", "due": "2026-11-03T00:00:00.000Z"}
        recorder = _Recorder(
            lambda request: httpx.Response(200, json=existing if request.method == "GET" else {})
        )

        await _drive(client, recorder, lambda: client.update_task("l1", "t1", clear_due=True))

        put = recorder.requests[-1]
        assert put.method == "PUT"
        assert "due" not in httpx.Response(200, content=put.content).json()

    async def test_microsoft_patches_it_to_nothing(self) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"id": "t1"}))

        await _drive(client, recorder, lambda: client.update_task("l1", "t1", clear_due=True))

        body = httpx.Response(200, content=recorder.requests[0].content).json()
        assert body == {"dueDateTime": None}

    @pytest.mark.parametrize("make", [_google, _microsoft])
    async def test_a_date_and_its_removal_together_are_refused_unsent(self, make: Any) -> None:
        client, recorder = make(), _Recorder(_ok())
        with pytest.raises(ValueError):
            await _drive(
                client,
                recorder,
                lambda: client.update_task(
                    "l1", "t1", due="2026-11-03T00:00:00.000Z", clear_due=True
                ),
            )
        assert recorder.requests == []


class TestAToDoDueNamesItsZone:
    """Measured on Graph (2026-11-07): given UTC, To Do keeps the UTC date; given the zone, it keeps
    local midnight. A due given with its zone is sent with it; one given without keeps UTC."""

    async def test_a_new_task_carries_the_zone_it_was_given(self) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"id": "t1"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_task(
                "l1", "Pay", due="2026-11-08T00:00:00", due_zone="Europe/Paris"
            ),
        )

        body = httpx.Response(200, content=recorder.requests[-1].content).json()
        assert body["dueDateTime"] == {
            "dateTime": "2026-11-08T00:00:00",
            "timeZone": "Europe/Paris",
        }

    async def test_a_change_carries_it_too(self) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"id": "t1"}))

        await _drive(
            client,
            recorder,
            lambda: client.update_task(
                "l1", "t1", due="2026-11-08T00:00:00", due_zone="Europe/Paris"
            ),
        )

        body = httpx.Response(200, content=recorder.requests[0].content).json()
        assert body["dueDateTime"] == {
            "dateTime": "2026-11-08T00:00:00",
            "timeZone": "Europe/Paris",
        }

    async def test_a_due_given_without_a_zone_keeps_utc(self) -> None:
        client, recorder = _microsoft(), _Recorder(_ok({"id": "t1"}))

        await _drive(
            client,
            recorder,
            lambda: client.update_task("l1", "t1", due="2026-11-08T00:00:00Z"),
        )

        body = httpx.Response(200, content=recorder.requests[0].content).json()
        assert body["dueDateTime"]["timeZone"] == "UTC"

    async def test_google_keeps_a_date_and_takes_no_zone(self) -> None:
        client = _google()
        recorder = _Recorder(_ok({"id": "t1", "title": "Pay"}))

        await _drive(
            client,
            recorder,
            lambda: client.create_task(
                "l1", "Pay", due="2026-11-08T00:00:00.000Z", due_zone="Europe/Paris"
            ),
        )

        body = httpx.Response(200, content=recorder.requests[-1].content).json()
        assert body["due"] == "2026-11-08T00:00:00.000Z"


class TestEditingACompletedGoogleTask:
    async def test_keeps_its_completion_date(self) -> None:
        client = _google()
        existing = {
            "id": "t1",
            "title": "Pay",
            "status": "completed",
            "completed": "2026-10-01T08:00:00.000Z",
        }
        recorder = _Recorder(
            lambda request: httpx.Response(200, json=existing if request.method == "GET" else {})
        )

        await _drive(client, recorder, lambda: client.update_task("l1", "t1", title="Paid"))

        body = httpx.Response(200, content=recorder.requests[-1].content).json()
        assert (body["status"], body["completed"]) == ("completed", "2026-10-01T08:00:00.000Z")

    async def test_reopening_it_drops_the_date(self) -> None:
        client = _google()
        existing = {"id": "t1", "title": "Pay", "status": "completed", "completed": "x"}
        recorder = _Recorder(
            lambda request: httpx.Response(200, json=existing if request.method == "GET" else {})
        )

        await _drive(client, recorder, lambda: client.update_task("l1", "t1", status="needsAction"))

        body = httpx.Response(200, content=recorder.requests[-1].content).json()
        assert body["status"] == "needsAction"
        assert "completed" not in body
