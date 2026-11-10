"""What a contact and the person exchanged by phone (2026-11-07).

The calls LIA placed to the contact's numbers and the texts those numbers sent, read on LIA's own
records, each on a session of its own so one failing leaves the other standing. A source says why
it has nothing: no number to look under, a capability switched off or no record of that kind at
all, a read that failed — never shown as nothing found. A line never carries the number.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.constants import WORKBENCH_CONTACT_HISTORY_CALLS_SCAN, WORKBENCH_CONTACT_HISTORY_ITEMS
from src.core.exceptions import AuthorizationError, ExternalServiceError, ResourceConflictError
from src.domains.sms.constants import SMS_CARD_EXCERPT_CHARS
from src.domains.sms.relation_reader import LineText, LineTexts
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.number_calls import CallsToLines, PlacedCall
from src.domains.workbench import contacts_lines

pytestmark = pytest.mark.unit

USER = uuid4()
AT = datetime(2026, 11, 7, 9, 30, tzinfo=UTC)
PHONES = ["06 12 34 56 78"]
SESSION = object()


def _placed(**fields: Any) -> PlacedCall:
    return PlacedCall(
        **{
            "id": uuid4(),
            "at": AT,
            "status": PhoneCallStatus.COMPLETED,
            "outcome": PhoneCallOutcome.OBJECTIVE_MET,
            "seconds": 93.5,
            "purpose": "Move Tuesday's appointment",
            **fields,
        }
    )


def _text(body: str = "Call me back", **fields: Any) -> LineText:
    return LineText(**{"id": uuid4(), "at": AT, "body": body, **fields})


@contextlib.asynccontextmanager
async def _session() -> AsyncIterator[object]:
    yield SESSION


@pytest.fixture
def readers() -> Any:
    calls = AsyncMock(return_value=CallsToLines(calls=[], cut=False))
    texts = AsyncMock(return_value=LineTexts(texts=[], cut=False))
    with (
        patch.object(contacts_lines, "get_db_context", _session),
        patch.object(contacts_lines, "calls_to_lines", calls),
        patch.object(contacts_lines, "texts_from_lines", texts),
    ):
        yield SimpleNamespace(calls=calls, texts=texts)


async def _history(phones: list[str] = PHONES) -> contacts_lines.PhoneHistory:
    return await contacts_lines.phone_history(USER, phones)


def _switched_off() -> AuthorizationError:
    return AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED", "capability": "sms"})


class TestWhatIsAsked:
    async def test_a_contact_with_no_number_asks_neither_record(self, readers: Any) -> None:
        history = await _history([])

        assert (history.telephony, history.sms) == ("not_requested", "not_requested")
        readers.calls.assert_not_awaited()
        readers.texts.assert_not_awaited()

    async def test_each_record_is_asked_for_the_numbers_as_saved(self, readers: Any) -> None:
        await _history(["06 12 34 56 78", "+33 1 40 00 00 00"])

        readers.calls.assert_awaited_once_with(
            SESSION,
            USER,
            ["06 12 34 56 78", "+33 1 40 00 00 00"],
            limit=WORKBENCH_CONTACT_HISTORY_ITEMS,
            scan=WORKBENCH_CONTACT_HISTORY_CALLS_SCAN,
        )
        readers.texts.assert_awaited_once_with(
            SESSION,
            USER,
            ["06 12 34 56 78", "+33 1 40 00 00 00"],
            limit=WORKBENCH_CONTACT_HISTORY_ITEMS,
        )


class TestTheCalls:
    async def test_a_line_says_when_how_it_went_and_what_for(self, readers: Any) -> None:
        call = _placed()
        readers.calls.return_value = CallsToLines(calls=[call], cut=False)

        history = await _history()

        (line,) = history.calls
        assert line.id == call.id
        assert line.at == AT
        assert line.status == PhoneCallStatus.COMPLETED
        assert line.outcome == PhoneCallOutcome.OBJECTIVE_MET
        assert line.seconds == 93.5
        assert line.purpose == "Move Tuesday's appointment"
        assert history.telephony == "used"

    async def test_how_far_it_read_is_stated(self, readers: Any) -> None:
        readers.calls.return_value = CallsToLines(calls=[], cut=True)

        history = await _history()

        assert history.calls_cut is True
        assert history.calls_window == WORKBENCH_CONTACT_HISTORY_CALLS_SCAN

    async def test_no_call_on_record_has_nothing_to_say(self, readers: Any) -> None:
        readers.calls.return_value = None

        assert (await _history()).telephony == "disabled"

    async def test_telephony_switched_off_is_said(self, readers: Any) -> None:
        readers.calls.side_effect = _switched_off()

        assert (await _history()).telephony == "disabled"


class TestTheTexts:
    async def test_a_short_text_is_shown_whole(self, readers: Any) -> None:
        text = _text("On se voit demain ?")
        readers.texts.return_value = LineTexts(texts=[text], cut=False)

        history = await _history()

        (line,) = history.texts
        assert (line.id, line.at, line.excerpt, line.truncated) == (
            text.id,
            AT,
            "On se voit demain ?",
            False,
        )
        assert history.sms == "used"

    async def test_a_long_text_is_cut_and_says_so(self, readers: Any) -> None:
        body = "x" * (SMS_CARD_EXCERPT_CHARS + 1)
        readers.texts.return_value = LineTexts(texts=[_text(body)], cut=False)

        (line,) = (await _history()).texts

        assert line.excerpt == "x" * SMS_CARD_EXCERPT_CHARS
        assert line.truncated is True

    async def test_how_far_it_read_is_stated(self, readers: Any) -> None:
        readers.texts.return_value = LineTexts(texts=[], cut=True)

        history = await _history()

        assert history.texts_cut is True
        assert history.texts_window == settings.sms_directory_max_contacts

    async def test_an_empty_archive_has_nothing_to_say(self, readers: Any) -> None:
        readers.texts.return_value = None

        assert (await _history()).sms == "disabled"

    async def test_sms_switched_off_is_said(self, readers: Any) -> None:
        readers.texts.side_effect = _switched_off()

        assert (await _history()).sms == "disabled"


class TestAFailedRead:
    @pytest.mark.parametrize(
        "failure",
        [
            OperationalError("SELECT", {}, Exception("statement timeout")),
            ExternalServiceError("sms", detail="SMS_CONTENT_UNAVAILABLE"),
            ResourceConflictError("sms", detail={"error_code": "QUERY_TOO_BROAD"}),
            AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"}),
        ],
        ids=["database", "unreadable", "too_broad", "switch_unknown"],
    )
    async def test_is_never_read_as_nothing_found(self, readers: Any, failure: Exception) -> None:
        readers.texts.side_effect = failure
        readers.calls.return_value = CallsToLines(calls=[_placed()], cut=False)

        history = await _history()

        assert history.sms == "unavailable"
        assert history.texts == []
        assert history.telephony == "used"
        assert len(history.calls) == 1

    async def test_of_the_calls_leaves_the_texts_standing(self, readers: Any) -> None:
        readers.calls.side_effect = ExternalServiceError(
            "telephony", detail="CALL_NUMBER_UNAVAILABLE"
        )
        readers.texts.return_value = LineTexts(texts=[_text()], cut=False)

        history = await _history()

        assert history.telephony == "unavailable"
        assert history.sms == "used"
