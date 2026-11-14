"""The one door every e-mail writer reads the person's style through (ADR-383)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.constants import (
    WRITING_STYLE_MAIL_HEAD_CHARS,
    WRITING_STYLE_MAIL_TAIL_CHARS,
    WRITING_STYLE_MIN_SENT_MAILS,
    WRITING_STYLE_PROFILE_MAX_CHARS,
    WRITING_STYLE_READ_CONCURRENCY,
)
from src.core.exceptions import UsageLimitExceededError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.emails import writing_style as door
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.models import ConnectorType
from src.domains.writing_style.repository import StoredStyle

pytestmark = pytest.mark.unit
#: The door itself, taken at import: this folder's conftest stands a stub in for every
#: OTHER test, which reads no style unless it says so.
writing_style_for = door.writing_style_for
USER = uuid4()
NOW = datetime(2026, 11, 13, 9, tzinfo=UTC)


def _row(profile: str | None, *, age_days: int = 1, encrypted: str | None = None) -> Any:
    return SimpleNamespace(
        profile_encrypted=(
            encrypted if encrypted is not None else (encrypt_data(profile) if profile else None)
        ),
        mails_read=12,
        built_at=NOW - timedelta(days=age_days),
    )


class _World:
    """The door's outside: the stored row, the sent folder and the model, all recorded."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        stored: StoredStyle | None,
        sent: Sequence[Mapping[str, Any]] | None = (),
        answer: str | BaseException = "Writes « Salut », signs « Seb ».",
    ) -> None:
        self.stored = stored
        self.sent = sent
        self.answer = answer
        self.saved: list[tuple[str | None, int]] = []
        self.reads = 0
        self.asked: list[list[str]] = []
        self.recorded: list[tuple[str, bool]] = []
        monkeypatch.setattr(door, "_now", lambda: NOW)
        monkeypatch.setattr(door, "_read_stored", self._read_stored)
        monkeypatch.setattr(door, "_save", self._save)
        monkeypatch.setattr(door, "_read_sent", self._read_sent)
        monkeypatch.setattr(door, "_ask_model", self._ask_model)
        monkeypatch.setattr(door, "_record_read", self._record)

    async def _read_stored(self, user_id: UUID) -> StoredStyle | None:
        return self.stored

    async def _save(self, user_id: UUID, profile: str | None, mails_read: int) -> None:
        self.saved.append((profile, mails_read))

    async def _read_sent(self, user_id: UUID, count: int) -> list[Mapping[str, Any]] | None:
        self.reads += 1
        await asyncio.sleep(0)
        return None if self.sent is None else list(self.sent)

    async def _ask_model(self, samples: list[str], user_id: UUID, config: Any) -> str:
        self.asked.append(samples)
        await asyncio.sleep(0)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    def _record(self, *, succeeded: bool, duration_ms: int) -> None:
        self.recorded.append(("writing_style:email", succeeded))


def _mails(count: int) -> list[dict[str, str]]:
    return [{"id": str(i), "body": f"Salut {i},\n\nOk.\n\n++\nSeb"} for i in range(count)]


async def test_no_account_and_a_switched_off_account_read_no_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=False, row=_row("x", age_days=99)))

    assert await writing_style_for(None, config=None) is None
    assert await writing_style_for(USER, config=None) is None
    assert world.reads == 0 and world.saved == []


async def test_a_fresh_profile_is_served_without_reading_the_mailbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=_row("Signs « Seb ».")))

    assert await writing_style_for(str(USER), config=None) == "Signs « Seb »."
    assert world.reads == 0 and world.asked == []


