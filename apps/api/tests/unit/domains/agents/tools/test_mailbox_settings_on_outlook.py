"""The assistant reaches Outlook's automatic replies and rules (ADR-369, lot 12).

The same four tools serve Gmail and Outlook, as the same screen does: the mailbox's own client
speaks the settings' vocabulary, and what Outlook cannot hold is refused before the card, or
dropped from a card that shows exactly what will be written. A confirmed act runs on the provider
active at that moment.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.context import active_connector_types_ctx
from src.domains.agents.tools import mailbox_settings_tools as tools
from src.domains.agents.tools.common import connector_not_activated_refusal
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.outlook_mailbox_settings_mixin import (
    MailboxSettingsNotGrantedError,
)
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit

USER = uuid4()


def _outlook(**answers: Any) -> Any:
    mailbox = MagicMock(spec=MicrosoftOutlookClient)
    for name, answer in answers.items():
        setattr(mailbox, name, AsyncMock(return_value=answer))
    return mailbox


def _deps() -> Any:
    async def held(_: Any, connector_type: ConnectorType) -> Any:
        return object() if connector_type is ConnectorType.MICROSOFT_OUTLOOK else None

    service = MagicMock(get_connector_credentials=AsyncMock(side_effect=held))
    return MagicMock(get_connector_service=AsyncMock(return_value=service))


def _confirmed(client: Any) -> Any:
    return patch.object(
        tools,
        "resolve_client_for_category",
        AsyncMock(return_value=(client, ConnectorType.MICROSOFT_OUTLOOK)),
    )


class TestReading:
    async def test_the_settings_are_read_from_the_mailbox_itself(self) -> None:
        client = _outlook(
            get_vacation={"enableAutoReply": True, "responseBodyPlainText": "Away"},
            list_filters={"filter": [{"id": "r1", "criteria": {"from": "a"}, "action": {}}]},
            list_send_as={"sendAs": []},
        )

        result = await tools.GetMailboxSettingsTool().execute_api_call(client, USER)

        assert result["vacation_responder"]["enabled"] is True
        assert result["filter_count"] == 1
        assert result["send_as_count"] == 0

    async def test_a_connection_without_the_right_says_what_to_do(self) -> None:
        client = _outlook()
        client.get_vacation = AsyncMock(side_effect=MailboxSettingsNotGrantedError())

        result = await tools.GetMailboxSettingsTool().execute_api_call(client, USER)

        assert result["success"] is False
        assert result["error"] == tools.RECONNECT_TO_GRANT


class TestTheResponder:
    def test_an_open_end_is_a_real_error_on_outlook(self) -> None:
        token = active_connector_types_ctx.set(frozenset({ConnectorType.MICROSOFT_OUTLOOK.value}))
        try:
            assert tools._vacation_limits("2027-07-01", "") == "end_date_required"
            assert tools._vacation_limits("2027-07-01", "2027-07-02") is None
            assert tools._vacation_limits("", "") is None
        finally:
            active_connector_types_ctx.reset(token)

    def test_gmail_keeps_its_open_end(self) -> None:
        token = active_connector_types_ctx.set(frozenset({ConnectorType.GOOGLE_GMAIL.value}))
        try:
            assert tools._vacation_limits("2027-07-01", "") is None
        finally:
            active_connector_types_ctx.reset(token)

    async def test_a_confirmed_one_runs_on_the_active_mailbox(self) -> None:
        client = _outlook(update_vacation={})
        with _confirmed(client):
            result = await tools.execute_vacation_responder_draft(
                {
                    "enable": True,
                    "subject": "",
                    "body": "Away",
                    "start_date": "2027-07-01",
                    "end_date": "2027-07-02",
                    "user_timezone": "UTC",
                },
                USER,
                _deps(),
            )

        assert result == {"success": True, "enabled": True}
        sent = client.update_vacation.await_args.kwargs
        assert sent["body"] == "Away"
        assert sent["start_time_ms"] < sent["end_time_ms"]


class TestAConnectionWithoutTheRight:
    async def test_a_confirmed_act_says_so_by_its_connector(self) -> None:
        client = _outlook()
        client.update_vacation = AsyncMock(side_effect=MailboxSettingsNotGrantedError())

        with _confirmed(client):
            result = await tools.execute_vacation_responder_draft({"enable": False}, USER, _deps())

        assert result == connector_not_activated_refusal(ConnectorType.MICROSOFT_OUTLOOK)

    async def test_a_deletion_says_it_before_the_card(self) -> None:
        client = _outlook()
        client.list_filters = AsyncMock(side_effect=MailboxSettingsNotGrantedError())

        result = await tools.DeleteEmailFilterTool().execute_api_call(client, USER, filter_id="r1")

        assert result == {"success": False, "error": tools.RECONNECT_TO_GRANT}


class TestARule:
    async def test_a_gmail_search_is_refused_before_the_card(self) -> None:
        client = _outlook(list_labels={})

        result = await tools.CreateEmailFilterTool().execute_api_call(
            client, USER, query="larger:5M", mark_as_read=True
        )

        assert result == {"success": False, "error": "query_not_supported"}

    async def test_a_confirmed_one_runs_on_the_active_mailbox(self) -> None:
        client = _outlook(create_filter={"id": "r1"})
        with _confirmed(client):
            result = await tools.execute_email_filter_draft(
                {"criteria": {"from": "a@example.org"}, "mark_as_read": True}, USER, _deps()
            )

        assert result == {"success": True, "filter_id": "r1"}
        sent = client.create_filter.await_args.kwargs
        assert sent["action"] == {"removeLabelIds": ["UNREAD"]}

    async def test_a_deletion_reads_it_from_the_mailbox_first(self) -> None:
        rule = {"id": "r1", "criteria": {"from": "a"}, "action": {"addLabelIds": ["Bills"]}}
        client = _outlook(list_filters={"filter": [rule]}, label_names={})

        result = await tools.DeleteEmailFilterTool().execute_api_call(client, USER, filter_id="r1")

        assert result["success"] is True
        assert result["label_names"] == ["Bills"]

    async def test_a_confirmed_deletion_runs_on_the_active_mailbox(self) -> None:
        client = _outlook(delete_filter=None)
        with _confirmed(client):
            result = await tools.execute_email_filter_delete_draft(
                {"filter_id": "r1"}, USER, _deps()
            )

        assert result == {"success": True, "filter_id": "r1"}
        client.delete_filter.assert_awaited_once_with("r1")
