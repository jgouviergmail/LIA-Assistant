"""Gmail history/profile client contract (lot G, 2026-08)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> GoogleGmailClient:
    instance = GoogleGmailClient.__new__(GoogleGmailClient)
    instance.user_id = uuid4()
    return instance


class TestGetProfile:
    async def test_calls_profile_endpoint(self, client: GoogleGmailClient) -> None:
        spy = AsyncMock(return_value={"historyId": "123"})
        client._make_request = spy  # type: ignore[method-assign]
        result = await client.get_profile()
        assert spy.call_args.args[:2] == ("GET", "/users/me/profile")
        assert result["historyId"] == "123"


class TestGetHistory:
    async def test_requests_inbox_message_added_deltas(self, client: GoogleGmailClient) -> None:
        spy = AsyncMock(return_value={"history": []})
        client._make_request = spy  # type: ignore[method-assign]

        await client.get_history(start_history_id="4000")

        assert spy.call_args.args[:2] == ("GET", "/users/me/history")
        params = spy.call_args.kwargs["params"]
        assert params["startHistoryId"] == "4000"
        # A list: httpx repeats the key, which is how the API takes several
        # history types (the mail RAG source asks for three — ADR-262).
        assert params["historyTypes"] == ["messageAdded"]
        # INBOX only: sent, spam and archived mail are not heartbeat signal.
        assert params["labelId"] == "INBOX"
        assert params["maxResults"] > 0

    async def test_a_label_source_reads_its_own_label_changes(
        self, client: GoogleGmailClient
    ) -> None:
        """ADR-262: the mail source follows label adds/removes on ITS label."""
        spy = AsyncMock(return_value={"history": []})
        client._make_request = spy  # type: ignore[method-assign]

        await client.get_history(
            start_history_id="4000",
            history_types=("messageAdded", "labelAdded", "labelRemoved"),
            label_id="Label_42",
        )

        params = spy.call_args.kwargs["params"]
        assert params["historyTypes"] == ["messageAdded", "labelAdded", "labelRemoved"]
        assert params["labelId"] == "Label_42"
