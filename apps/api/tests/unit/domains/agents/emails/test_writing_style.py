"""The one door every e-mail writer reads the person's style through (ADR-383).

Writers READ it; it is learned only at the person's request (amendment 2026-11-16), and
every learning says how it ended.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest

from src.core.constants import (
    WRITING_STYLE_LEARN_WAIT_SECONDS,
    WRITING_STYLE_MAIL_HEAD_CHARS,
    WRITING_STYLE_MAIL_TAIL_CHARS,
    WRITING_STYLE_MIN_SENT_MAILS,
    WRITING_STYLE_PROFILE_MAX_CHARS,
    WRITING_STYLE_READ_CONCURRENCY,
)
from src.core.exceptions import UsageLimitExceededError
from src.core.llm_config_helper import run_bound_seconds
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.emails import writing_style as door
from src.domains.agents.emails.writing_style import (
    LLM_TYPE,
    EmptyStyleProfile,
    Learning,
    LearningOutcome,
    SentMailUnreadable,
    learn_one_at_a_time,
    learn_writing_style,
    learned_record_at,
    learned_since,
)
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.models import ConnectorType
from src.domains.writing_style.repository import StoredStyle
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, SharedFlightResult

pytestmark = pytest.mark.unit
#: The door itself, taken at import: this folder's conftest stands a stub in for every
#: OTHER test, which reads no style unless it says so.
writing_style_for = door.writing_style_for
USER = uuid4()
#: What one provider search answers at most: the agents' per-request ceiling.
_CEILING = 25
NOW = datetime(2026, 11, 16, 9, tzinfo=UTC)
PROFILE = "Writes « Salut », signs « Seb »."


def _row(profile: str | None, *, age_days: int = 1, encrypted: str | None = None) -> Any:
    return SimpleNamespace(
        profile_encrypted=(
            encrypted if encrypted is not None else (encrypt_data(profile) if profile else None)
        ),
        mails_read=12,
        built_at=NOW - timedelta(days=age_days),
    )


def _mails(count: int) -> list[dict[str, str]]:
    return [{"id": str(i), "body": f"Salut {i},\n\nOk.\n\n++\nSeb"} for i in range(count)]


class _SentFolder:
    """A mailbox whose search answers the sent mail whole (Gmail, IMAP), or fails."""

    SEARCH_HITS_ARE_WHOLE = True

    def __init__(self, sent: Sequence[Mapping[str, Any]] | BaseException) -> None:
        self.sent = sent
        self.searches = 0

    async def search_emails(
        self, query: str, *, max_results: int, use_cache: bool, page_token: str | None = None
    ) -> dict[str, Any]:
        self.searches += 1
        if isinstance(self.sent, BaseException):
            raise self.sent
        return {"messages": list(self.sent)[:max_results], "next_page_token": None}


class _World:
    """The door's outside: the stored row, the mailbox, the model, the register.

    ``after_save`` is what a read finds once a save kept nothing (the default: the same
    state as before) — the switch turned off, or the record forgotten, meanwhile.
    """

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        stored: StoredStyle | None,
        sent: Sequence[Mapping[str, Any]] | BaseException | ClientUnavailable = (),
        answer: str | BaseException = PROFILE,
        kept: bool = True,
        after_save: StoredStyle | None | Literal["same"] = "same",
    ) -> None:
        self.stored = stored
        self.answer = answer
        self.kept = kept
        self.after_save = after_save
        self.saved: list[tuple[str | None, int]] = []
        self.replaced: list[datetime | None] = []
        self.asked: list[list[str]] = []
        self.recorded: list[tuple[str, bool]] = []
        self.mailbox = None if isinstance(sent, ClientUnavailable) else _SentFolder(sent)
        self.unavailable = sent if isinstance(sent, ClientUnavailable) else None
        monkeypatch.setattr(door, "_now", lambda: NOW)
        monkeypatch.setattr(door, "_read_stored", self._read_stored)
        monkeypatch.setattr(door, "_save", self._save)
        monkeypatch.setattr(door, "_ask_model", self._ask_model)
        monkeypatch.setattr(door, "_record_read", self._record)
        monkeypatch.setattr(door, "open_active_client", self._open)

    @property
    def searches(self) -> int:
        return self.mailbox.searches if self.mailbox is not None else 0

    @asynccontextmanager
    async def _open(self, category: str, user_id: UUID) -> AsyncIterator[object]:
        assert (category, user_id) == ("email", USER)
        if self.unavailable is not None:
            yield self.unavailable
        else:
            yield ActiveClient(self.mailbox, ConnectorType.GOOGLE_GMAIL, None)

    async def _read_stored(self, user_id: UUID) -> StoredStyle | None:
        if self.saved and self.after_save != "same":
            return self.after_save
        return self.stored

    async def _save(
        self, user_id: UUID, profile: str | None, mails_read: int, replaces: datetime | None
    ) -> bool:
        self.saved.append((profile, mails_read))
        self.replaced.append(replaces)
        return self.kept

    async def _ask_model(self, samples: list[str], user_id: UUID, config: Any) -> str:
        self.asked.append(samples)
        await asyncio.sleep(0)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    def _record(self, *, succeeded: bool, duration_ms: int) -> None:
        self.recorded.append(("writing_style:email", succeeded))


# =============================================================================
# The writers read it, and only read it
# =============================================================================


async def test_no_account_and_a_switched_off_account_read_no_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=False, row=_row("x")))

    assert await writing_style_for(None) is None
    assert await writing_style_for(USER) is None
    assert world.searches == 0 and world.saved == []


async def test_a_learned_profile_is_served_however_old_and_nothing_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It never expires on its own: the person learns it again when they choose."""
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=_row(PROFILE, age_days=400)))

    assert await writing_style_for(str(USER)) == PROFILE
    assert world.searches == 0 and world.asked == []


