"""The latest texts a contact's numbers sent, read on PostgreSQL (2026-11-07).

The archive keys a sender by an owner-blind digest of its spelling, so a number cannot be looked up
under every spelling it may have arrived under. The senders are read newest first under the
directory's bound and matched by the rule the SMS page names a sender with (``same_line`` without
inferring a country): a contact written nationally finds texts received in E.164, and a named
sender never answers a number. A bound that hid older senders is said.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.ingestion.models import IngestionToken
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.relation_reader import texts_from_lines
from src.domains.users.models import User
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC).replace(microsecond=0)
LINE = "+33612345678"
NATIONAL = "06 12 34 56 78"


@pytest.fixture(autouse=True)
def _sms_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sms_enabled", True)


def _text(sender: str = LINE, *, minutes: int = 0, body: str = "On se voit demain ?") -> Any:
    return message(sender=sender, body=body, date=(NOW - timedelta(minutes=minutes)).isoformat())


async def _receive(session: AsyncSession, user: User, *texts: Any) -> None:
    await SmsIngestionService(session).ingest(await authority(session, user), list(texts))


async def _read(session: AsyncSession, owner: UUID, numbers: list[str], *, limit: int = 5) -> Any:
    return await texts_from_lines(session, owner, numbers, limit=limit)


class TestWhichTextsAnswer:
    async def test_a_number_written_nationally_finds_the_texts_received_in_e164(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(db_session, test_user, _text(body="Received in E.164"))

        read = await _read(db_session, test_user.id, [NATIONAL])

        assert [item.body for item in read.texts] == ["Received in E.164"]

    async def test_a_number_in_e164_finds_the_texts_received_nationally(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(db_session, test_user, _text("0612345678", body="Received nationally"))

        read = await _read(db_session, test_user.id, ["+33 6 12 34 56 78"])

        assert [item.body for item in read.texts] == ["Received nationally"]

    async def test_two_spellings_of_one_line_are_read_together(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(
            db_session,
            test_user,
            _text(LINE, minutes=3, body="third"),
            _text("06 12 34 56 78", minutes=1, body="first"),
            _text(LINE, minutes=2, body="second"),
        )

        read = await _read(db_session, test_user.id, [NATIONAL])

        assert [item.body for item in read.texts] == ["first", "second", "third"]

    async def test_a_named_sender_never_answers_a_number(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(db_session, test_user, _text("BANK"), _text("0612345678 Ana"))

        read = await _read(db_session, test_user.id, [NATIONAL])

        assert read.texts == []

    async def test_another_line_is_left_out(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(db_session, test_user, _text("+33698765432"))

        assert (await _read(db_session, test_user.id, [NATIONAL])).texts == []

    async def test_another_account_texts_are_never_read(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        other = User(id=uuid4(), email=f"other-{uuid4()}@example.test", is_active=True)
        db_session.add(other)
        await db_session.flush()
        theirs = await authority(db_session, other)
        await SmsIngestionService(db_session).ingest(theirs, [_text(body="Someone else's")])
        # The seeding helper mints one token hash: the second account needs its own.
        await db_session.execute(
            update(IngestionToken)
            .where(IngestionToken.id == theirs.token_id)
            .values(token_hash=f"spent-{uuid4()}")
        )
        await _receive(db_session, test_user, _text("+33698765432", body="Mine"))

        assert (await _read(db_session, test_user.id, [NATIONAL])).texts == []


class TestWhatTheListHolds:
    async def test_the_latest_come_first_and_no_more_than_asked(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        minutes = [30, 10, 50, 20, 40, 60]
        await _receive(db_session, test_user, *(_text(minutes=m, body=f"m{m}") for m in minutes))

        read = await _read(db_session, test_user.id, [NATIONAL], limit=5)

        assert [item.body for item in read.texts] == ["m10", "m20", "m30", "m40", "m50"]

    async def test_a_text_says_when_and_what_never_who(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        await _receive(db_session, test_user, _text(minutes=7, body="Call me back"))

        (item,) = (await _read(db_session, test_user.id, [NATIONAL])).texts

        assert item.at == NOW - timedelta(minutes=7)
        assert item.body == "Call me back"
        assert not hasattr(item, "sender")
        assert "612345678" not in repr(item)


class TestHowFarItRead:
    async def test_a_bound_that_hid_older_senders_is_stated(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "sms_directory_max_contacts", 1)
        await _receive(
            db_session, test_user, _text("+33698765432", minutes=1), _text(LINE, minutes=5)
        )

        read = await _read(db_session, test_user.id, [NATIONAL])

        assert read.texts == []
        assert read.cut is True

    async def test_a_whole_read_claims_no_cut(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "sms_directory_max_contacts", 2)
        await _receive(db_session, test_user, _text("+33698765432"), _text(LINE, minutes=5))

        read = await _read(db_session, test_user.id, [NATIONAL])

        assert len(read.texts) == 1
        assert read.cut is False


class TestWhenItHasNothingToSay:
    async def test_an_archive_with_no_text_has_nothing_to_say(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        assert await _read(db_session, test_user.id, [NATIONAL]) is None

    async def test_the_switched_off_capability_refuses_the_read(
        self,
        db_session: AsyncSession,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _receive(db_session, test_user, _text())
        monkeypatch.setattr(settings, "sms_enabled", False)

        with pytest.raises(AuthorizationError) as refused:
            await _read(db_session, test_user.id, [NATIONAL])

        assert refused.value.detail["error_code"] == "CAPABILITY_DISABLED"
