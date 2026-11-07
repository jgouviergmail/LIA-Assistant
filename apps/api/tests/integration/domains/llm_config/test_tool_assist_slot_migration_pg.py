"""What LIA does from the Tools starts on a row the instance pays for (ADR-372), on a real PostgreSQL.

The revision's own ``upgrade`` and ``downgrade`` run through an Alembic ``Operations`` context bound
to the test's connection, inside its rolled-back transaction.

What must hold: every tuning column reaches the new row, the output cap never falls under what a
rewrite needs, an administrator's row is kept, an instance with no digest row starts on the
response's, and the downgrade removes the slot's row alone.
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
    / "2026_11_06_2100-c8e4a1f27b53_tool_assist_slot.py"
)
#: What identifies a row or dates it, and so is not a setting to carry over.
_NOT_TUNING = frozenset({"id", "llm_type", "created_at", "updated_at", "updated_by"})
_OUTPUT_FLOOR = 4000


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tool_assist_slot", _MIGRATION)
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
            "WHERE llm_type IN ('email_digest', 'response', 'tool_assist')"
        )
    )


async def _tuned_row(session: AsyncSession, slot: str, max_tokens: int | None) -> None:
    """A row with every setting filled, as production's could be."""
    await session.execute(
        text(
            "INSERT INTO llm_config_overrides "
            "(id, llm_type, provider, model, temperature, top_p, frequency_penalty, "
            "presence_penalty, max_tokens, timeout_seconds, context_window, reasoning_effort, "
            "provider_config, created_at, updated_at) "
            "VALUES (:id, :slot, 'anthropic', 'some-model', 0.3, 0.9, 0.1, 0.2, "
            ":max_tokens, 300, 200000, CAST(:reasoning AS jsonb), :config, now(), now())"
        ),
        {
            "id": uuid4(),
            "slot": slot,
            "max_tokens": max_tokens,
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
async def test_every_tuning_column_reaches_the_slot_s_row(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_row(session, "email_digest", 9000)

    await _migrate(session, MIGRATION.upgrade)

    digest = await _row(session, "email_digest")
    slot = await _row(session, "tool_assist")
    assert digest is not None and slot is not None
    tuning = set(digest) - _NOT_TUNING
    assert tuning, "the table holds no setting: the comparison proves nothing"
    assert {column: slot[column] for column in tuning} == {
        column: digest[column] for column in tuning
    }
    assert slot["id"] != digest["id"]
    assert slot["updated_by"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("digest_cap", [None, 500])
async def test_the_output_cap_holds_a_rewrite(
    async_session: AsyncSession, digest_cap: int | None
) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_row(session, "email_digest", digest_cap)

    await _migrate(session, MIGRATION.upgrade)

    slot = await _row(session, "tool_assist")
    assert slot is not None
    assert slot["max_tokens"] == _OUTPUT_FLOOR


@pytest.mark.asyncio
async def test_a_row_an_administrator_saved_is_kept(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_row(session, "email_digest", 9000)
    await session.execute(
        text(
            "INSERT INTO llm_config_overrides (id, llm_type, max_tokens, created_at, updated_at) "
            "VALUES (:id, 'tool_assist', 7, now(), now())"
        ),
        {"id": uuid4()},
    )

    await _migrate(session, MIGRATION.upgrade)

    slot = await _row(session, "tool_assist")
    assert slot is not None
    assert slot["max_tokens"] == 7
    assert slot["model"] is None


@pytest.mark.asyncio
async def test_with_no_digest_row_it_starts_on_the_response_s(
    async_session: AsyncSession,
) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_row(session, "response", 8000)

    await _migrate(session, MIGRATION.upgrade)

    slot = await _row(session, "tool_assist")
    assert slot is not None
    assert (slot["provider"], slot["model"]) == ("anthropic", "some-model")


@pytest.mark.asyncio
async def test_with_neither_row_the_slot_stays_on_its_default(
    async_session: AsyncSession,
) -> None:
    session = async_session
    await _no_slots(session)

    await _migrate(session, MIGRATION.upgrade)

    assert await _row(session, "tool_assist") is None


@pytest.mark.asyncio
async def test_the_downgrade_removes_the_slot_s_row_alone(async_session: AsyncSession) -> None:
    session = async_session
    await _no_slots(session)
    await _tuned_row(session, "email_digest", 9000)
    await _migrate(session, MIGRATION.upgrade)

    await _migrate(session, MIGRATION.downgrade)

    assert await _row(session, "tool_assist") is None
    assert await _row(session, "email_digest") is not None