async def test_nothing_learned_or_too_little_learned_reads_no_style_and_learns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for stored in (StoredStyle(enabled=True, row=None), StoredStyle(enabled=True, row=_row(None))):
        world = _World(monkeypatch, stored=stored, sent=_mails(5))

        assert await writing_style_for(USER) is None
        assert world.searches == 0 and world.asked == [] and world.saved == []


async def test_a_profile_that_cannot_be_read_back_reads_as_nothing_learned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=_row(None, encrypted="not-a-fernet-token")),
        sent=_mails(5),
    )

    assert await writing_style_for(USER) is None
    assert world.searches == 0


# =============================================================================
# Learning, at the person's request
# =============================================================================


async def test_a_learning_reads_the_sent_mail_asks_once_and_keeps_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=_mails(5))

    learning = await learn_writing_style(USER, replaces=None, config=None)

    assert learning == Learning("learned", 5)
    assert world.searches == 1 and len(world.asked) == 1 and len(world.asked[0]) == 5
    assert world.saved == [(PROFILE, 5)] and world.replaced == [None]
    assert world.recorded == [("writing_style:email", True)]


async def test_learning_again_replaces_the_record_it_was_asked_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _row("old")
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=old), sent=_mails(4))

    learning = await learn_writing_style(USER, replaces=old.built_at, config=None)

    assert learning == Learning("learned", 4)
    assert world.saved == [(PROFILE, 4)] and world.replaced == [old.built_at]


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

    learning = await learn_writing_style(USER, replaces=None, config=None, reading=reading)

    assert learning.outcome == "learned"
    assert opened == ["mail"] and world.recorded == []


async def test_too_few_sent_mails_teach_nothing_and_ask_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(WRITING_STYLE_MIN_SENT_MAILS - 1) + [{"id": "x", "body": "   "}],
    )

    learning = await learn_writing_style(USER, replaces=None, config=None)

    assert learning == Learning("too_few", WRITING_STYLE_MIN_SENT_MAILS - 1)
    assert world.asked == []
    assert world.saved == [(None, WRITING_STYLE_MIN_SENT_MAILS - 1)]


