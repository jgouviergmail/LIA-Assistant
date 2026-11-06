"""Outlook's automatic replies and rules, in the mailbox settings' one vocabulary (ADR-369, lot 12).

The screen and the assistant speak to a mailbox's settings in the words of Gmail's settings
client: a responder bounded in epoch milliseconds, its end excluded, and filters made of criteria
and actions. The fake honours Graph's DOCUMENTED contract (the test account does not hold
``MailboxSettings.ReadWrite``, so nothing here is measured): a rule needs a ``displayName`` and a
``sequence``, ``moveToFolder`` takes a folder's id, a write answers less than a read says, and a
token without the right answers 403.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import MICROSOFT_OUTLOOK_SCOPES
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.mail_folders import MailFolder
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.outlook_mailbox_settings_mixin import (
    MailboxSettingNotHeldError,
    MailboxSettingsNotGrantedError,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

START = datetime(2027, 7, 1, 22, 0, tzinfo=UTC)
END = datetime(2027, 7, 15, 22, 0, tzinfo=UTC)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _when(moment: datetime) -> dict[str, str]:
    return {"dateTime": moment.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}


def _posted(graph: FakeGraph) -> Any:
    return next(body for method, _, body in graph.calls if method == "POST")


def _denied() -> ConnectorAPIError:
    return ConnectorAPIError("microsoft_outlook", 403, "Access is denied")


class FakeGraph:
    """The mailbox's settings and rules, in memory, as Graph documents them."""

    def __init__(self) -> None:
        self.replies: dict[str, Any] = {"status": "disabled", "externalAudience": "all"}
        self.rules: list[dict[str, Any]] = []
        self.calls: list[tuple[str, str, Any]] = []
        self.next_page: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        self.calls.append((method, endpoint, json_data))
        if endpoint == "/me/mailboxSettings/automaticRepliesSetting":
            return self.replies
        if endpoint == "/me/mailboxSettings":
            self.replies = {**self.replies, **json_data["automaticRepliesSetting"]}
            return {}
        if endpoint == "/me/mailFolders/archive":
            return {"id": "folder-archive"}
        if endpoint == "/me/mailFolders/inbox/messageRules" and method == "GET":
            if self.next_page:
                return {"value": self.rules, "@odata.nextLink": "https://graph/next"}
            return {"value": self.rules}
        if endpoint == "/me/mailFolders/inbox/messageRules":
            rule = {"id": f"r{len(self.rules) + 1}", "isReadOnly": False, **json_data}
            self.rules.append(rule)
            return rule
        if method == "DELETE":
            self.rules = [rule for rule in self.rules if not endpoint.endswith(rule["id"])]
            return {}
        raise AssertionError(endpoint)


@pytest.fixture
def graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def client(graph: FakeGraph) -> Iterator[MicrosoftOutlookClient]:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    outlook = MicrosoftOutlookClient(uuid4(), credentials, MagicMock())
    folders = [MailFolder("folder-bills", "Bills", "Bills")]
    with (
        patch.object(outlook, "_make_request", graph.request),
        patch.object(outlook, "list_folders", AsyncMock(return_value=(folders, True))),
    ):
        yield outlook


def test_the_right_is_asked_at_the_next_connection() -> None:
    assert "MailboxSettings.ReadWrite" in MICROSOFT_OUTLOOK_SCOPES