async def test_a_fresh_empty_profile_is_built_and_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Built, nothing learned: the sent folder is not read again before it is due (ADR-248)."""
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=_row(None)))

    assert await writing_style_for(USER, config=None) is None
    assert world.reads == 0


async def test_a_missing_or_stale_profile_is_learned_kept_and_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = settings.writing_style_max_age_days + 1
    for stored in (
        StoredStyle(enabled=True, row=None),
        StoredStyle(enabled=True, row=_row("old", age_days=stale)),
    ):
        world = _World(monkeypatch, stored=stored, sent=_mails(5))

        assert await writing_style_for(USER, config=None) == ("Writes « Salut », signs « Seb ».")
        assert world.reads == 1 and len(world.asked[0]) == 5
        assert world.saved == [("Writes « Salut », signs « Seb ».", 5)]
        assert world.recorded == [("writing_style:email", True)]


async def test_a_profile_that_cannot_be_read_back_is_learned_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=_row(None, encrypted="not-a-fernet-token")),
        sent=_mails(4),
    )

    assert await writing_style_for(USER, config=None) is not None
    assert world.reads == 1


async def test_too_few_sent_mails_teach_nothing_and_ask_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(WRITING_STYLE_MIN_SENT_MAILS - 1) + [{"id": "x", "body": "   "}],
    )

    assert await writing_style_for(USER, config=None) is None
    assert world.asked == []
    assert world.saved == [(None, WRITING_STYLE_MIN_SENT_MAILS - 1)]


async def test_no_mailbox_learns_nothing_and_keeps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=None)

    assert await writing_style_for(USER, config=None) is None
    assert world.saved == [] and world.asked == []


async def test_a_failed_learning_drafts_without_style_and_keeps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer=RuntimeError("model down"),
    )

    assert await writing_style_for(USER, config=None) is None
    assert world.saved == []


async def test_a_spending_ceiling_is_said_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer=UsageLimitExceededError(limit_name="cycle_tokens", reason="ceiling"),
    )

    with pytest.raises(UsageLimitExceededError):
        await writing_style_for(USER, config=None)


async def test_a_long_profile_is_kept_within_its_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer="x" * (WRITING_STYLE_PROFILE_MAX_CHARS + 50),
    )

    served = await writing_style_for(USER, config=None)

    assert served is not None and len(served) == WRITING_STYLE_PROFILE_MAX_CHARS
    assert world.saved[0][0] == served


async def test_an_assist_files_the_read_of_the_mailbox_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside a turn no runtime names the reader: the caller's own filing is used."""
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=_mails(5))
    opened: list[str] = []

    @asynccontextmanager
    async def reading() -> AsyncIterator[None]:
        opened.append("mail")
        yield

    assert await writing_style_for(USER, config=None, reading=reading) is not None
    assert opened == ["mail"] and world.recorded == []


async def test_a_failed_read_of_the_sent_folder_is_filed_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=_mails(5))

    async def refused(user_id: UUID, count: int) -> list[Mapping[str, Any]] | None:
        raise ConnectionError("mailbox down")

    monkeypatch.setattr(door, "_read_sent", refused)

    assert await writing_style_for(USER, config=None) is None
    assert world.recorded == [("writing_style:email", False)] and world.saved == []


async def test_drafts_asked_together_learn_once(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=_mails(5))

    served = await asyncio.gather(*(writing_style_for(USER, config=None) for _ in range(4)))

    assert len(set(served)) == 1 and served[0] is not None
    assert world.reads == 1 and len(world.asked) == 1


class _Mailbox:
    """A mailbox as the door reads it: a listing, then — where the listing carries
    previews only — each message, which takes the longer the earlier it was listed."""

    def __init__(self, *, whole: bool, listed: int, unreadable: str | None = None) -> None:
        self.SEARCH_HITS_ARE_WHOLE = whole
        self._listed, self._unreadable = listed, unreadable
        self.asked: list[tuple[str, int, bool]] = []
        self.started: list[str] = []
        self.reading = 0
        self.widest = 0

    async def search_emails(
        self, query: str, *, max_results: int, use_cache: bool
    ) -> dict[str, Any]:
        self.asked.append((query, max_results, use_cache))
        hits = [{"id": f"m{index}", "body": f"listed {index}"} for index in range(self._listed)]
        return {"messages": hits[:max_results]}

    async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
        assert use_cache is False
        self.started.append(message_id)
        self.reading += 1
        self.widest = max(self.widest, self.reading)
        try:
            for _turn in range(self._listed - int(message_id[1:])):
                await asyncio.sleep(0)
            if message_id == self._unreadable:
                raise RuntimeError("down")
            return {"id": message_id, "body": f"whole {message_id}"}
        finally:
            self.reading -= 1


def _open(monkeypatch: pytest.MonkeyPatch, opened: object) -> None:
    @asynccontextmanager
    async def door_to_the_mailbox(category: str, user_id: UUID) -> AsyncIterator[object]:
        assert (category, user_id) == ("email", USER)
        yield opened

    monkeypatch.setattr(door, "open_active_client", door_to_the_mailbox)


def _outlook(mailbox: _Mailbox) -> ActiveClient:
    return ActiveClient(mailbox, ConnectorType.MICROSOFT_OUTLOOK, None)


