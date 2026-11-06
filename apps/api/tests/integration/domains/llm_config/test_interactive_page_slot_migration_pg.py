"""The page's own slot starts on the row documents had (ADR-370), on a real PostgreSQL.

The revision's own ``upgrade`` and ``downgrade`` run through an Alembic ``Operations``
context bound to the test's connection, inside its rolled-back transaction.

What must hold: every tuning column reaches the new row, an administrator's existing
row is kept, an instance with no document row gets none, and the downgrade removes
the page's row alone.
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
    / "2026_11_05_2200-7c3e91a4d2f6_interactive_page_slot.py"
)
#: What identifies a row or dates it, and so is not a setting to carry over.
_NOT_TUNING = frozenset({"id", "llm_type", "created_at", "updated_at", "updated_by"})


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("interactive_page_slot", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of the revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _no_slots(session: AsyncSession) -> None:
    await session.execute(
        text(
            "DELETE FROM llm_config_overrides "
            "WHERE llm_type IN ('document_generation', 'interactive_page')"
        )
    )


async def _tuned_document_row(session: AsyncSession) -> None:
    """A document row with every setting filled, as production's could be."""
    await session.execute(
        text(
            "INSERT INTO llm_config_overrides "
            "(id, llm_type, provider, model, temperature, top_p, frequency_penalty, "
            "presence_penalty, max_tokens, timeout_seconds, context_window, reasoning_effort, "
            "provider_config, created_at, updated_at) "
            "VALUES (:id, 'document_generation', 'anthropic', 'some-model', 0.3, 0.9, 0.1, 0.2, "
            "100000, 300, 200000, CAST(:reasoning AS jsonb), :config, now(), now())"
        ),
        {
            "id": uuid4(),
            "reasoning": '{"level": "low", "budget_tokens": null, "exclude_from_output": false}',
            "config": '{"a": 1}',
        },
    )


async def _row(session: AsyncSession, slot: str) -> dict[str, Any] | None:
    result = await session.execute(
        text("SELECT * FROM llm_config_overrides WHERE llm_type = :slot"), {"slot": slot}
    )
    row = result.mappings().one_or_none()
    return dict(row) if row is not None else None


@pytest.mark.asyncio
async def test_every_tuning_column_reaches_the_page_s_row(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_document_row(session)

    await _migrate(session, MIGRATION.upgrade)

    document = await _row(session, "document_generation")
    page = await _row(session, "interactive_page")
    assert document is not None and page is not None
    tuning = set(document) - _NOT_TUNING
    assert tuning, "the table holds no setting: the comparison proves nothing"
    assert {column: page[column] for column in tuning} == {
        column: document[column] for column in tuning
    }
    assert all(document[column] is not None for column in tuning)
    assert page["id"] != document["id"]
    assert page["updated_by"] is None


@pytest.mark.asyncio
async def test_a_row_an_administrator_saved_is_kept(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_document_row(session)
    await session.execute(
        text(
            "INSERT INTO llm_config_overrides (id, llm_type, max_tokens, created_at, updated_at) "
            "VALUES (:id, 'interactive_page', 7, now(), now())"
        ),
        {"id": uuid4()},
    )

    await _migrate(session, MIGRATION.upgrade)

    page = await _row(session, "interactive_page")
    assert page is not None
    assert page["max_tokens"] == 7
    assert page["model"] is None


@pytest.mark.asyncio
async def test_with_no_document_row_the_slot_stays_on_its_default(
    async_session: AsyncSession,
) -> None:
    session = async_session
    await _no_slots(session)

    await _migrate(session, MIGRATION.upgrade)

    assert await _row(session, "interactive_page") is None


@pytest.mark.asyncio
async def test_the_downgrade_removes_the_page_s_row_alone(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_document_row(session)
    await _migrate(session, MIGRATION.upgrade)

    await _migrate(session, MIGRATION.downgrade)

    assert await _row(session, "interactive_page") is None
    assert await _row(session, "document_generation") is not None
