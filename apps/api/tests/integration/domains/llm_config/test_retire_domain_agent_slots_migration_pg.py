"""The sixteen domain-agent slots leave with their nodes (ADR-371), on a real PostgreSQL.

What must hold: every retired row goes, the slot that still writes the mail stays, and so does any
other row of the table. The list is held against the registry: a name it lost must be a name the
code no longer reads.
"""

from __future__ import annotations

import importlib.util
import re
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

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_11_06_2000-b6d21f7e4a90_retire_domain_agent_slots.py"
)
_KEPT = ("emails_agent", "response")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("retire_domain_agent_slots", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
RETIRED = tuple(re.findall(r"'([a-z_]+_agent)'", MIGRATION._RETIRE_THE_SLOTS.text))


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of the revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _rows(session: AsyncSession) -> set[str]:
    result = await session.execute(text("SELECT llm_type FROM llm_config_overrides"))
    return {row[0] for row in result}


async def _one_row_each(session: AsyncSession, slots: tuple[str, ...]) -> None:
    await session.execute(
        text("DELETE FROM llm_config_overrides WHERE llm_type = ANY(:slots)"),
        {"slots": list(slots)},
    )
    for slot in slots:
        await session.execute(
            text(
                "INSERT INTO llm_config_overrides (id, llm_type, created_at, updated_at) "
                "VALUES (:id, :slot, now(), now())"
            ),
            {"id": uuid4(), "slot": slot},
        )


def test_it_retires_sixteen_slots_the_registry_no_longer_holds() -> None:
    assert len(set(RETIRED)) == 16
    assert not set(RETIRED) & set(LLM_TYPES_REGISTRY)
    assert "emails_agent" not in RETIRED


@pytest.mark.asyncio
async def test_every_retired_row_goes_and_the_rest_stays(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, (*RETIRED, *_KEPT))

    await _migrate(session, MIGRATION.upgrade)

    held = await _rows(session)
    assert not held & set(RETIRED)
    assert set(_KEPT) <= held


@pytest.mark.asyncio
async def test_the_downgrade_writes_nothing_back(async_session: AsyncSession) -> None:
    session = async_session
    await _one_row_each(session, (*RETIRED, *_KEPT))
    await _migrate(session, MIGRATION.upgrade)
    before = await _rows(session)

    await _migrate(session, MIGRATION.downgrade)

    assert await _rows(session) == before
