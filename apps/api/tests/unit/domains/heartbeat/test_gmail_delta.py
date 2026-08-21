"""Gmail history.list delta sync for the heartbeat (lot G, 2026-08).

Contract: ``fetch_new_message_ids`` returns the EXACT list of new INBOX
message ids since the stored anchor, or None whenever the caller must use
the legacy ``is:unread after:`` query (first run, unsupported provider,
expired anchor, Redis unavailable). None is always fail-open — the heartbeat
must keep working when the delta machinery cannot.

This is also the prerequisite of lot H phase 2: a Gmail push notification
only carries a historyId, this module turns it into messages.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.heartbeat.gmail_delta import fetch_new_message_ids

pytestmark = pytest.mark.unit


def _client(history: dict | Exception | None = None, profile_id: str = "1000") -> MagicMock:
    client = MagicMock(spec=["get_history", "get_profile"])
    client.get_profile = AsyncMock(return_value={"historyId": profile_id})
    if isinstance(history, Exception):
        client.get_history = AsyncMock(side_effect=history)
    else:
        client.get_history = AsyncMock(return_value=history or {})
    return client


def _redis(anchor: str | None = None) -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=anchor)
    redis.set = AsyncMock()
    return redis


class TestFetchNewMessageIds:
    async def test_provider_without_history_support_returns_none(self) -> None:
        client = MagicMock(spec=["search_emails"])  # Apple/Microsoft shape
        assert await fetch_new_message_ids(client, _redis(), uuid4()) is None

    async def test_first_run_anchors_and_falls_back_to_legacy(self) -> None:
        client = _client(profile_id="4321")
        redis = _redis(anchor=None)

        result = await fetch_new_message_ids(client, redis, uuid4())

        assert result is None  # legacy path this tick
        client.get_profile.assert_awaited_once()
        stored = redis.set.await_args.args[1]
        assert stored == "4321"

    async def test_delta_returns_new_ids_deduped_and_advances_anchor(self) -> None:
        client = _client(
            history={
                "history": [
                    {"messagesAdded": [{"message": {"id": "m1"}}]},
                    {"messagesAdded": [{"message": {"id": "m2"}}, {"message": {"id": "m1"}}]},
                    {},  # history entries without messagesAdded are ignored
                ],
                "historyId": "5000",
            }
        )
        redis = _redis(anchor="4000")

        result = await fetch_new_message_ids(client, redis, uuid4())

        assert result == ["m1", "m2"]
        client.get_history.assert_awaited_once()
        assert client.get_history.await_args.kwargs.get("start_history_id") == "4000"
        assert redis.set.await_args.args[1] == "5000"

    async def test_empty_delta_is_an_exact_empty_list_not_none(self) -> None:
        """No new mail is a real answer — the caller must NOT re-query."""
        client = _client(history={"historyId": "4100"})
        result = await fetch_new_message_ids(client, _redis(anchor="4000"), uuid4())
        assert result == []

    async def test_expired_anchor_reanchors_and_falls_back(self) -> None:
        """Gmail 404s an expired historyId — re-anchor and use the legacy path."""
        client = _client(
            history=ConnectorAPIError(
                connector_type="google_gmail", status_code=404, detail="expired"
            ),
            profile_id="9999",
        )
        redis = _redis(anchor="1")

        result = await fetch_new_message_ids(client, redis, uuid4())

        assert result is None
        assert redis.set.await_args.args[1] == "9999"

    async def test_redis_unavailable_is_fail_open(self) -> None:
        client = _client()
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("down"))
        assert await fetch_new_message_ids(client, redis, uuid4()) is None