class TestTheResponder:
    async def test_off_reads_as_off(self, client: Any) -> None:
        vacation = await client.get_vacation()

        assert vacation["enableAutoReply"] is False
        assert "startTime" not in vacation

    async def test_a_scheduled_one_reads_as_its_instants(self, client: Any, graph: Any) -> None:
        graph.replies = {
            "status": "scheduled",
            "scheduledStartDateTime": _when(START),
            "scheduledEndDateTime": _when(END),
            "externalReplyMessage": "<html><body><p>Away</p></body></html>",
        }

        vacation = await client.get_vacation()

        assert vacation["enableAutoReply"] is True
        assert vacation["startTime"] == _ms(START)
        assert vacation["endTime"] == _ms(END)
        assert vacation["responseBodyPlainText"] == "Away"
        assert vacation["responseSubject"] == ""

    async def test_an_open_one_has_no_days(self, client: Any, graph: Any) -> None:
        graph.replies = {"status": "alwaysEnabled", "externalReplyMessage": "Away"}

        vacation = await client.get_vacation()

        assert vacation["enableAutoReply"] is True
        assert "startTime" not in vacation

    async def test_words_kept_for_the_organisation_alone_are_read(
        self, client: Any, graph: Any
    ) -> None:
        graph.replies = {"status": "alwaysEnabled", "internalReplyMessage": "Inside"}

        assert (await client.get_vacation())["responseBodyPlainText"] == "Inside"

    async def test_a_read_asks_its_instants_in_utc(self, client: Any) -> None:
        spy = AsyncMock(return_value={"status": "disabled"})

        with patch.object(client, "_make_request", spy):
            await client.get_vacation()

        assert spy.await_args.kwargs["extra_headers"] == {"Prefer": 'outlook.timezone="UTC"'}

    async def test_days_read_on_an_unknown_zone_are_no_days(self, client: Any, graph: Any) -> None:
        graph.replies = {
            "status": "scheduled",
            "scheduledStartDateTime": {"dateTime": "soon", "timeZone": "UTC"},
            "scheduledEndDateTime": _when(END),
        }

        assert "startTime" not in await client.get_vacation()

    async def test_days_are_written_as_a_schedule_in_utc(self, client: Any, graph: Any) -> None:
        vacation = await client.update_vacation(
            enable=True, body="Back soon", start_time_ms=_ms(START), end_time_ms=_ms(END)
        )

        written = graph.calls[0][2]["automaticRepliesSetting"]
        assert written["status"] == "scheduled"
        assert written["scheduledStartDateTime"]["timeZone"] == "UTC"
        assert written["scheduledStartDateTime"]["dateTime"].startswith("2027-07-01T22:00:00")
        assert written["scheduledEndDateTime"]["dateTime"].startswith("2027-07-15T22:00:00")
        assert written["externalAudience"] == "all"
        assert vacation["startTime"] == _ms(START)

    async def test_the_same_words_go_inside_and_outside(self, client: Any, graph: Any) -> None:
        await client.update_vacation(enable=True, body="Back <soon>\nLia")

        written = graph.calls[0][2]["automaticRepliesSetting"]
        assert written["status"] == "alwaysEnabled"
        assert written["internalReplyMessage"] == written["externalReplyMessage"]
        assert "Back &lt;soon&gt;<br>Lia" in written["externalReplyMessage"]

    async def test_a_last_day_alone_starts_now(self, client: Any, graph: Any) -> None:
        await client.update_vacation(enable=True, body="Away", end_time_ms=_ms(END))

        written = graph.calls[0][2]["automaticRepliesSetting"]
        assert written["status"] == "scheduled"
        assert "dateTime" in written["scheduledStartDateTime"]

    async def test_a_first_day_with_no_last_is_refused_unsent(
        self, client: Any, graph: Any
    ) -> None:
        with pytest.raises(MailboxSettingNotHeldError):
            await client.update_vacation(enable=True, body="Away", start_time_ms=_ms(START))

        assert graph.calls == []

    async def test_a_subject_outlook_would_drop_is_refused_unsent(
        self, client: Any, graph: Any
    ) -> None:
        with pytest.raises(MailboxSettingNotHeldError):
            await client.update_vacation(enable=True, subject="Away", body="Away")

        assert graph.calls == []

    async def test_turning_it_off_sends_only_that(self, client: Any, graph: Any) -> None:
        await client.update_vacation(enable=False)

        assert graph.calls[0][2] == {"automaticRepliesSetting": {"status": "disabled"}}

    async def test_a_write_is_proved_by_reading_it_back(self, client: Any, graph: Any) -> None:
        await client.update_vacation(enable=True, body="Away")

        assert [call[0] for call in graph.calls] == ["PATCH", "GET"]

    @pytest.mark.parametrize("act", ["read", "write"])
    async def test_a_token_without_the_right_says_so(
        self, client: Any, graph: Any, act: str
    ) -> None:
        with (
            patch.object(graph, "request", AsyncMock(side_effect=_denied())),
            patch.object(client, "_make_request", AsyncMock(side_effect=_denied())),
            pytest.raises(MailboxSettingsNotGrantedError),
        ):
            if act == "read":
                await client.get_vacation()
            else:
                await client.update_vacation(enable=False)

    async def test_any_other_refusal_stays_what_it_is(self, client: Any) -> None:
        failure = ConnectorAPIError("microsoft_outlook", 400, "Bad request")
        with (
            patch.object(client, "_make_request", AsyncMock(side_effect=failure)),
            pytest.raises(ConnectorAPIError),
        ):
            await client.get_vacation()


