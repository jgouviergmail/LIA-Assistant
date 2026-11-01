"""Drive ids as ONE path segment, and values that cannot close a query string (ADR-369).

A file id reaches the Drive client from a browser (the « Tools » files screen)
or a model (the assistant's Drive tools). Interpolated raw into a path,
``a/../b`` or ``x?y`` aimed the person's own token at another endpoint;
interpolated raw into the ``q`` expression, a quote closed the string and the
rest became query syntax (``' or trashed = true or '``). Every id now travels
quoted in a path, a folded one refused before any request, and every value in
``q`` is escaped as Drive's grammar asks — the backslash before the quote, or an
escaped backslash re-opens the quote.

A download whose size the caller already read does not read the metadata twice.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

HOSTILE = "a/../b?alt=media#x"
QUOTED = "a%2F..%2Fb%3Falt%3Dmedia%23x"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.fixture
def client() -> Iterator[GoogleDriveClient]:
    yield GoogleDriveClient(uuid4(), _credentials(), MagicMock())


async def _drive(
    client: Any, call: Callable[[], Any], answer: httpx.Response | None = None
) -> tuple[list[httpx.Request], Any]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if answer is not None:
            return answer
        if request.url.params.get("alt") == "media" or request.url.path.endswith("/export"):
            return httpx.Response(200, content=b"bytes")
        return httpx.Response(200, json={"id": "f1", "name": "Report", "size": "5", "files": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await call()
    return seen, result


def _path(request: httpx.Request) -> str:
    return request.url.raw_path.decode().split("?", 1)[0]


class TestFileIdsArePathSegments:
    @pytest.mark.parametrize(
        ("call", "suffix"),
        [
            (lambda c: c.get_file_metadata(HOSTILE), ""),
            (lambda c: c.export_google_doc(HOSTILE, "application/pdf"), "/export"),
            (lambda c: c.delete_file(HOSTILE), ""),
        ],
    )
    async def test_a_file_id_travels_as_one_path_segment(
        self, client: GoogleDriveClient, call: Callable[[Any], Any], suffix: str
    ) -> None:
        seen, _ = await _drive(client, lambda: call(client))

        assert [_path(request) for request in seen] == [f"/drive/v3/files/{QUOTED}{suffix}"]

    async def test_a_download_quotes_its_id_on_both_reads(self, client: GoogleDriveClient) -> None:
        seen, data = await _drive(client, lambda: client.get_file_content(HOSTILE))

        assert [_path(request) for request in seen] == [f"/drive/v3/files/{QUOTED}"] * 2
        assert data == b"bytes"

    @pytest.mark.parametrize("folded", ["", ".", ".."])
    async def test_a_folded_id_is_refused_before_any_request(
        self, client: GoogleDriveClient, folded: str
    ) -> None:
        seen: list[httpx.Request] = []
        with pytest.raises(ConnectorAPIError) as refused:
            seen, _ = await _drive(client, lambda: client.get_file_metadata(folded))

        assert (refused.value.upstream_status_code, seen) == (404, [])


class TestQueryValuesAreEscaped:
    async def test_a_folder_id_cannot_close_the_query_string(
        self, client: GoogleDriveClient
    ) -> None:
        seen, _ = await _drive(
            client, lambda: client.list_files(folder_id="x' in parents or 'a", content_type="all")
        )

        assert seen[0].url.params["q"] == "'x\\' in parents or \\'a' in parents and trashed = false"

    async def test_search_words_escape_the_backslash_before_the_quote(
        self, client: GoogleDriveClient
    ) -> None:
        # « a\' or trashed = true or name contains 'b »: escaping only the quote
        # leaves « a\\' » — an escaped backslash, then a quote that closes.
        words = "a\\' or trashed = true or name contains 'b"
        seen, _ = await _drive(
            client, lambda: client.search_files(words, folder_id="f'1", content_type="all")
        )

        assert seen[0].url.params["q"] == (
            "name contains 'a\\\\\\' or trashed = true or name contains \\'b'"
            " and 'f\\'1' in parents and trashed = false"
        )


class TestASearchPages:
    async def test_a_search_follows_its_cursor_and_hands_the_next_one(
        self, client: GoogleDriveClient
    ) -> None:
        # Drive may answer a partial page before the end: only its cursor says more.
        answer = httpx.Response(200, json={"files": [], "nextPageToken": "n3"})
        seen, result = await _drive(
            client, lambda: client.search_files("budget", page_token="n2"), answer
        )

        params = seen[0].url.params
        assert (params["pageToken"], params["fields"].startswith("nextPageToken,files(")) == (
            "n2",
            True,
        )
        assert result["nextPageToken"] == "n3"

    @pytest.mark.parametrize(
        ("mode", "order"), [("name_only", "modifiedTime desc"), ("full_text", None)]
    )
    async def test_a_full_text_search_asks_no_order(
        self, client: GoogleDriveClient, mode: str, order: str | None
    ) -> None:
        # Drive refuses a sort beside a fullText term (« results are always in
        # descending relevance order »): asked, the whole search failed.
        seen, _ = await _drive(client, lambda: client.search_files("budget", search_mode=mode))

        assert seen[0].url.params.get("orderBy") == order


class TestAKnownSize:
    async def test_reads_the_body_without_a_second_metadata_read(
        self, client: GoogleDriveClient
    ) -> None:
        seen, data = await _drive(
            client, lambda: client.get_file_content("f1", max_size_bytes=10, known_size=5)
        )

        assert ([request.url.params.get("alt") for request in seen], data) == (["media"], b"bytes")

    async def test_past_the_bound_reads_nothing(self, client: GoogleDriveClient) -> None:
        seen, data = await _drive(
            client, lambda: client.get_file_content("f1", max_size_bytes=10, known_size=11)
        )

        assert (seen, data) == ([], None)
