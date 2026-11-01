"""Gmail's mailbox settings, by the person's own hand (ADR-369, Task 4.6).

Gmail alone carries them (the descriptor's VACATION and FILTERS): elsewhere
they are refused before anything is sent. The vacation responder is set in
the person's own DAYS — the first one from its midnight, the last one
INCLUDED (Gmail's ``endTime`` is exclusive: the midnight after) — and read back
as the same days. A filter is created once per submission, never applying a
system label; the list says what each one does. Nothing deletes a filter: the
client has no such act (the panel says so).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_settings
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
        close=AsyncMock(),
    )
    with patch.object(mail_settings, "GoogleGmailSettingsClient", MagicMock(return_value=client)):
        yield client


def _door(kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
    mailbox = MagicMock(credentials=object())
    mailbox.is_system_label = lambda name: name.upper() in {"INBOX", "TRASH", "UNREAD"}

    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=mailbox, connector_type=kind, preferred_name=None)

    return patch.object(mail_settings, "open_tool_client", opened)


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
    @pytest.mark.parametrize("kind", [ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.APPLE_EMAIL])
    async def test_they_are_refused_unsent(self, kind: ConnectorType, gmail_settings: Any) -> None:
        with _door(kind), pytest.raises(BaseAPIException) as refused:
            await mail_settings.read_vacation(USER, PARIS)

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        gmail_settings.get_vacation.assert_not_awaited()