async def test_a_listing_of_whole_messages_is_the_read(monkeypatch: pytest.MonkeyPatch) -> None:
    mailbox = _Mailbox(whole=True, listed=30)
    _open(monkeypatch, _outlook(mailbox))

    sent = await door._read_sent(USER, 12)

    assert sent is not None and [mail["body"] for mail in sent] == [
        f"listed {index}" for index in range(12)
    ]
    assert mailbox.asked == [("in:sent", 12, False)] and mailbox.started == []


async def test_a_listing_of_previews_is_read_a_few_messages_at_a_time_in_its_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One at a time, fifty reads stood between the person and their first draft; all
    at once, they would pass what one mailbox bears."""
    listed = WRITING_STYLE_READ_CONCURRENCY * 3
    mailbox = _Mailbox(whole=False, listed=listed)
    _open(monkeypatch, _outlook(mailbox))

    sent = await door._read_sent(USER, listed)

    # The earliest listed is the slowest read: the order kept is the listing's.
    assert sent is not None and [mail["body"] for mail in sent] == [
        f"whole m{index}" for index in range(listed)
    ]
    assert mailbox.widest == WRITING_STYLE_READ_CONCURRENCY


async def test_a_message_that_cannot_be_read_fails_the_read_and_stops_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A style learned from what an outage left would be kept for months: the learning
    fails as a whole, and the next e-mail written is the retry."""
    listed = WRITING_STYLE_READ_CONCURRENCY * 3
    mailbox = _Mailbox(whole=False, listed=listed, unreadable=f"m{listed - 1}")
    _open(monkeypatch, _outlook(mailbox))

    with pytest.raises(RuntimeError):
        await door._read_sent(USER, listed)

    assert mailbox.reading == 0


async def test_a_failed_read_leaves_the_messages_not_yet_started_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed = WRITING_STYLE_READ_CONCURRENCY * 3
    mailbox = _Mailbox(
        whole=False, listed=listed, unreadable=f"m{WRITING_STYLE_READ_CONCURRENCY - 1}"
    )
    _open(monkeypatch, _outlook(mailbox))

    with pytest.raises(RuntimeError):
        await door._read_sent(USER, listed)

    assert mailbox.reading == 0 and len(mailbox.started) < listed


async def test_an_account_with_no_mailbox_has_nothing_to_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(monkeypatch, ClientUnavailable.NO_CONNECTOR)

    assert await door._read_sent(USER, 12) is None


def test_a_sample_keeps_the_opening_and_the_end_of_a_long_mail() -> None:
    head = "Salut Paul,\n" + "a" * WRITING_STYLE_MAIL_HEAD_CHARS
    tail = "b" * WRITING_STYLE_MAIL_TAIL_CHARS + "\n++\nSeb"
    samples = door.sent_samples([{"body": head + "MIDDLE" * 500 + tail}, {"body": "Short."}])

    assert samples[0].startswith("Salut Paul,") and samples[0].endswith("++\nSeb")
    assert "MIDDLE" not in samples[0] and "[…]" in samples[0]
    assert samples[1] == "Short."


def test_empty_bodies_are_no_samples() -> None:
    assert door.sent_samples([{"body": ""}, {"body": "  \n "}, {}]) == []


def test_the_stored_profile_is_encrypted() -> None:
    sealed = door.seal("Signs « Seb ».")
    assert sealed is not None and "Seb" not in sealed and decrypt_data(sealed) == "Signs « Seb »."
    assert door.seal(None) is None


def test_each_writer_reads_its_block_only_when_a_profile_exists() -> None:
    for render in (door.reply_block, door.compose_block):
        assert render(None) == "" and render("  ") == ""
        block = render("Signs « Seb ».")
        assert block.endswith("\nSigns « Seb ».\n\n") and "never their facts" in block
    assert door.reply_block("x") != door.compose_block("x")


def test_the_profile_request_reads_the_mails_as_data() -> None:
    messages = door.profile_messages(["Salut Paul,\n\n++\nSeb", "Hello Léa"])

    assert "Never say WHAT they wrote about" in str(messages[0].content)
    data = str(messages[-1].content)
    assert "Salut Paul" in data and "Hello Léa" in data and "\n\n---\n\n" in data
    assert "Salut Paul" not in str(messages[0].content)  # the static part holds no mail