async def test_a_switched_off_account_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    for stored in (StoredStyle(enabled=False, row=None), None):
        world = _World(monkeypatch, stored=stored, sent=_mails(5))

        learning = await learn_writing_style(USER, replaces=None, config=None)

        assert learning == Learning("switched_off")
        assert world.searches == 0 and world.saved == [] and world.recorded == []


@pytest.mark.parametrize("after", [StoredStyle(enabled=False, row=None), None])
async def test_a_switch_turned_off_meanwhile_keeps_nothing_and_says_so(
    monkeypatch: pytest.MonkeyPatch, after: StoredStyle | None
) -> None:
    """Off, or the account gone, by the time the result was to be kept."""
    _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        kept=False,
        after_save=after,
    )

    learning = await learn_writing_style(USER, replaces=None, config=None)

    assert learning == Learning("switched_off", 5)


@pytest.mark.parametrize(
    ("now_stands", "asked_on"),
    [
        # Forgotten since the person asked.
        (None, NOW - timedelta(days=2)),
        # Learned again since (another tab, the assistant) — the later record stands.
        (_row("newer", age_days=1, encrypted="sealed"), NOW - timedelta(days=2)),
        # Asked on nothing learned, and a record stands now.
        (_row("newer", age_days=1, encrypted="sealed"), None),
    ],
)
async def test_a_record_changed_since_the_request_is_neither_read_nor_paid_for(
    monkeypatch: pytest.MonkeyPatch, now_stands: Any, asked_on: datetime | None
) -> None:
    """The person's later act stands: nothing is read, asked or written over it."""
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=now_stands), sent=_mails(5))

    learning = await learn_writing_style(USER, replaces=asked_on, config=None)

    assert learning == Learning("superseded")
    assert world.searches == 0 and world.asked == [] and world.saved == []
    assert world.recorded == []


async def test_a_record_forgotten_during_the_learning_stays_forgotten_and_it_is_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forgotten while the mailbox and the model answered: the save keeps nothing over it."""
    old = _row("old")
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=old),
        sent=_mails(5),
        kept=False,
        after_save=StoredStyle(enabled=True, row=None),
    )

    learning = await learn_writing_style(USER, replaces=old.built_at, config=None)

    assert learning == Learning("superseded", 5)
    assert world.replaced == [old.built_at] and len(world.asked) == 1


async def test_a_save_keeps_the_profile_in_place_of_the_record_asked_on_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record the person asked on reaches the conditioned write, sealed profile beside it."""
    calls: list[dict[str, Any]] = []

    class _Repository:
        def __init__(self, db: object) -> None:
            self.db = db

        async def save(self, user_id: UUID, **written: Any) -> bool:
            calls.append({"user_id": user_id, **written})
            return True

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(door, "WritingStyleRepository", _Repository)
    monkeypatch.setattr(door, "get_db_context", session)
    monkeypatch.setattr(door, "_now", lambda: NOW)
    asked_on = NOW - timedelta(days=3)

    assert await door._save(USER, PROFILE, 5, asked_on)

    (call,) = calls
    assert (call["user_id"], call["mails_read"], call["built_at"]) == (USER, 5, NOW)
    assert call["replaces"] == asked_on
    assert decrypt_data(call["profile_encrypted"]) == PROFILE


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (StoredStyle(enabled=True, row=_row(PROFILE, encrypted="sealed")), NOW - timedelta(days=1)),
        (
            StoredStyle(enabled=False, row=_row(PROFILE, encrypted="sealed")),
            NOW - timedelta(days=1),
        ),
        (StoredStyle(enabled=True, row=None), None),
        (None, None),
    ],
)
async def test_a_request_names_the_record_it_is_made_on(
    monkeypatch: pytest.MonkeyPatch, stored: StoredStyle | None, expected: datetime | None
) -> None:
    _World(monkeypatch, stored=stored)

    assert await learned_record_at(USER) == expected


