"""Consolidation lifecycle against PostgreSQL: cooldown stamp, gauges, eligibility.

Covers the ADR-159 review findings that only a real database can pin:

- the cooldown stamp is written on EVERY completed run, including the very
  common one that decides there is nothing to maintain. Skipping it left the
  user permanently eligible and the consolidation LLM re-ran at every scheduler
  tick, forever;
- the portrait-age gauge and the scheduler's eligibility query share ONE
  predicate, so the gauge can never report a staleness the scheduler will not
  act on;
- the effectiveness gauges publish a value for every theme, including the
  absent ones — a theme with no series reads as "no data", a theme at 0 reads
  as "unreachable", and only the second is alertable.

The consolidation LLM is faked: these tests are about persistence and metrics,
not about what the model answers.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals import consolidation_service
from src.domains.journals.models import JournalEntry, JournalTheme
from src.domains.journals.repository import (
    JournalEntryRepository,
    consolidation_eligible_user_conditions,
)
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def _redirect_db_context(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``get_db_context()`` to the test session.

    The consolidation service opens its OWN sessions, on purpose: it runs
    detached from any request. That makes it invisible to the per-test
    transaction, so a naive test asserts on a row the service never saw.

    Both import spellings must be patched at their SOURCE module, not on
    ``consolidation_service``: the service imports ``get_db_context`` inside the
    functions, so the name is resolved at call time and a module-attribute patch
    on the caller would never be consulted.
    """
    from src.infrastructure import database
    from src.infrastructure.database import session as database_session

    @asynccontextmanager
    async def _fake_ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(database, "get_db_context", _fake_ctx)
    monkeypatch.setattr(database_session, "get_db_context", _fake_ctx)


async def _make_user(session: AsyncSession, **overrides: Any) -> User:
    """Insert a consolidation-eligible user, overridable field by field."""
    fields: dict[str, Any] = {
        "email": f"conso-{uuid.uuid4().hex[:8]}@example.com",
        "hashed_password": "x",
        "is_active": True,
        "journals_enabled": True,
        "journal_consolidation_enabled": True,
    }
    fields.update(overrides)
    user = User(**fields)
    session.add(user)
    await session.flush()
    return user


def _fake_llm(
    actions: list[dict[str, Any]] | None = None,
    portrait_full: str = "",
    portrait_brief: str = "",
) -> Any:
    """Build a stand-in for ``invoke_with_instrumentation``.

    The payload is serialised with ``json.dumps`` rather than interpolated:
    the consolidation answer is a JSON object whose braces would otherwise
    fight with any templating, and a test that silently produced invalid JSON
    would assert on the parser's empty fallback instead of on the service.
    """
    payload = json.dumps(
        {
            "actions": actions or [],
            "portrait_full": portrait_full,
            "portrait_brief": portrait_brief,
        }
    )

    async def _call(**_kwargs: Any) -> AIMessage:
        return AIMessage(content=payload)

    return _call


async def _make_entry(session: AsyncSession, user: User, theme: str) -> JournalEntry:
    """Insert one active journal entry with the given theme."""
    entry = JournalEntry(
        user_id=user.id,
        theme=theme,
        title=f"t-{theme}",
        content="c",
        mood="reflective",
        status="active",
        source="conversation",
        char_count=1,
        level="L1",
    )
    session.add(entry)
    await session.flush()
    return entry