class TestARule:
    async def test_it_reads_as_criteria_and_actions(self, client: Any, graph: Any) -> None:
        graph.rules = [
            {
                "id": "r1",
                "displayName": "Bills",
                "sequence": 1,
                "isReadOnly": True,
                "conditions": {
                    "senderContains": ["ana@example.org"],
                    "recipientContains": ["team@example.org"],
                    "subjectContains": ["invoice"],
                    "hasAttachments": True,
                },
                "actions": {
                    "moveToFolder": "folder-bills",
                    "markAsRead": True,
                    "forwardTo": [{"emailAddress": {"address": "me@example.org"}}],
                },
            }
        ]

        listed = (await client.list_filters())["filter"][0]

        assert listed["id"] == "r1"
        assert listed["name"] == "Bills"
        assert listed["read_only"] is True
        assert listed["criteria"] == {
            "from": "ana@example.org",
            "to": "team@example.org",
            "subject": "invoice",
            "hasAttachment": True,
        }
        assert listed["action"]["addLabelIds"] == ["Bills"]
        assert listed["action"]["removeLabelIds"] == ["UNREAD"]
        assert listed["action"]["forward"] == "me@example.org"

    async def test_a_sender_named_exactly_reads_as_one(self, client: Any, graph: Any) -> None:
        graph.rules = [
            {
                "id": "r1",
                "displayName": "x",
                "conditions": {
                    "fromAddresses": [{"emailAddress": {"address": "ana@example.org"}}],
                    "sentToAddresses": [{"emailAddress": {"address": "me@example.org"}}],
                },
                "actions": {"delete": True},
            }
        ]

        listed = (await client.list_filters())["filter"][0]

        assert listed["criteria"] == {"from": "ana@example.org", "to": "me@example.org"}

    async def test_the_archive_reads_as_leaving_the_inbox(self, client: Any, graph: Any) -> None:
        graph.rules = [
            {
                "id": "r1",
                "displayName": "x",
                "conditions": {"subjectContains": ["news"]},
                "actions": {"moveToFolder": "folder-archive"},
            }
        ]

        listed = (await client.list_filters())["filter"][0]

        assert listed["action"].get("addLabelIds", []) == []
        assert listed["action"]["removeLabelIds"] == ["INBOX"]

    async def test_a_folder_nobody_lists_keeps_its_id(self, client: Any, graph: Any) -> None:
        graph.rules = [{"id": "r1", "displayName": "x", "actions": {"moveToFolder": "folder-gone"}}]

        listed = (await client.list_filters())["filter"][0]

        assert listed["action"]["addLabelIds"] == ["folder-gone"]

    async def test_a_page_past_the_first_is_read(self, client: Any, graph: Any) -> None:
        graph.rules = [{"id": "r1", "displayName": "x"}]
        graph.next_page = [{"id": "r2", "displayName": "y"}]
        follow = AsyncMock(return_value={"value": graph.next_page})

        with patch.object(client, "_make_request_full_url", follow):
            listed = (await client.list_filters())["filter"]

        assert [item["id"] for item in listed] == ["r1", "r2"]

    async def test_a_new_one_is_named_and_comes_last(self, client: Any, graph: Any) -> None:
        graph.rules = [{"id": "r1", "displayName": "x", "sequence": 4}]

        made = await client.create_filter(
            criteria={"from": "ana@example.org", "subject": "invoice", "hasAttachment": True},
            action={"addLabelIds": ["Bills"], "removeLabelIds": ["UNREAD"]},
        )

        written = _posted(graph)
        assert written["displayName"] == "ana@example.org"
        assert written["sequence"] == 5
        assert written["isEnabled"] is True
        assert written["conditions"] == {
            "senderContains": ["ana@example.org"],
            "subjectContains": ["invoice"],
            "hasAttachments": True,
        }
        assert written["actions"] == {"moveToFolder": "folder-bills", "markAsRead": True}
        assert made["id"] == "r2"

    async def test_the_first_rule_comes_first(self, client: Any, graph: Any) -> None:
        await client.create_filter(
            criteria={"to": "team@example.org"}, action={"removeLabelIds": ["UNREAD"]}
        )

        written = _posted(graph)
        assert written["sequence"] == 1
        assert written["displayName"] == "team@example.org"
        assert written["conditions"] == {"recipientContains": ["team@example.org"]}

    async def test_leaving_the_inbox_goes_to_the_archive(self, client: Any, graph: Any) -> None:
        await client.create_filter(
            criteria={"subject": "news"}, action={"removeLabelIds": ["INBOX"]}
        )

        assert _posted(graph)["actions"] == {"moveToFolder": "folder-archive"}

    async def test_a_folder_named_wins_over_the_archive(self, client: Any, graph: Any) -> None:
        await client.create_filter(
            criteria={"subject": "news"},
            action={"addLabelIds": ["Bills"], "removeLabelIds": ["INBOX"]},
        )

        assert _posted(graph)["actions"] == {"moveToFolder": "folder-bills"}

    async def test_a_folder_named_by_its_id_is_taken_as_it_is(
        self, client: Any, graph: Any
    ) -> None:
        await client.create_filter(
            criteria={"subject": "news"}, action={"addLabelIds": ["folder-bills"]}
        )

        assert _posted(graph)["actions"] == {"moveToFolder": "folder-bills"}

    async def test_a_mailbox_with_no_archive_is_refused_unsent(
        self, client: Any, graph: Any
    ) -> None:
        missing = ConnectorAPIError("microsoft_outlook", 404, "not found")

        with (
            patch.object(client, "_archive_id", AsyncMock(return_value=None)),
            pytest.raises(MailboxSettingNotHeldError),
        ):
            await client.create_filter(
                criteria={"subject": "news"}, action={"removeLabelIds": ["INBOX"]}
            )

        assert missing.upstream_status_code == 404
        assert [call for call in graph.calls if call[0] == "POST"] == []

    async def test_a_gmail_search_is_refused_unsent(self, client: Any, graph: Any) -> None:
        with pytest.raises(MailboxSettingNotHeldError):
            await client.create_filter(
                criteria={"query": "larger:5M"}, action={"removeLabelIds": ["UNREAD"]}
            )

        assert graph.calls == []

    async def test_it_is_deleted_by_its_id(self, client: Any, graph: Any) -> None:
        graph.rules = [{"id": "r1", "displayName": "x"}]

        await client.delete_filter("r1")

        assert graph.rules == []

    async def test_an_id_of_another_shape_asks_nothing(self, client: Any, graph: Any) -> None:
        with pytest.raises(ConnectorAPIError):
            await client.delete_filter("..")

        assert graph.calls == []


class TestWhatOutlookHasNot:
    async def test_it_sends_from_no_alias(self, client: Any) -> None:
        assert await client.list_send_as() == {"sendAs": []}

    async def test_folders_are_named_by_their_id(self, client: Any) -> None:
        assert await client.label_names() == {"folder-bills": "Bills"}

    def test_a_system_label_means_nothing_here(self, client: Any) -> None:
        assert client.is_system_label("Bills") is False
