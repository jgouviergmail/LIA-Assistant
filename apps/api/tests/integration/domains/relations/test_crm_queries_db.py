"""Personal-CRM queries against real PostgreSQL — exactness and recall.

The CRM stopped paging rows and started asking the database the questions the
UI actually asks: how many, how recently, and which rows for THIS person.
Every oracle here is a PostgreSQL behavior an in-memory substitute cannot
exercise:

- ``GROUP BY`` over the whole set — the counts a card shows are claims, and
  the previous page-length implementation under-reported past its window;
- the ``unaccent`` extension really being installed and applied on BOTH sides
  of the memory search (a missing extension fails loudly here, not in prod);
- LIKE metacharacters in a person's name being escaped rather than acting as
  wildcards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory, MemoryCategory
from src.domains.memories.repository import MemoryRepository
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


@pytest.fixture
async def crm_user(async_session: AsyncSession):
    """One active user owning the CRM signals under test."""
    from src.domains.users.models import User

    user = User(
        email="crm_owner@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="CRM Owner",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _add_loop(session, user, counterparty, *, status=OpenLoopStatus.OPEN, days_ago=1):
    loop = OpenLoop(
        user_id=user.id,
        counterparty=counterparty,
        subject="dossier",
        direction="user_owes",
        status=status.value,
        created_at=NOW - timedelta(days=days_ago),
    )
    session.add(loop)
    return loop


async def _add_call(session, user, callee, *, days_ago=1):
    call = PhoneCall(
        user_id=user.id,
        callee_display=callee,
        callee_phone="encrypted-by-the-service",
        objective="rappeler",
        status=PhoneCallStatus.COMPLETED,
        created_at=NOW - timedelta(days=days_ago),
    )
    session.add(call)
    return call


async def _add_memory(session, user, content):
    memory = Memory(
        user_id=user.id,
        content=content,
        category=MemoryCategory.RELATIONSHIP.value,
        emotional_weight=0,
        trigger_topic="",
        usage_nuance="",
        importance=0.5,
        char_count=len(content),
    )
    session.add(memory)
    return memory


class TestOpenLoopAggregate:
    """One row per stored spelling, counted over the WHOLE backlog."""

    async def test_counts_every_spelling_separately_and_exactly(
        self, async_session: AsyncSession, crm_user
    ):
        for _ in range(3):
            await _add_loop(async_session, crm_user, "Gérard Dupont")
        await _add_loop(async_session, crm_user, "gerard dupont", days_ago=5)
        await async_session.commit()

        rows = await OpenLoopRepository(async_session).aggregate_open_by_counterparty(crm_user.id)
        counts = {row.raw_name: row.count for row in rows}
        assert counts == {"Gérard Dupont": 3, "gerard dupont": 1}
        # The folding that merges them is the caller's, never SQL's.
        assert {row.last_at for row in rows} == {NOW - timedelta(days=1), NOW - timedelta(days=5)}

    async def test_ignores_closed_loops_and_blank_counterparties(
        self, async_session: AsyncSession, crm_user
    ):
        await _add_loop(async_session, crm_user, "Marie")
        await _add_loop(async_session, crm_user, "Marie", status=OpenLoopStatus.CLOSED)
        await _add_loop(async_session, crm_user, "   ")
        await _add_loop(async_session, crm_user, None)
        await async_session.commit()

        rows = await OpenLoopRepository(async_session).aggregate_open_by_counterparty(crm_user.id)
        assert {row.raw_name: row.count for row in rows} == {"Marie": 1}

    async def test_lists_rows_for_the_exact_spellings_given(
        self, async_session: AsyncSession, crm_user
    ):
        await _add_loop(async_session, crm_user, "Gérard Dupont")
        await _add_loop(async_session, crm_user, "gerard dupont")
        await _add_loop(async_session, crm_user, "Paul Martin")
        await async_session.commit()

        repo = OpenLoopRepository(async_session)
        both = await repo.list_open_for_counterparties(
            crm_user.id, ["Gérard Dupont", "gerard dupont"], 50
        )
        assert {loop.counterparty for loop in both} == {"Gérard Dupont", "gerard dupont"}
        # An empty spelling list asks for nothing — never "everything".
        assert await repo.list_open_for_counterparties(crm_user.id, [], 50) == []


class TestCallAggregate:
    async def test_counts_calls_per_callee_over_the_whole_history(
        self, async_session: AsyncSession, crm_user
    ):
        await _add_call(async_session, crm_user, "Marie Leroy", days_ago=400)
        await _add_call(async_session, crm_user, "Marie Leroy", days_ago=2)
        await _add_call(async_session, crm_user, "Paul", days_ago=3)
        await async_session.commit()

        rows = await TelephonyRepository(async_session).aggregate_calls_by_callee(crm_user.id)
        counts = {row.raw_name: row.count for row in rows}
        # The 400-day-old call counts: an aggregate has no window to fall out of.
        assert counts == {"Marie Leroy": 2, "Paul": 1}
        marie = next(row for row in rows if row.raw_name == "Marie Leroy")
        assert marie.last_at == NOW - timedelta(days=2)

    async def test_lists_calls_for_the_exact_callees_given(
        self, async_session: AsyncSession, crm_user
    ):
        await _add_call(async_session, crm_user, "Marie Leroy", days_ago=2)
        await _add_call(async_session, crm_user, "Paul", days_ago=3)
        await async_session.commit()

        calls = await TelephonyRepository(async_session).list_calls_for_callees(
            crm_user.id, ["Marie Leroy"], 50
        )
        assert [call.callee_display for call in calls] == ["Marie Leroy"]


class TestMemorySearch:
    """The predicate moved from a Python loop over 500 rows into PostgreSQL."""

    async def test_matches_accent_and_case_insensitively(
        self, async_session: AsyncSession, crm_user
    ):
        await _add_memory(async_session, crm_user, "Gérard adore la randonnée")
        await _add_memory(async_session, crm_user, "GERARD déteste le café")
        await _add_memory(async_session, crm_user, "Note sans rapport")
        await async_session.commit()

        rows, total = await MemoryRepository(async_session).list_mentioning_name(
            crm_user.id, "gerard", 50
        )
        assert total == 2
        assert len(rows) == 2

    async def test_total_is_exact_while_the_page_is_capped(
        self, async_session: AsyncSession, crm_user
    ):
        for index in range(5):
            await _add_memory(async_session, crm_user, f"Marie, note {index}")
        await async_session.commit()

        rows, total = await MemoryRepository(async_session).list_mentioning_name(
            crm_user.id, "Marie", 2
        )
        assert len(rows) == 2 and total == 5

    async def test_like_metacharacters_are_literal(self, async_session: AsyncSession, crm_user):
        """A name is a name, never a pattern: '%' must not match everything."""
        await _add_memory(async_session, crm_user, "Rien à voir avec la requête")
        await async_session.commit()

        _rows, total = await MemoryRepository(async_session).list_mentioning_name(
            crm_user.id, "%", 50
        )
        assert total == 0

    async def test_blank_name_asks_for_nothing(self, async_session: AsyncSession, crm_user):
        await _add_memory(async_session, crm_user, "Une note")
        await async_session.commit()

        assert await MemoryRepository(async_session).list_mentioning_name(
            crm_user.id, "   ", 50
        ) == ([], 0)