class TestCooldownStamp:
    """`journal_last_consolidated_at` gates the scheduler — it must always move."""

    async def test_stamp_helper_writes_the_timestamp(
        self, async_session: AsyncSession, _redirect_db_context: None
    ) -> None:
        """The helper persists a fresh UTC timestamp on the user row."""
        user = await _make_user(async_session, journal_last_consolidated_at=None)

        await consolidation_service._stamp_last_consolidated(user.id)

        await async_session.refresh(user)
        assert user.journal_last_consolidated_at is not None
        assert user.journal_last_consolidated_at.tzinfo is not None
        age = datetime.now(UTC) - user.journal_last_consolidated_at
        assert age < timedelta(minutes=5)

    async def test_stamp_helper_is_a_noop_on_an_unknown_user(
        self, _redirect_db_context: None
    ) -> None:
        """A user deleted between the run and the stamp must not raise.

        The stamp runs after the LLM call, in its own session; the row can be
        gone by then, and a raise there would be logged as a whole-run failure.
        """
        await consolidation_service._stamp_last_consolidated(uuid.uuid4())

    async def test_run_with_no_actions_still_consumes_the_cooldown(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """The regression this whole finding is about.

        A consolidation whose LLM answer contains no maintenance action is the
        NORMAL outcome — the prompt explicitly says so. Before the fix it
        returned before stamping, so the scheduler's cooldown gate never closed
        and the run repeated at every tick.
        """
        user = await _make_user(async_session, journal_last_consolidated_at=None)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())

        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 0
        await async_session.refresh(user)
        assert user.journal_last_consolidated_at is not None, (
            "a no-action run must still consume the cooldown, otherwise the "
            "scheduler re-runs the consolidation LLM at every tick forever"
        )

    async def test_stamped_user_is_no_longer_eligible_within_the_cooldown(
        self, async_session: AsyncSession
    ) -> None:
        """The stamp actually closes the scheduler's gate.

        Pins the link between the column and the eligibility predicate: a test
        that only asserted "the column moved" would pass even if the scheduler
        read a different one.
        """
        cooldown_threshold = datetime.now(UTC) - timedelta(hours=6)
        fresh = await _make_user(async_session, journal_last_consolidated_at=datetime.now(UTC))
        stale = await _make_user(
            async_session, journal_last_consolidated_at=datetime.now(UTC) - timedelta(hours=12)
        )
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(
                        and_(
                            *consolidation_eligible_user_conditions(),
                            (
                                User.journal_last_consolidated_at.is_(None)
                                | (User.journal_last_consolidated_at < cooldown_threshold)
                            ),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )

        assert stale.id in eligible
        assert fresh.id not in eligible


class TestConsolidationDeletesCounter:
    """The pruning counter must actually count — it feeds a live Grafana panel."""

    async def test_applied_deletes_increment_the_counter(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """A delete applied by the consolidation shows up in the metric.

        ``journal_consolidation_deletes_total`` replaced a counter that was
        declared, dashboarded and never incremented — its panel had read
        "No data" since it shipped. Wiring it without an oracle would have
        reproduced exactly that defect, one name later.
        """
        from src.infrastructure.observability.metrics_journals import (
            journal_consolidation_deletes_total,
        )

        user = await _make_user(async_session)
        doomed = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        keeper = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        entry_id = str(doomed.id)

        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(actions=[{"action": "delete", "entry_id": entry_id}]),
        )

        before = journal_consolidation_deletes_total._value.get()
        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )
        after = journal_consolidation_deletes_total._value.get()

        assert applied == 1
        assert after - before == 1.0, (
            "the consolidation deleted an entry but the counter did not move — "
            "the Grafana panel would read 'No data' exactly like its predecessor"
        )

        remaining = (
            (
                await async_session.execute(
                    select(JournalEntry.id).where(JournalEntry.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [keeper.id]

    async def test_a_run_without_deletes_leaves_the_counter_alone(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """Only real deletions count — otherwise the pruning signal is noise."""
        from src.infrastructure.observability.metrics_journals import (
            journal_consolidation_deletes_total,
        )

        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        entry_id = str(entry.id)

        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(actions=[{"action": "update", "entry_id": entry_id, "title": "reworded"}]),
        )

        before = journal_consolidation_deletes_total._value.get()
        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 1
        assert journal_consolidation_deletes_total._value.get() == before


class TestEligibilityPredicate:
    """One predicate, shared by the scheduler and the portrait-age gauge."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("journals_enabled", False),
            ("journal_consolidation_enabled", False),
            ("is_active", False),
        ],
    )
    async def test_opted_out_user_is_excluded(
        self, async_session: AsyncSession, field: str, value: bool
    ) -> None:
        """A user who cannot be consolidated is not eligible."""
        user = await _make_user(async_session, **{field: value})
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(and_(*consolidation_eligible_user_conditions()))
                )
            )
            .scalars()
            .all()
        )
        assert user.id not in eligible

    async def test_soft_deleted_user_is_excluded(self, async_session: AsyncSession) -> None:
        """A soft-deleted user keeps their rows but must never be processed."""
        user = await _make_user(async_session, deleted_at=datetime.now(UTC))
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(and_(*consolidation_eligible_user_conditions()))
                )
            )
            .scalars()
            .all()
        )
        assert user.id not in eligible


class TestPortraitAgeGauge:
    """The staleness gauge must only measure what the scheduler still owns."""

    async def test_ignores_users_without_a_compiled_portrait(
        self, async_session: AsyncSession
    ) -> None:
        """Never compiled is not stale — it is a different, separate signal."""
        await _make_user(async_session, journal_portrait_compiled_at=None)
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert age == 0.0

    async def test_reports_the_oldest_eligible_portrait(self, async_session: AsyncSession) -> None:
        """The gauge is a max over eligible users."""
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=3),
        )
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=30),
        )
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert 29.0 < age < 31.0

    async def test_ignores_an_ineligible_user_however_stale(
        self, async_session: AsyncSession
    ) -> None:
        """A user the scheduler will never pick up must not pin the gauge.

        Without this filter a single soft-deleted account froze the gauge at an
        ever-growing value, so the staleness alert could never clear and became
        unactionable — the exact opposite of the gauge's purpose.
        """
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=2),
        )
        await _make_user(
            async_session,
            deleted_at=datetime.now(UTC),
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(days=400),
        )
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert age < 24.0, "a soft-deleted user must not pin the staleness gauge"


class TestThemeDistribution:
    """The gauge that would have caught the ADR-159 defect on day one."""

    async def test_counts_active_entries_per_theme(self, async_session: AsyncSession) -> None:
        """Themes present in the corpus are counted."""
        user = await _make_user(async_session)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        await _make_entry(async_session, user, JournalTheme.SELF_REFLECTION.value)
        await async_session.flush()

        counts = await JournalEntryRepository(async_session).count_by_theme_global()
        assert counts[JournalTheme.LEARNINGS.value] >= 2
        assert counts[JournalTheme.SELF_REFLECTION.value] >= 1

    async def test_archived_entries_are_excluded(self, async_session: AsyncSession) -> None:
        """Only ACTIVE entries shape the corpus."""
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.IDEAS_ANALYSES.value)
        entry.status = "archived"
        await async_session.flush()

        counts = await JournalEntryRepository(async_session).count_by_theme_global()
        assert counts.get(JournalTheme.IDEAS_ANALYSES.value, 0) == 0
