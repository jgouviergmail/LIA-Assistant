"""F018: skill-state provisioning must use ONE bulk upsert, not a per-row loop.

These pin the *shape* of the DB access (a bounded number of ``execute`` calls)
without a live database — the actual insert semantics (idempotent ON CONFLICT,
no duplicates) are proven end-to-end against a real DB. The regression these
guard against is silently reverting to an O(users × skills) savepoint loop.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.skills.repository import UserSkillStateRepository


@pytest.mark.asyncio
async def test_ensure_states_for_user_no_missing_skips_insert():
    db = MagicMock()
    db.execute = AsyncMock(return_value=[])  # missing-skills select → nothing missing
    repo = UserSkillStateRepository(db)

    created = await repo.ensure_states_for_user(uuid4())

    assert created == 0
    assert db.execute.await_count == 1  # only the SELECT, no INSERT at all


@pytest.mark.asyncio
async def test_ensure_states_for_user_uses_single_bulk_insert():
    db = MagicMock()
    missing = [(uuid4(),), (uuid4(),), (uuid4(),)]  # 3 missing skills
    db.execute = AsyncMock(side_effect=[missing, MagicMock(rowcount=3)])
    repo = UserSkillStateRepository(db)

    created = await repo.ensure_states_for_user(uuid4())

    assert created == 3
    # 1 SELECT + exactly 1 bulk INSERT — NOT 1 + N (the old savepoint loop).
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_create_states_for_all_users_uses_single_bulk_insert():
    db = MagicMock()
    users = [(uuid4(),), (uuid4(),)]
    db.execute = AsyncMock(side_effect=[users, MagicMock(rowcount=2)])
    repo = UserSkillStateRepository(db)

    created = await repo.create_states_for_all_users(uuid4())

    assert created == 2
    assert db.execute.await_count == 2  # 1 SELECT + 1 bulk INSERT


@pytest.mark.asyncio
async def test_ensure_states_for_all_system_skills_is_one_set_based_statement():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=5))
    repo = UserSkillStateRepository(db)

    created = await repo.ensure_states_for_all_system_skills()

    assert created == 5
    # ONE cross-join INSERT ... SELECT for the whole users × skills set — never
    # a per-user loop.
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_state_rows_generate_distinct_ids_and_timestamps():
    repo = UserSkillStateRepository(MagicMock())
    uid, s1, s2 = uuid4(), uuid4(), uuid4()

    rows = repo._state_rows([(uid, s1), (uid, s2)])

    assert len(rows) == 2
    assert rows[0]["id"] != rows[1]["id"]  # per-row UUIDs (mixins use Python defaults)
    assert all(r["created_at"] == r["updated_at"] for r in rows)
    assert all(r["is_active"] is True for r in rows)
