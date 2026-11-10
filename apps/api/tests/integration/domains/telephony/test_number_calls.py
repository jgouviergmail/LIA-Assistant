"""The latest calls LIA placed to a contact's numbers, read on PostgreSQL (2026-11-07).

A callee's number is stored encrypted and keyed by nothing a query could match, so the latest
third-party calls are read newest first under a bound and matched by the telephony domain's own
rule (``same_line``): a contact written nationally finds the calls dialled in E.164. Only the calls
LIA placed to someone else answer, never the owner's own nor a verification, and the number never
leaves the reader. How far it read is stated when the bound hid older calls.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ExternalServiceError
from src.core.security import encrypt_data
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.number_calls import calls_to_lines
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
LINE = "+33612345678"
NATIONAL = "06 12 34 56 78"


@pytest.fixture(autouse=True)
def _telephony_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_enabled", True)
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)


def _call(
    owner: UUID,
    *,
    number: str = LINE,
    minutes: int = 0,
    kind: CallKind = CallKind.THIRD_PARTY,
    **fields: Any,
) -> PhoneCall:
    return PhoneCall(
        id=uuid4(),
        user_id=owner,
        callee_display="Ana",
        callee_phone=encrypt_data(number),
        objective=fields.pop("objective", "Book a table for Saturday"),
        status=fields.pop("status", PhoneCallStatus.COMPLETED),
        call_kind=kind,
        created_at=NOW - timedelta(minutes=minutes),
        **fields,
    )


async def _seed(session: AsyncSession, *calls: PhoneCall) -> None:
    session.add_all(calls)
    await session.flush()


async def _read(
    session: AsyncSession, owner: UUID, numbers: list[str], *, limit: int = 5, scan: int = 50
) -> Any:
    return await calls_to_lines(session, owner, numbers, limit=limit, scan=scan)


class TestWhichCallsAnswer:
    async def test_a_number_written_nationally_finds_the_calls_dialled_in_e164(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        call = _call(test_user.id)
        await _seed(async_session, call)

        read = await _read(async_session, test_user.id, [NATIONAL])

        assert [item.id for item in read.calls] == [call.id]

    async def test_a_number_in_e164_finds_the_calls_dialled_nationally(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        call = _call(test_user.id, number="0612345678")
        await _seed(async_session, call)

        read = await _read(async_session, test_user.id, ["+33 6 12 34 56 78"])

        assert [item.id for item in read.calls] == [call.id]

    async def test_with_no_country_declared_the_two_spellings_still_meet(
        self,
        async_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
        call = _call(test_user.id)
        await _seed(async_session, call)

        read = await _read(async_session, test_user.id, [NATIONAL])

        assert [item.id for item in read.calls] == [call.id]

    async def test_another_line_is_left_out(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, _call(test_user.id, number="+33698765432"))

        read = await _read(async_session, test_user.id, [NATIONAL])

        assert read.calls == []

    async def test_only_the_calls_lia_placed_to_someone_else_answer(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        theirs = _call(test_user.id, minutes=3)
        await _seed(
            async_session,
            theirs,
            _call(test_user.id, kind=CallKind.SELF, minutes=1),
            _call(test_user.id, kind=CallKind.VERIFICATION, minutes=2),
        )

        read = await _read(async_session, test_user.id, [LINE])

        assert [item.id for item in read.calls] == [theirs.id]

    async def test_another_account_calls_are_never_read(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        other = User(id=uuid4(), email=f"other-{uuid4()}@example.test", is_active=True)
        async_session.add(other)
        await async_session.flush()
        await _seed(async_session, _call(other.id), _call(test_user.id, number="+33698765432"))

        read = await _read(async_session, test_user.id, [LINE])

        assert read.calls == []

    async def test_any_of_the_numbers_finds_its_calls(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        mobile, office = _call(test_user.id, minutes=1), _call(
            test_user.id, number="+33140000000", minutes=2
        )
        await _seed(async_session, mobile, office)

        read = await _read(async_session, test_user.id, ["01 40 00 00 00", NATIONAL])

        assert [item.id for item in read.calls] == [mobile.id, office.id]


class TestWhatTheListHolds:
    async def test_the_latest_come_first_and_no_more_than_asked(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        calls = [_call(test_user.id, minutes=minutes) for minutes in (30, 10, 50, 20, 40, 60)]
        await _seed(async_session, *calls)

        read = await _read(async_session, test_user.id, [LINE], limit=5)

        newest_first = sorted(calls, key=lambda call: call.created_at, reverse=True)
        assert [item.id for item in read.calls] == [call.id for call in newest_first[:5]]

    async def test_a_line_says_when_how_it_went_and_what_for(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        call = _call(
            test_user.id,
            minutes=5,
            objective="Move Tuesday's appointment",
            outcome=PhoneCallOutcome.OBJECTIVE_MET,
            call_seconds=Decimal("93.50"),
        )
        unanswered = _call(test_user.id, minutes=9, status=PhoneCallStatus.NO_ANSWER)
        await _seed(async_session, call, unanswered)

        first, second = (await _read(async_session, test_user.id, [LINE])).calls

        assert first.at == NOW - timedelta(minutes=5)
        assert first.purpose == "Move Tuesday's appointment"
        assert first.outcome == PhoneCallOutcome.OBJECTIVE_MET
        assert first.status == PhoneCallStatus.COMPLETED
        assert first.seconds == 93.5
        assert second.status == PhoneCallStatus.NO_ANSWER
        assert second.outcome is None
        assert second.seconds is None

    async def test_the_number_never_leaves_the_reader(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, _call(test_user.id))

        (item,) = (await _read(async_session, test_user.id, [NATIONAL])).calls

        values = [str(getattr(item, field.name)) for field in dataclasses.fields(item)]
        assert not any("612345678" in value for value in values)
        assert {field.name for field in dataclasses.fields(item)} == {
            "id",
            "at",
            "status",
            "outcome",
            "seconds",
            "purpose",
        }


class TestHowFarItRead:
    async def test_a_bound_that_hid_older_calls_is_stated(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(
            async_session,
            _call(test_user.id, number="+33698765432", minutes=1),
            _call(test_user.id, number="+33698765432", minutes=2),
            _call(test_user.id, minutes=3),
        )

        read = await _read(async_session, test_user.id, [LINE], scan=2)

        assert read.calls == []
        assert read.cut is True

    async def test_a_full_list_within_the_bound_claims_no_cut(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, *(_call(test_user.id, minutes=m) for m in (1, 2, 3)))

        read = await _read(async_session, test_user.id, [LINE], limit=1, scan=2)

        assert len(read.calls) == 1
        assert read.cut is False

    async def test_a_whole_read_claims_no_cut(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, _call(test_user.id))

        assert (await _read(async_session, test_user.id, [LINE], scan=1)).cut is False


class TestWhenItHasNothingToSay:
    async def test_an_account_lia_never_called_anyone_for_has_nothing_to_say(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, _call(test_user.id, kind=CallKind.SELF))

        assert await _read(async_session, test_user.id, [LINE]) is None

    async def test_calls_to_someone_else_still_leave_something_to_say(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        await _seed(async_session, _call(test_user.id, number="+33698765432"))

        read = await _read(async_session, test_user.id, [LINE])

        assert read is not None
        assert read.calls == []

    async def test_the_switched_off_capability_refuses_the_read(
        self,
        async_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _seed(async_session, _call(test_user.id))
        monkeypatch.setattr(settings, "telephony_enabled", False)

        with pytest.raises(AuthorizationError) as refused:
            await _read(async_session, test_user.id, [LINE])

        assert refused.value.detail["error_code"] == "CAPABILITY_DISABLED"

    async def test_a_number_that_cannot_be_read_fails_the_read_rather_than_hiding_a_call(
        self, async_session: AsyncSession, test_user: User
    ) -> None:
        broken = _call(test_user.id)
        broken.callee_phone = "not-a-cipher"
        await _seed(async_session, broken)

        with pytest.raises(ExternalServiceError):
            await _read(async_session, test_user.id, [LINE])
