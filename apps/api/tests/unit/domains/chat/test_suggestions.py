"""Suggestions for the empty chat — grounded, or absent.

The empty chat offered three generic examples. It could instead show that LIA
already knows the day. The constraint is what makes this hard: the chat page
deliberately fetches no connector state, and offering "summarise my important
mails" to an account with no mail connector turns the first interaction into a
failure — the exact trap `lib/chat-starters` was written to avoid.

So a suggestion is only produced when the evidence for it is ALREADY in the
briefing cache. Never a live fetch: the suggestions must not wake a connector,
spend a quota, or make the empty chat slower than it is.

Cold cache is the normal case, not a degraded one — the client falls back to
the generic starters, exactly as before.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    CardSection,
    CardStatus,
    ForYouData,
    ForYouLoopItem,
    MailItem,
    MailsData,
)
from src.domains.chat.suggestions import build_chat_suggestions

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _user() -> SimpleNamespace:
    """A double honouring the fields `BriefingService` reads at construction.

    A bare `SimpleNamespace(id=...)` would make the constructor raise, and the
    builder's best-effort guard would then report "no suggestion" for what is
    really a broken fixture.
    """
    return SimpleNamespace(
        id=uuid4(),
        timezone="Europe/Paris",
        language="fr",
        briefing_preferences=None,
    )


def _section(data: object | None, status: CardStatus = CardStatus.OK) -> CardSection:
    return CardSection(status=status, data=data, generated_at=NOW)


def _agenda(*titles: str) -> CardSection:
    return _section(
        AgendaData(
            events=[AgendaEventItem(title=t, start_local="14:00", end_local=None) for t in titles]
        )
    )


def _mails(count: int) -> CardSection:
    return _section(
        MailsData(
            items=[
                MailItem(subject=f"Sujet {i}", received_local="09:00", sender_name="Marie")
                for i in range(count)
            ],
            total_unread_today=count,
        )
    )


def _for_you(*subjects: str) -> CardSection:
    return _section(
        ForYouData(
            open_loops=[
                ForYouLoopItem(id=str(uuid4()), subject=s, direction="user_owes", days_open=3)
                for s in subjects
            ],
            recent_automations=[],
        )
    )


def _reminder_stub(contents: tuple[str, ...]) -> AsyncMock:
    """A reminders fetcher answering with exactly these contents."""
    return AsyncMock(
        return_value=SimpleNamespace(items=[SimpleNamespace(content=c) for c in contents])
    )


async def _build(*, reminders: tuple[str, ...] = (), **sections: CardSection) -> list[object]:
    """Run the builder against a cache returning exactly these sections.

    The reminder source is stubbed to "none" by default and NOT left to the
    real fetcher: it opens a database session (`get_db_context`), which a unit
    test must never do. Left unpatched it reached the real pool — harmless
    alone, a hang under `-n auto --dist loadscope` where seventeen workers ask
    for a connection at once. Tests that care about reminders patch it
    themselves (see `TestRemindersAreReachableWithoutAnyConnector`).
    """
    empty = _section(None, CardStatus.NOT_CONFIGURED)
    bundle = SimpleNamespace(
        agenda=sections.get("agenda", empty),
        mails=sections.get("mails", empty),
        for_you=sections.get("for_you", empty),
    )
    with (
        patch(
            "src.domains.briefing.service.BriefingService.read_cached_cards",
            new=AsyncMock(return_value=bundle),
        ),
        patch(
            "src.domains.briefing.fetchers.fetch_reminders",
            new=_reminder_stub(reminders),
        ),
    ):
        return await build_chat_suggestions(user=_user())


class TestGrounding:
    async def test_a_cold_cache_suggests_nothing(self) -> None:
        """The client then shows its generic starters — no invented context."""
        assert await _build() == []

    async def test_an_upcoming_event_becomes_a_preparation_suggestion(self) -> None:
        suggestions = await _build(agenda=_agenda("Revue produit"))

        assert [s.id for s in suggestions] == ["next_event"]
        assert suggestions[0].params == {"subject": "Revue produit"}

    async def test_unread_mail_becomes_a_summary_suggestion(self) -> None:
        suggestions = await _build(mails=_mails(3))

        assert [s.id for s in suggestions] == ["important_mails"]
        # No subject is quoted: the suggestion is about the batch, and naming
        # one sender would pick a correspondent the reader did not choose.
        assert suggestions[0].params == {}

    async def test_an_open_commitment_becomes_a_closing_suggestion(self) -> None:
        suggestions = await _build(for_you=_for_you("devis de Marie"))

        assert [s.id for s in suggestions] == ["close_loop"]
        assert suggestions[0].params == {"subject": "devis de Marie"}


class TestRefusal:
    async def test_an_empty_section_suggests_nothing(self) -> None:
        """Present in cache, but with no event: there is nothing to prepare."""
        assert await _build(agenda=_agenda()) == []

    async def test_a_failed_section_suggests_nothing(self) -> None:
        """An error is not evidence — the connector may be down or expired."""
        assert await _build(agenda=_section(None, CardStatus.ERROR)) == []

    async def test_a_hidden_section_is_not_resurrected_as_a_suggestion(self) -> None:
        """The reader hid this card; suggesting from it would override that."""
        assert await _build(agenda=_section(None, CardStatus.HIDDEN)) == []


class TestOrderAndBounds:
    async def test_at_most_three_are_returned(self) -> None:
        suggestions = await _build(
            agenda=_agenda("Revue produit"),
            mails=_mails(2),
            for_you=_for_you("devis de Marie", "rappeler le plombier"),
        )

        assert len(suggestions) <= 3

    async def test_the_order_is_stable_and_starts_with_the_day(self) -> None:
        suggestions = await _build(
            agenda=_agenda("Revue produit"), mails=_mails(2), for_you=_for_you("devis")
        )

        assert [s.id for s in suggestions] == ["next_event", "important_mails", "close_loop"]

    async def test_only_the_FIRST_event_and_commitment_are_quoted(self) -> None:
        """Three cards, three suggestions — never three variants of one."""
        suggestions = await _build(agenda=_agenda("Premier", "Deuxième"))

        assert len(suggestions) == 1
        assert suggestions[0].params["subject"] == "Premier"


class TestSafety:
    async def test_a_cache_failure_degrades_to_no_suggestion(self) -> None:
        """A suggestion is a bonus; it must never break opening the chat."""
        with (
            patch(
                "src.domains.briefing.service.BriefingService.read_cached_cards",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
            patch("src.domains.briefing.fetchers.fetch_reminders", new=_reminder_stub(())),
        ):
            assert await build_chat_suggestions(user=_user()) == []

    async def test_no_live_fetch_is_ever_attempted(self) -> None:
        """The whole design rests on this: reading only what is already there.

        Asserted against the BUILDING path, not a docstring: `build_cards` is
        what wakes the connectors, spends the quotas and makes the call slow.
        """
        with (
            patch(
                "src.domains.briefing.service.BriefingService.read_cached_cards",
                new=AsyncMock(return_value=SimpleNamespace()),
            ),
            patch(
                "src.domains.briefing.service.BriefingService.build_cards",
                new=AsyncMock(),
            ) as build,
            # The reminder source is read LIVE by design (local table, < 10 ms).
            # Left to the real fetcher it opens a database session — 21 s here
            # against the pool, and a hang under `-n auto --dist loadscope`.
            patch(
                "src.domains.briefing.fetchers.fetch_reminders",
                new=_reminder_stub(()),
            ),
        ):
            await build_chat_suggestions(user=_user())

        build.assert_not_awaited()


class TestRemindersAreReachableWithoutAnyConnector:
    """The one grounded source an account without connectors can still feed.

    Measured on a real dev account 2026-08-03: `agenda` and `mails` were
    NOT_CONFIGURED (no connector) and `for_you` EMPTY (no open commitment), so
    the empty chat could only ever show its generic starters. The three sources
    chosen for ADR-199 were exactly the ones such an account cannot fill.

    Reminders close that gap and cost nothing ADR-199 forbids: they live in a
    LOCAL table, `fetch_reminders` is documented as "always succeeds — does not
    raise ConnectorNotConfiguredError", and the briefing rates the read at
    < 10 ms. That is precisely why the section is `TTL = 0`, never cached —
    and therefore invisible to a cache-only reader, which is how the cheapest
    source in the system ended up unreachable.
    """

    async def test_a_pending_reminder_becomes_a_suggestion(self) -> None:
        suggestions = await _build(reminders=("Rappeler le dentiste",))

        assert [s.id for s in suggestions] == ["reminder"]
        assert suggestions[0].params == {"subject": "Rappeler le dentiste"}

    async def test_no_reminder_yields_no_suggestion(self) -> None:
        assert await _build() == []

    async def test_a_failing_read_never_stands_between_the_reader_and_their_chat(self) -> None:
        empty = _section(None, CardStatus.NOT_CONFIGURED)
        bundle = SimpleNamespace(agenda=empty, mails=empty, for_you=empty)
        with (
            patch(
                "src.domains.briefing.service.BriefingService.read_cached_cards",
                new=AsyncMock(return_value=bundle),
            ),
            patch(
                "src.domains.briefing.fetchers.fetch_reminders",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
        ):
            assert await build_chat_suggestions(user=_user()) == []

    async def test_the_day_still_comes_first(self) -> None:
        """Order is stable: a meeting outranks a reminder."""
        suggestions = await _build(
            agenda=_agenda("Revue produit"), reminders=("Rappeler le dentiste",)
        )

        assert [s.id for s in suggestions] == ["next_event", "reminder"]

    async def test_only_the_first_reminder_is_quoted(self) -> None:
        """Three cards should give three different suggestions, not three of one."""
        suggestions = await _build(reminders=("Dentiste", "Chien", "Courses"))

        assert len(suggestions) == 1
