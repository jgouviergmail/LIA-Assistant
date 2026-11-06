"""OneDrive's changes, in the words of Drive's feed (ADR-369, lot 11).

One drain reads both drives: a page names ``changes``, then ``nextPageToken`` or
``newStartPageToken``. Graph's tokens live inside its links, whichever form the link takes, and
its subscription refuses a second one on the same resource.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote_plus
from uuid import uuid4

import httpx
import pytest

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME, RAG_DRIVE_CHANGES_PAGE_SIZE_MAX
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.onedrive_changes import ChangesFeedLostError, delta_token
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

GRAPH = "https://graph.microsoft.com/v1.0"
WHEN = datetime(2026, 11, 20, 8, 30, tzinfo=UTC)
FILE = {
    "id": "f1",
    "name": "Budget.pdf",
    "file": {"mimeType": "application/pdf"},
    "lastModifiedDateTime": "2026-11-02T09:00:00Z",
    "parentReference": {"id": "p1"},
}


def _client() -> MicrosoftOneDriveClient:
    return MicrosoftOneDriveClient(
        uuid4(),
        ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        MagicMock(),
    )


class _Graph:
    def __init__(self, *answers: httpx.Response) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, unquote_plus(str(request.url)), body))
        return self.answers.pop(0)


async def _ask(graph: _Graph, call: Callable[[MicrosoftOneDriveClient], Any]) -> Any:
    client = _client()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call(client)


class TestAToken:
    @pytest.mark.parametrize(
        ("link", "expected"),
        [
            (f"{GRAPH}/me/drive/root/delta?token=abc123", "abc123"),
            (f"{GRAPH}/me/drive/root/delta(token='abc123')", "abc123"),
            (f"{GRAPH}/me/drive/root/delta?(token='abc123')", "abc123"),
            (f"{GRAPH}/me/drive/root/delta(token=%27abc123%27)", "abc123"),
            (f"{GRAPH}/me/drive/root/delta?token=a%2Bb", "a+b"),
        ],
    )
    def test_it_is_read_whichever_form_the_link_takes(self, link: str, expected: str) -> None:
        assert delta_token(link) == expected

    @pytest.mark.parametrize("link", [None, "", f"{GRAPH}/me/drive/root/delta"])
    def test_a_link_with_none_names_none(self, link: str | None) -> None:
        assert delta_token(link) is None


class TestWhereTheFeedStarts:
    async def test_it_is_now_nothing_enumerated(self) -> None:
        graph = _Graph(
            httpx.Response(
                200, json={"value": [], "@odata.deltaLink": f"{GRAPH}/delta?token=latest-1"}
            )
        )

        token = await _ask(graph, lambda client: client.get_changes_start_page_token())

        assert token == "latest-1"
        assert "/me/drive/root/delta?token=latest" in graph.calls[0][1]

    async def test_an_answer_with_no_token_is_said(self) -> None:
        graph = _Graph(httpx.Response(200, json={"value": []}))

        with pytest.raises(ChangesFeedLostError):
            await _ask(graph, lambda client: client.get_changes_start_page_token())


class TestAPage:
    async def test_it_reads_as_drive_s(self) -> None:
        graph = _Graph(
            httpx.Response(
                200, json={"value": [FILE], "@odata.nextLink": f"{GRAPH}/delta?token=next-1"}
            )
        )

        page = await _ask(graph, lambda client: client.list_changes("from-1", page_size=50))

        assert page["nextPageToken"] == "next-1"
        assert "newStartPageToken" not in page
        (change,) = page["changes"]
        assert change["fileId"] == "f1"
        assert change["removed"] is False
        assert change["file"]["mimeType"] == "application/pdf"
        assert change["file"]["parents"] == ["p1"]
        url = graph.calls[0][1]
        assert "/me/drive/root/delta?token=from-1" in url
        assert "$top=50" in url
        assert "deleted" in url

    async def test_the_last_one_says_where_the_next_drain_starts(self) -> None:
        graph = _Graph(
            httpx.Response(200, json={"value": [], "@odata.deltaLink": f"{GRAPH}/d?token=base-2"})
        )

        page = await _ask(graph, lambda client: client.list_changes("from-1"))

        assert page == {"changes": [], "newStartPageToken": "base-2"}

    async def test_a_deleted_file_is_removed_under_its_parent(self) -> None:
        deleted = {"id": "f1", "deleted": {}, "parentReference": {"id": "p1"}}
        graph = _Graph(
            httpx.Response(200, json={"value": [deleted], "@odata.deltaLink": f"{GRAPH}/d?token=b"})
        )

        (change,) = (await _ask(graph, lambda client: client.list_changes("t")))["changes"]

        assert change["removed"] is True
        assert change["file"]["parents"] == ["p1"]

    async def test_a_deleted_folder_stays_a_folder(self) -> None:
        deleted = {"id": "d1", "deleted": {}, "folder": {}}
        graph = _Graph(
            httpx.Response(200, json={"value": [deleted], "@odata.deltaLink": f"{GRAPH}/d?token=b"})
        )

        (change,) = (await _ask(graph, lambda client: client.list_changes("t")))["changes"]

        assert change["file"]["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME

    async def test_its_size_stays_within_the_feed_s_bound(self) -> None:
        graph = _Graph(
            httpx.Response(200, json={"value": [], "@odata.deltaLink": f"{GRAPH}/d?token=b"})
        )

        await _ask(graph, lambda client: client.list_changes("t", page_size=1_000_000))

        assert f"$top={RAG_DRIVE_CHANGES_PAGE_SIZE_MAX}&" in graph.calls[0][1]

    async def test_a_token_graph_forgot_is_a_lost_feed(self) -> None:
        graph = _Graph(httpx.Response(410, json={"error": {"code": "resyncRequired"}}))

        with pytest.raises(ChangesFeedLostError):
            await _ask(graph, lambda client: client.list_changes("old"))

    async def test_any_other_failure_stays_what_it_is(self) -> None:
        graph = _Graph(httpx.Response(403, json={"error": {"code": "accessDenied"}}))

        with pytest.raises(Exception) as raised:
            await _ask(graph, lambda client: client.list_changes("t"))

        assert not isinstance(raised.value, ChangesFeedLostError)


class TestASubscription:
    async def test_it_watches_the_whole_drive(self) -> None:
        graph = _Graph(httpx.Response(201, json={"id": "s1", "expirationDateTime": "x"}))

        answer = await _ask(
            graph,
            lambda client: client.create_subscription("https://a.test/hook", "secret", WHEN),
        )

        method, url, body = graph.calls[0]
        assert (method, url) == ("POST", f"{GRAPH}/subscriptions")
        assert body == {
            "changeType": "updated",
            "notificationUrl": "https://a.test/hook",
            "resource": "me/drive/root",
            "expirationDateTime": "2026-11-20T08:30:00Z",
            "clientState": "secret",
            "latestSupportedTlsVersion": "v1_2",
        }
        assert answer["id"] == "s1"

    async def test_one_that_outlived_its_row_is_replaced(self) -> None:
        """Graph refuses a second subscription: a reconnected drive would stay silent for days."""
        graph = _Graph(
            httpx.Response(409, json={"error": {"code": "ExtensionError"}}),
            httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "old", "resource": "me/drive/root"},
                        {"id": "mail", "resource": "me/messages"},
                    ]
                },
            ),
            httpx.Response(204),
            httpx.Response(201, json={"id": "s2"}),
        )

        answer = await _ask(
            graph,
            lambda client: client.create_subscription("https://a.test/hook", "secret", WHEN),
        )

        assert answer["id"] == "s2"
        assert [(call[0], call[1].removeprefix(GRAPH)) for call in graph.calls] == [
            ("POST", "/subscriptions"),
            ("GET", "/subscriptions"),
            ("DELETE", "/subscriptions/old"),
            ("POST", "/subscriptions"),
        ]

    async def test_any_other_refusal_stays_what_it_is(self) -> None:
        graph = _Graph(httpx.Response(403, json={"error": {"code": "accessDenied"}}))

        with pytest.raises(Exception):  # noqa: B017 - the type is the client's own
            await _ask(
                graph,
                lambda client: client.create_subscription("https://a.test/hook", "secret", WHEN),
            )

        assert len(graph.calls) == 1

    async def test_it_is_renewed_in_place(self) -> None:
        graph = _Graph(httpx.Response(200, json={"id": "s1"}))

        await _ask(graph, lambda client: client.renew_subscription("s1", WHEN))

        assert graph.calls[0] == (
            "PATCH",
            f"{GRAPH}/subscriptions/s1",
            {"expirationDateTime": "2026-11-20T08:30:00Z"},
        )

    async def test_an_id_travels_as_one_segment(self) -> None:
        graph = _Graph(httpx.Response(204))

        await _ask(graph, lambda client: client.delete_subscription("a/../b"))

        assert "/subscriptions/a/../b" in graph.calls[0][1]
        assert graph.calls[0][0] == "DELETE"
