"""A mailbox's settings, by the person's own hand (ADR-369, Task 4.6, lot 12).

Gmail and Outlook carry them (the descriptor's VACATION and FILTERS): elsewhere
they are refused before anything is sent. The vacation responder is set in
the person's own DAYS — the first one from its midnight, the last one
INCLUDED (Gmail's ``endTime`` is exclusive: the midnight after) — and read back
as the same days. A filter is created once per submission, never applying a
system label; the list says what each one does, and one is deleted by its id: the
client has no such act (the panel says so).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Iterator
from datetime import date, datetime
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients import mailbox_settings
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.outlook_mailbox_settings_mixin import (
    MailboxSettingNotHeldError,
    MailboxSettingsNotGrantedError,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_settings
from src.domains.workbench.errors import (
    NOT_SUPPORTED_BY_PROVIDER,
    OUTCOME_UNKNOWN,
    RECONNECT_REQUIRED,
    refusal_code_of,
)
from src.domains.workbench.schemas.mail_settings import NewFilter, VacationChange
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")


def _millis(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=PARIS).timestamp() * 1000)


@pytest.fixture(autouse=True)
def redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


@pytest.fixture
def gmail_settings() -> Any:
    client = MagicMock(
        update_vacation=AsyncMock(return_value={}),
        get_vacation=AsyncMock(),
        list_filters=AsyncMock(),
        create_filter=AsyncMock(return_value={"id": "f9", "criteria": {}, "action": {}}),
        delete_filter=AsyncMock(),
        close=AsyncMock(),
    )
    built = MagicMock(return_value=client)
    with (
        patch.object(mail_settings, "GoogleGmailSettingsClient", built),
        patch.object(mailbox_settings, "GoogleGmailSettingsClient", built),
    ):
        yield client


def _door(kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
    mailbox = MagicMock(spec=GoogleGmailClient, credentials=object())
    mailbox.is_system_label = lambda name: name.upper() in {"INBOX", "TRASH", "UNREAD"}

    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=mailbox, connector_type=kind, preferred_name=None)

    return patch.object(mail_settings, "open_tool_client", opened)


@contextlib.contextmanager
def _settings_client(client: Any) -> Iterator[None]:
    with (
        patch.object(mail_settings, "GoogleGmailSettingsClient", return_value=client),
        patch.object(mailbox_settings, "GoogleGmailSettingsClient", return_value=client),
    ):
        yield


class TestSendAs:
    LISTED: ClassVar[dict[str, Any]] = {
        "sendAs": [
            {
                "sendAsEmail": "me@gmail.com",
                "displayName": "",
                "isPrimary": True,
                "isDefault": True,
            },
            {
                "sendAsEmail": "work@example.com",
                "displayName": "Ana Lima",
                "verificationStatus": "accepted",
            },
            {"sendAsEmail": "pending@example.com", "verificationStatus": "pending"},
        ]
    }

    async def test_the_addresses_offered_are_those_gmail_sends_from(self) -> None:
        client = MagicMock(list_send_as=AsyncMock(return_value=self.LISTED), close=AsyncMock())
        with _door(ConnectorType.GOOGLE_GMAIL), _settings_client(client):
            senders = await mail_settings.read_send_as(USER)

        assert [(item.address, item.is_default) for item in senders.items] == [
            ("me@gmail.com", True),
            ("work@example.com", False),
        ]

    async def test_a_provider_with_no_alias_lists_nothing_and_calls_nobody(self) -> None:
        with _door(ConnectorType.MICROSOFT_OUTLOOK), pytest.raises(BaseAPIException) as refused:
            await mail_settings.read_send_as(USER)

        assert refused.value.detail["code"] == "not_supported_by_provider"

    def _opened(self, connector_type: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
        mailbox = MagicMock(send_from=MagicMock(), credentials=MagicMock())
        return ActiveClient(client=mailbox, connector_type=connector_type, preferred_name=None)

    async def test_an_alias_of_the_mailbox_becomes_where_the_message_leaves_from(self) -> None:
        opened = self._opened()
        client = MagicMock(list_send_as=AsyncMock(return_value=self.LISTED), close=AsyncMock())
        with _settings_client(client):
            await mail_settings.apply_send_as(opened, USER, "WORK@example.com")

        opened.client.send_from.assert_called_once_with("Ana Lima <work@example.com>")
        client.close.assert_awaited_once()

    @pytest.mark.parametrize("address", ["pending@example.com", "stranger@example.com"])
    async def test_an_address_gmail_would_rewrite_is_refused(self, address: str) -> None:
        opened = self._opened()
        client = MagicMock(list_send_as=AsyncMock(return_value=self.LISTED), close=AsyncMock())
        with _settings_client(client), pytest.raises(BaseAPIException) as refused:
            await mail_settings.apply_send_as(opened, USER, address)

        assert refused.value.detail["code"] == "invalid_request"
        opened.client.send_from.assert_not_called()

    async def test_a_provider_with_no_alias_refuses_one(self) -> None:
        opened = self._opened(ConnectorType.APPLE_EMAIL)

        with pytest.raises(BaseAPIException) as refused:
            await mail_settings.apply_send_as(opened, USER, "work@example.com")

        assert refused.value.detail["code"] == "not_supported_by_provider"


class TestTheVacationResponder:
    async def test_it_is_set_in_the_person_s_days_the_last_one_included(
        self, gmail_settings: Any
    ) -> None:
        change = VacationChange(
            enabled=True,
            subject="Absent",
            body="De retour le 9.",
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 6),
        )
        with _door():
            await mail_settings.set_vacation(USER, PARIS, change)

        gmail_settings.update_vacation.assert_awaited_once_with(
            enable=True,
            subject="Absent",
            body="De retour le 9.",
            start_time_ms=_millis(date(2026, 11, 2)),
            end_time_ms=_millis(date(2026, 11, 7)),
        )
        gmail_settings.close.assert_awaited_once()

    async def test_it_reads_back_as_the_same_days(self, gmail_settings: Any) -> None:
        gmail_settings.get_vacation.return_value = {
            "enableAutoReply": True,
            "responseSubject": "Absent",
            "responseBodyPlainText": "De retour le 9.",
            "startTime": str(_millis(date(2026, 11, 2))),
            "endTime": str(_millis(date(2026, 11, 7))),
        }
        with _door():
            vacation = await mail_settings.read_vacation(USER, PARIS)

        assert (vacation.enabled, vacation.start_date, vacation.end_date) == (
            True,
            date(2026, 11, 2),
            date(2026, 11, 6),
        )

    async def test_turning_it_off_sends_only_that(self, gmail_settings: Any) -> None:
        with _door():
            await mail_settings.set_vacation(USER, PARIS, VacationChange(enabled=False))

        gmail_settings.update_vacation.assert_awaited_once_with(enable=False)

    def test_a_period_ends_on_or_after_it_starts(self) -> None:
        with pytest.raises(ValidationError):
            VacationChange(enabled=True, start_date=date(2026, 11, 6), end_date=date(2026, 11, 2))


class TestFilters:
    async def test_the_list_says_what_each_does(self, gmail_settings: Any) -> None:
        gmail_settings.list_filters.return_value = {
            "filter": [
                {
                    "id": "f1",
                    "criteria": {"from": "news@example.org", "hasAttachment": True},
                    "action": {"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX", "UNREAD"]},
                }
            ]
        }
        with _door():
            listed = await mail_settings.list_filters(USER)

        found = listed.filters[0]
        assert (found.id, found.sender, found.has_attachment) == ("f1", "news@example.org", True)
        assert (found.add_label_ids, found.archive, found.mark_read) == (["Label_1"], True, True)

    async def test_one_is_created_once_per_submission(self, gmail_settings: Any) -> None:
        request = NewFilter(
            sender="news@example.org",
            add_label_id="Label_1",
            archive=True,
            idempotency_key=uuid4(),
        )
        with _door():
            made = await mail_settings.create_filter(USER, request)
            with pytest.raises(BaseAPIException) as replayed:
                await mail_settings.create_filter(USER, request)

        gmail_settings.create_filter.assert_awaited_once_with(
            criteria={"from": "news@example.org"},
            action={"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"]},
        )
        assert made.id == "f9"
        assert replayed.value.detail["code"] == "already_submitted"

    async def test_a_filter_is_deleted_by_its_id(self, gmail_settings: Any) -> None:
        with _door():
            await mail_settings.delete_filter(USER, "f9")

        gmail_settings.delete_filter.assert_awaited_once_with("f9")
        gmail_settings.close.assert_awaited()

    async def test_deleting_a_filter_elsewhere_is_refused_unsent(self, gmail_settings: Any) -> None:
        with _door(ConnectorType.APPLE_EMAIL), pytest.raises(BaseAPIException) as refused:
            await mail_settings.delete_filter(USER, "f9")

        assert refusal_code_of(refused.value) == NOT_SUPPORTED_BY_PROVIDER
        gmail_settings.delete_filter.assert_not_awaited()

    async def test_a_deletion_whose_answer_is_lost_is_said_unknown(
        self, gmail_settings: Any
    ) -> None:
        gmail_settings.delete_filter.side_effect = httpx.ReadTimeout("lost")

        with _door(), pytest.raises(BaseAPIException) as caught:
            await mail_settings.delete_filter(USER, "f9")

        assert refusal_code_of(caught.value) == OUTCOME_UNKNOWN

    async def test_a_system_label_is_never_applied_by_a_filter(self, gmail_settings: Any) -> None:
        request = NewFilter(sender="x@example.org", add_label_id="TRASH", idempotency_key=uuid4())
        with _door(), pytest.raises(BaseAPIException) as refused:
            await mail_settings.create_filter(USER, request)

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        gmail_settings.create_filter.assert_not_awaited()

    def test_a_filter_matches_something_and_does_something(self) -> None:
        with pytest.raises(ValidationError):
            NewFilter(archive=True, idempotency_key=uuid4())
        with pytest.raises(ValidationError):
            NewFilter(sender="x@example.org", idempotency_key=uuid4())


class TestElsewhere:
    async def test_they_are_refused_unsent(self, gmail_settings: Any) -> None:
        with _door(ConnectorType.APPLE_EMAIL), pytest.raises(BaseAPIException) as refused:
            await mail_settings.read_vacation(USER, PARIS)

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        gmail_settings.get_vacation.assert_not_awaited()


def _outlook(**answers: Any) -> tuple[Any, Any]:
    """A door on Outlook, whose client speaks the settings' vocabulary itself."""
    mailbox = MagicMock(spec=MicrosoftOutlookClient)
    for name, answer in answers.items():
        setattr(
            mailbox,
            name,
            AsyncMock(side_effect=answer) if _raises(answer) else AsyncMock(return_value=answer),
        )
    mailbox.is_system_label = lambda name: False

    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=mailbox, connector_type=ConnectorType.MICROSOFT_OUTLOOK, preferred_name=None
        )

    return mailbox, patch.object(mail_settings, "open_tool_client", opened)