async def test_one_learning_per_account_at_a_time_whichever_surface_asks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings' click and the assistant's card share ONE claim across workers: a
    request arriving meanwhile waits for the first and answers what it kept, paying nothing."""
    flights: list[dict[str, Any]] = []

    async def flight(key: str, **kwargs: Any) -> SharedFlightResult[Learning]:
        flights.append({"key": key, **kwargs})
        return SharedFlightResult(value=await kwargs["build"](), claimed=True, waited=False)

    monkeypatch.setattr(door, "run_shared_flight", flight)
    monkeypatch.setattr(door, "_now", lambda: NOW)
    learned = Learning("learned", 12)

    async def learn() -> Learning:
        return learned

    assert await learn_one_at_a_time(USER, learn) is learned

    (only,) = flights
    assert only["key"] == f"{CLAIM_PREFIX}:writing_style_learn:{USER}"
    assert only["owner_liveness"] is True
    # A second request waits at least as long as the first one's model call may take.
    assert only["wait_budget_s"] == run_bound_seconds(WRITING_STYLE_LEARN_WAIT_SECONDS, LLM_TYPE)
    # What it waits for: a learning kept since THIS request began, read back from its row.
    _World(monkeypatch, stored=StoredStyle(enabled=True, row=_row(PROFILE, age_days=0)))
    assert await only["read_shared"]() == Learning("learned", 12)
    _World(monkeypatch, stored=StoredStyle(enabled=True, row=_row(PROFILE, age_days=1)))
    assert await only["read_shared"]() is None


@pytest.mark.parametrize(
    ("unavailable", "outcome"),
    [
        (ClientUnavailable.NO_CONNECTOR, "no_mailbox"),
        (ClientUnavailable.NO_CLIENT, "no_mailbox"),
        (ClientUnavailable.NO_CREDENTIALS, "reconnect"),
    ],
)
async def test_a_mailbox_that_cannot_be_opened_says_why_and_files_no_read(
    monkeypatch: pytest.MonkeyPatch, unavailable: ClientUnavailable, outcome: LearningOutcome
) -> None:
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=unavailable)

    assert await learn_writing_style(USER, replaces=None, config=None) == Learning(outcome)
    assert world.saved == [] and world.asked == [] and world.recorded == []


async def test_a_mailbox_that_fails_is_said_with_its_cause_and_filed_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = ConnectionError("mailbox down")
    world = _World(monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=down)

    with pytest.raises(SentMailUnreadable) as raised:
        await learn_writing_style(USER, replaces=None, config=None)

    assert raised.value.__cause__ is down
    assert world.recorded == [("writing_style:email", False)] and world.saved == []


async def test_a_model_failure_keeps_nothing_and_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer=RuntimeError("model down"),
    )

    with pytest.raises(RuntimeError):
        await learn_writing_style(USER, replaces=None, config=None)
    assert world.saved == []


async def test_a_spending_ceiling_is_said_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer=UsageLimitExceededError(limit_name="cycle_tokens", reason="ceiling"),
    )

    with pytest.raises(UsageLimitExceededError):
        await learn_writing_style(USER, replaces=None, config=None)


async def test_a_model_that_says_nothing_keeps_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(
        monkeypatch, stored=StoredStyle(enabled=True, row=None), sent=_mails(5), answer="  "
    )

    with pytest.raises(EmptyStyleProfile):
        await learn_writing_style(USER, replaces=None, config=None)
    assert world.saved == []


async def test_a_long_profile_is_kept_within_its_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _World(
        monkeypatch,
        stored=StoredStyle(enabled=True, row=None),
        sent=_mails(5),
        answer="x" * (WRITING_STYLE_PROFILE_MAX_CHARS + 50),
    )

    await learn_writing_style(USER, replaces=None, config=None)

    assert len(world.saved[0][0] or "") == WRITING_STYLE_PROFILE_MAX_CHARS


async def test_what_a_concurrent_learning_kept_is_read_back_from_its_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    since = NOW - timedelta(minutes=1)
    for stored, expected in (
        (StoredStyle(enabled=True, row=_row(PROFILE, age_days=0)), Learning("learned", 12)),
        (StoredStyle(enabled=True, row=_row(None, age_days=0)), Learning("too_few", 12)),
        (StoredStyle(enabled=True, row=_row(PROFILE, age_days=1)), None),
        (StoredStyle(enabled=True, row=None), None),
        (None, None),
    ):
        _World(monkeypatch, stored=stored)

        assert await learned_since(USER, since) == expected


# =============================================================================
# Reading the sent folder
# =============================================================================


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
        self, query: str, *, max_results: int, use_cache: bool, page_token: str | None = None
    ) -> dict[str, Any]:
        """One page, as a provider answers: never more than the agents' ceiling."""
        self.asked.append((query, max_results, use_cache))
        hits = [{"id": f"m{index}", "body": f"listed {index}"} for index in range(self._listed)]
        start = int(page_token or 0)
        end = start + min(max_results, _CEILING)
        return {
            "messages": hits[start:end],
            "next_page_token": str(end) if end < len(hits) else None,
        }

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

    sent = await door._read_sent(USER, 12, None)

    assert isinstance(sent, list) and [mail["body"] for mail in sent] == [
        f"listed {index}" for index in range(12)
    ]
    assert mailbox.asked == [("in:sent", 12, False)] and mailbox.started == []


