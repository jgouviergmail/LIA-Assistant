"""Gmail Settings client (lot I, 2026-08).

Dedicated client (the Gmail client file is size-frozen) riding the
GOOGLE_GMAIL connector token with the new ``gmail.settings.basic`` scope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.domains.connectors.clients.google_gmail_settings_client import (
    GoogleGmailSettingsClient,
)
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


def _client() -> GoogleGmailSettingsClient:
    instance = GoogleGmailSettingsClient.__new__(GoogleGmailSettingsClient)
    instance.user_id = uuid4()
    return instance


class TestScopes:
    def test_settings_scope_is_requested_at_oauth(self) -> None:
        assert "https://www.googleapis.com/auth/gmail.settings.basic" in GOOGLE_GMAIL_SCOPES

    def test_rides_the_gmail_connector(self) -> None:
        assert GoogleGmailSettingsClient.connector_type is ConnectorType.GOOGLE_GMAIL


class TestVacationSettings:
    async def test_get_vacation(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"enableAutoReply": False})
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.get_vacation()

        assert spy.call_args.args[:2] == ("GET", "/users/me/settings/vacation")
        assert result["enableAutoReply"] is False

    async def test_update_vacation_puts_full_settings(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"enableAutoReply": True})
        client._make_request = spy  # type: ignore[method-assign]

        await client.update_vacation(
            enable=True,
            subject="Absent",
            body="Je suis en congés jusqu'au 30/08.",
            start_time_ms=1_787_000_000_000,
            end_time_ms=1_787_800_000_000,
        )

        assert spy.call_args.args[:2] == ("PUT", "/users/me/settings/vacation")
        payload = spy.call_args.kwargs["json_data"]
        assert payload["enableAutoReply"] is True
        assert payload["responseSubject"] == "Absent"
        assert payload["responseBodyPlainText"].startswith("Je suis en congés")
        assert payload["startTime"] == 1_787_000_000_000
        assert payload["endTime"] == 1_787_800_000_000

    async def test_update_vacation_disable_omits_times(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"enableAutoReply": False})
        client._make_request = spy  # type: ignore[method-assign]

        await client.update_vacation(enable=False)

        payload = spy.call_args.kwargs["json_data"]
        assert payload == {"enableAutoReply": False}


class TestCreateFilter:
    async def test_create_filter_posts_criteria_and_action(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"id": "f9"})
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.create_filter(
            criteria={"from": "news@x.com"},
            action={"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"]},
        )

        assert spy.call_args.args[:2] == ("POST", "/users/me/settings/filters")
        payload = spy.call_args.kwargs["json_data"]
        assert payload["criteria"] == {"from": "news@x.com"}
        assert payload["action"]["addLabelIds"] == ["Label_1"]
        assert result["id"] == "f9"


class TestReadOnlyLists:
    async def test_list_filters(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"filter": [{"id": "f1"}]})
        client._make_request = spy  # type: ignore[method-assign]
        result = await client.list_filters()
        assert spy.call_args.args[:2] == ("GET", "/users/me/settings/filters")
        assert result["filter"] == [{"id": "f1"}]

    async def test_list_send_as(self) -> None:
        client = _client()
        spy = AsyncMock(return_value={"sendAs": [{"sendAsEmail": "me@x.com"}]})
        client._make_request = spy  # type: ignore[method-assign]
        result = await client.list_send_as()
        assert spy.call_args.args[:2] == ("GET", "/users/me/settings/sendAs")
        assert result["sendAs"][0]["sendAsEmail"] == "me@x.com"
