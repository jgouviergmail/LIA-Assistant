"""The shared-pins migration (ADR-345 amendment 2026-10-14), on a real PostgreSQL, both ways and back.

The revision's own ``upgrade`` and ``downgrade`` run through an Alembic
``Operations`` context bound to the test's connection — the DDL and the slot
rewrites are the ones production will run, inside the test's rolled-back
transaction.

What must hold:

- the upgrade moves the chat slot's pins first, then the radio's, each id once,
  a malformed one dropped, at most the ceiling of the release — each under the
  administrator who last saved its slot — and removes the key from the slots,
  the rest of their tuning written back the way the admin form writes it;
- a slot whose tuning is not an object is left as it is;
- the downgrade writes the shared list back into both slots, then drops it, and
  a second upgrade lands on the same list.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_10_14_1700-8ba7655b548b_fishaudio_shared_pins.py"
)

A = "a" * 32
B = "b" * 32
C = "c" * 32


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fishaudio_shared_pins", _MIGRATION)
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


async def _slot(
    session: AsyncSession, slot: str, config: object, *, updated_by: UUID | None
) -> None:
    """A slot row as the admin form stored it (a str is stored verbatim)."""
    await session.execute(
        text("DELETE FROM llm_config_overrides WHERE llm_type = :slot"), {"slot": slot}
    )
    await session.execute(
        text(
            "INSERT INTO llm_config_overrides "
            "(id, llm_type, provider, provider_config, updated_by, created_at, updated_at) "
            "VALUES (:id, :slot, 'fishaudio', :config, :updated_by, now(), now())"
        ),
        {
            "id": uuid4(),
            "slot": slot,
            "config": config if isinstance(config, str) else json.dumps(config),
            "updated_by": updated_by,
        },
    )


async def _config(session: AsyncSession, slot: str) -> str | None:
    return await session.scalar(
        text("SELECT provider_config FROM llm_config_overrides WHERE llm_type = :slot"),
        {"slot": slot},
    )


async def _pins(session: AsyncSession) -> list[tuple[str, UUID | None]]:
    rows = await session.execute(
        text("SELECT voice_id, pinned_by FROM fishaudio_pinned_voices ORDER BY created_at, id")
    )
    return [(row.voice_id, row.pinned_by) for row in rows]


async def _shared_list_exists(session: AsyncSession) -> bool:
    return bool(
        await session.scalar(text("SELECT to_regclass('fishaudio_pinned_voices') IS NOT NULL"))
    )


@pytest.mark.asyncio
async def test_the_migration_both_ways_and_back(async_session: AsyncSession) -> None:
    session = async_session
    admin = User(email=f"pins_{uuid4().hex}@example.com", hashed_password="x", is_active=True)
    session.add(admin)
    await session.flush()

    # The schema as it was: the pins on each slot, no shared list.
    await _migrate(session, MIGRATION.downgrade)
    assert not await _shared_list_exists(session)
    await _slot(
        session,
        "voice_tts",
        {"voice_male": "m", "speed": 1.0, "pinned_voices": [A, "not-an-id", B, A, 42]},
        updated_by=admin.id,
    )
    await _slot(
        session, "radio_voice", {"pinned_voices": [B, C], "latency": "low"}, updated_by=None
    )

    await _migrate(session, MIGRATION.upgrade)

    assert await _pins(session) == [(A, admin.id), (B, admin.id), (C, None)]
    assert await _config(session, "voice_tts") == '{"speed":1.0,"voice_male":"m"}'
    assert await _config(session, "radio_voice") == '{"latency":"low"}'

    await _migrate(session, MIGRATION.downgrade)

    assert not await _shared_list_exists(session)
    for slot in ("voice_tts", "radio_voice"):
        assert json.loads(await _config(session, slot) or "{}")["pinned_voices"] == [A, B, C]

    await _migrate(session, MIGRATION.upgrade)

    assert [voice_id for voice_id, _ in await _pins(session)] == [A, B, C]


@pytest.mark.asyncio
async def test_the_ceiling_holds_and_an_unreadable_tuning_is_left_alone(
    async_session: AsyncSession,
) -> None:
    session = async_session
    await _migrate(session, MIGRATION.downgrade)
    many = [f"{index:032x}" for index in range(MIGRATION._PINS_MAX + 5)]
    await _slot(session, "voice_tts", {"pinned_voices": many}, updated_by=None)
    await _slot(session, "radio_voice", "not json", updated_by=None)

    await _migrate(session, MIGRATION.upgrade)

    assert [voice_id for voice_id, _ in await _pins(session)] == many[: MIGRATION._PINS_MAX]
    assert await _config(session, "voice_tts") == "{}"
    assert await _config(session, "radio_voice") == "not json"
