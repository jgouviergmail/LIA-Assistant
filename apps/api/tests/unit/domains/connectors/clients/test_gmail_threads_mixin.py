"""Gmail thread reads for the mail RAG source (ADR-262).

The two calls go through the client's own request seam, honour the global
per-request volumetry cap, and never touch the message cache: a thread read
here becomes a document, not a prompt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.gmail_threads_mixin import GmailThreadsMixin
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> GoogleGmailClient:
    instance = GoogleGmailClient.__new__(GoogleGmailClient)
    instance.user_id = uuid4()
    return instance


def test_the_gmail_client_carries_the_thread_reads() -> None:
    assert issubclass(GoogleGmailClient, GmailThreadsMixin)


async def test_get_thread_reads_the_full_thread_without_caching(
    client: GoogleGmailClient,
) -> None:
    spy = AsyncMock(return_value={"id": "t1", "messages": []})
    client._make_request = spy  # type: ignore[method-assign]

    result = await client.get_thread("t1")

    assert result["id"] == "t1"
    assert spy.call_args.args[:2] == ("GET", "/users/me/threads/t1")
    assert spy.call_args.kwargs["params"] == {"format": "full"}


async def test_list_threads_filters_on_the_label_and_caps_the_page(
    client: GoogleGmailClient,
) -> None:
    spy = AsyncMock(return_value={"threads": [], "resultSizeEstimate": 0})
    client._make_request = spy  # type: ignore[method-assign]

    await client.list_threads(label_ids=["Label_7"], max_results=10_000, page_token="p2")

    assert spy.call_args.args[:2] == ("GET", "/users/me/threads")
    params = spy.call_args.kwargs["params"]
    assert params["labelIds"] == ["Label_7"]
    assert params["maxResults"] == apply_max_items_limit(10_000)
    assert params["pageToken"] == "p2"


async def test_list_threads_omits_an_absent_page_token(client: GoogleGmailClient) -> None:
    spy = AsyncMock(return_value={"threads": []})
    client._make_request = spy  # type: ignore[method-assign]

    await client.list_threads(label_ids=["Label_7"], max_results=50)

    assert "pageToken" not in spy.call_args.kwargs["params"]