async def test_more_mails_than_one_search_answers_are_read_page_after_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A style configured on 50 mails was learned on the 25 one search answered."""
    mailbox = _Mailbox(whole=True, listed=60)
    _open(monkeypatch, _outlook(mailbox))

    sent = await door._read_sent(USER, 50, None)

    assert isinstance(sent, list) and len(sent) == 50
    assert [mail["body"] for mail in sent] == [f"listed {index}" for index in range(50)]
    assert [asked[1] for asked in mailbox.asked] == [50, 25]


async def test_a_listing_of_previews_is_read_a_few_messages_at_a_time_in_its_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One at a time, fifty reads would keep the person waiting; all at once, they would
    pass what one mailbox bears."""
    listed = WRITING_STYLE_READ_CONCURRENCY * 3
    mailbox = _Mailbox(whole=False, listed=listed)
    _open(monkeypatch, _outlook(mailbox))

    sent = await door._read_sent(USER, listed, None)

    # The earliest listed is the slowest read: the order kept is the listing's.
    assert isinstance(sent, list) and [mail["body"] for mail in sent] == [
        f"whole m{index}" for index in range(listed)
    ]
    assert mailbox.widest == WRITING_STYLE_READ_CONCURRENCY


async def test_a_message_that_cannot_be_read_fails_the_read_and_stops_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A style learned from what an outage left would be kept until the person relearns
    it: the learning fails as a whole, and they ask again."""
    listed = WRITING_STYLE_READ_CONCURRENCY * 3
    mailbox = _Mailbox(whole=False, listed=listed, unreadable=f"m{listed - 1}")
    _open(monkeypatch, _outlook(mailbox))

    with pytest.raises(RuntimeError):
        await door._read_sent(USER, listed, None)

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
        await door._read_sent(USER, listed, None)

    assert mailbox.reading == 0 and len(mailbox.started) < listed


async def test_an_account_with_no_mailbox_has_nothing_to_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(monkeypatch, ClientUnavailable.NO_CONNECTOR)

    assert await door._read_sent(USER, 12, None) is ClientUnavailable.NO_CONNECTOR


# =============================================================================
# What the profile is learned from, and how the writers read it
# =============================================================================


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
