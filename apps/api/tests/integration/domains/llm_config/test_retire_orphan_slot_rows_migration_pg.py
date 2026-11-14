"""Three orphan override rows leave the table (ADR-244), on a real PostgreSQL.

What must hold: each of the three rows goes, every other row of the table stays
as it was, an instance that never held them is untouched, a second run changes
nothing, and the downgrade writes nothing back.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_11_11_2200-27fc835b8d44_retire_orphan_slot_rows.py"
)
#: Rows an administrator configured: the response, and the slot whose name
#: starts like a retired one would if the statement matched by pattern.
_KEPT = ("response", "compaction", "mcp_react_agent")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("retire_orphan_slot_rows", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
RETIRED: tuple[str, ...] = tuple(MIGRATION.RETIRED)


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of the revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _rows(session: AsyncSession) -> dict[str, str | None]:
    result = await session.execute(text("SELECT llm_type, model FROM llm_config_overrides"))
    return {row[0]: row[1] for row in result}


async def _one_row_each(session: AsyncSession, slots: tuple[str, ...]) -> None:
    await session.execute(text("DELETE FROM llm_config_overrides"))
    for slot in slots:
        await session.execute(
            text(
                "INSERT INTO llm_config_overrides (id, llm_type, model, created_at, updated_at) "
                "VALUES (:id, :slot, :model, now(), now())"
            ),
            {"id": uuid4(), "slot": slot, "model": f"model-of-{slot}"},
        )


@pytest.mark.asyncio
async def test_every_orphan_row_goes_and_the_rest_stays(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, (*RETIRED, *_KEPT))

    await _migrate(session, MIGRATION.upgrade)

    assert await _rows(session) == {slot: f"model-of-{slot}" for slot in _KEPT}


@pytest.mark.asyncio
async def test_an_instance_that_never_held_them_is_untouched(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, _KEPT)
    before = await _rows(session)

    await _migrate(session, MIGRATION.upgrade)

    assert await _rows(session) == before


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, (*RETIRED, *_KEPT))
    await _migrate(session, MIGRATION.upgrade)
    once = await _rows(session)

    await _migrate(session, MIGRATION.upgrade)

    assert await _rows(session) == once


@pytest.mark.asyncio
async def test_the_downgrade_writes_nothing_back(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, (*RETIRED, *_KEPT))
    await _migrate(session, MIGRATION.upgrade)
    before = await _rows(session)

    await _migrate(session, MIGRATION.downgrade)

    assert await _rows(session) == before