def _raises(answer: Any) -> bool:
    return isinstance(answer, Exception) or (
        isinstance(answer, type) and issubclass(answer, Exception)
    )


class TestOutlook:
    async def test_the_responder_reads_in_the_person_s_days(self, gmail_settings: Any) -> None:
        mailbox, door = _outlook(
            get_vacation={
                "enableAutoReply": True,
                "responseSubject": "",
                "responseBodyPlainText": "Away",
                "startTime": _millis(date(2027, 7, 2)),
                "endTime": _millis(date(2027, 7, 16)),
            }
        )

        with door:
            vacation = await mail_settings.read_vacation(USER, PARIS)

        assert (vacation.enabled, vacation.body) == (True, "Away")
        assert (vacation.start_date, vacation.end_date) == (date(2027, 7, 2), date(2027, 7, 15))
        gmail_settings.get_vacation.assert_not_awaited()

    async def test_the_responder_is_set_on_the_same_instants(self, gmail_settings: Any) -> None:
        mailbox, door = _outlook(update_vacation={"enableAutoReply": True})
        change = VacationChange(
            enabled=True, body="Away", start_date=date(2027, 7, 2), end_date=date(2027, 7, 15)
        )

        with door:
            await mail_settings.set_vacation(USER, PARIS, change)

        sent = mailbox.update_vacation.await_args.kwargs
        assert sent["start_time_ms"] == _millis(date(2027, 7, 2))
        assert sent["end_time_ms"] == _millis(date(2027, 7, 16))

    async def test_what_outlook_cannot_hold_is_said_by_name(self, gmail_settings: Any) -> None:
        mailbox, door = _outlook(update_vacation=MailboxSettingNotHeldError())
        change = VacationChange(enabled=True, subject="Away", body="Away")

        with door, pytest.raises(BaseAPIException) as refused:
            await mail_settings.set_vacation(USER, PARIS, change)

        assert refusal_code_of(refused.value) == NOT_SUPPORTED_BY_PROVIDER

    async def test_a_connection_without_the_right_asks_for_a_reconnection(
        self, gmail_settings: Any
    ) -> None:
        mailbox, door = _outlook(get_vacation=MailboxSettingsNotGrantedError())

        with door, pytest.raises(BaseAPIException) as refused:
            await mail_settings.read_vacation(USER, PARIS)

        assert refusal_code_of(refused.value) == RECONNECT_REQUIRED

    async def test_a_rule_says_its_name_and_whether_it_can_go(self, gmail_settings: Any) -> None:
        rule = {
            "id": "r1",
            "name": "Bills",
            "read_only": True,
            "criteria": {"from": "ana@example.org"},
            "action": {"addLabelIds": ["Bills"], "removeLabelIds": ["UNREAD"]},
        }
        mailbox, door = _outlook(list_filters={"filter": [rule]})

        with door:
            listed = (await mail_settings.list_filters(USER)).filters[0]

        assert (listed.name, listed.read_only) == ("Bills", True)
        assert (listed.sender, listed.add_label_ids, listed.mark_read) == (
            "ana@example.org",
            ["Bills"],
            True,
        )

    async def test_a_rule_is_created_once_per_submission(self, gmail_settings: Any) -> None:
        made = {"id": "r1", "name": "x", "criteria": {}, "action": {}}
        mailbox, door = _outlook(create_filter=made)
        request = NewFilter(sender="a@example.org", mark_read=True, idempotency_key=str(uuid4()))

        with door:
            await mail_settings.create_filter(USER, request)
            with pytest.raises(BaseAPIException):
                await mail_settings.create_filter(USER, request)

        mailbox.create_filter.assert_awaited_once()

    async def test_a_rule_is_deleted_by_its_id(self, gmail_settings: Any) -> None:
        mailbox, door = _outlook(delete_filter=None)

        with door:
            await mail_settings.delete_filter(USER, "r1")

        mailbox.delete_filter.assert_awaited_once_with("r1")
