"""Watch/stop API payloads on the Google clients (lot H, 2026-08).

Google's watch contract is exact: ``type`` must be ``web_hook``, ``ttl`` is a
string inside ``params``, drive watch requires the pageToken baseline, and
stop goes to the API-wide ``/channels/stop`` endpoint (Gmail uses
``/users/me/stop``). These payloads are pinned here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.google_gmail_settings_client import (
    GoogleGmailSettingsClient,
)

pytestmark = pytest.mark.unit


def _client(cls: type) -> object:
    instance = cls.__new__(cls)
    instance.user_id = uuid4()
    return instance


class TestCalendarWatch:
    async def test_watch_events_payload(self) -> None:
        client = _client(GoogleCalendarClient)
        spy = AsyncMock(return_value={"resourceId": "res-1", "expiration": "1787000000000"})
        client._make_request = spy  # type: ignore[attr-defined]

        result = await client.watch_events(  # type: ignore[attr-defined]
            channel_id="chan-1",
            token="secret",
            address="https://api.example.com/webhooks/google",
            ttl_seconds=604800,
        )

        method, path = spy.call_args.args[:2]
        assert (method, path) == ("POST", "/calendars/primary/events/watch")
        payload = spy.call_args.kwargs["json_data"]
        assert payload["id"] == "chan-1"
        assert payload["type"] == "web_hook"
        assert payload["address"] == "https://api.example.com/webhooks/google"
        assert payload["token"] == "secret"
        assert payload["params"] == {"ttl": "604800"}
        assert result["resourceId"] == "res-1"

    async def test_stop_channel(self) -> None:
        client = _client(GoogleCalendarClient)
        spy = AsyncMock(return_value={})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.stop_channel("chan-1", "res-1")  # type: ignore[attr-defined]

        assert spy.call_args.args[:2] == ("POST", "/channels/stop")
        assert spy.call_args.kwargs["json_data"] == {"id": "chan-1", "resourceId": "res-1"}


class TestDriveWatch:
    async def test_start_page_token(self) -> None:
        client = _client(GoogleDriveClient)
        spy = AsyncMock(return_value={"startPageToken": "1234"})
        client._make_request = spy  # type: ignore[attr-defined]

        token = await client.get_changes_start_page_token()  # type: ignore[attr-defined]

        assert spy.call_args.args[:2] == ("GET", "/changes/startPageToken")
        assert token == "1234"

    async def test_watch_changes_payload(self) -> None:
        client = _client(GoogleDriveClient)
        spy = AsyncMock(return_value={"resourceId": "res-d"})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.watch_changes(  # type: ignore[attr-defined]
            channel_id="chan-d",
            token="secret",
            address="https://api.example.com/webhooks/google",
            ttl_seconds=604800,
            page_token="1234",
        )

        method, path = spy.call_args.args[:2]
        assert (method, path) == ("POST", "/changes/watch")
        assert spy.call_args.kwargs["params"] == {"pageToken": "1234"}
        payload = spy.call_args.kwargs["json_data"]
        assert payload["type"] == "web_hook"
        assert payload["params"] == {"ttl": "604800"}

    async def test_stop_channel(self) -> None:
        client = _client(GoogleDriveClient)
        spy = AsyncMock(return_value={})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.stop_channel("chan-d", "res-d")  # type: ignore[attr-defined]

        assert spy.call_args.args[:2] == ("POST", "/channels/stop")


class TestGmailWatch:
    async def test_watch_mailbox_payload(self) -> None:
        client = _client(GoogleGmailSettingsClient)
        spy = AsyncMock(return_value={"historyId": "42", "expiration": "1787000000000"})
        client._make_request = spy  # type: ignore[attr-defined]

        result = await client.watch_mailbox(  # type: ignore[attr-defined]
            topic_name="projects/p/topics/lia-gmail-push"
        )

        assert spy.call_args.args[:2] == ("POST", "/users/me/watch")
        payload = spy.call_args.kwargs["json_data"]
        assert payload["topicName"] == "projects/p/topics/lia-gmail-push"
        assert payload["labelIds"] == ["INBOX"]
        assert result["historyId"] == "42"

    async def test_stop_mailbox_watch(self) -> None:
        client = _client(GoogleGmailSettingsClient)
        spy = AsyncMock(return_value={})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.stop_mailbox_watch()  # type: ignore[attr-defined]

        assert spy.call_args.args[:2] == ("POST", "/users/me/stop")
