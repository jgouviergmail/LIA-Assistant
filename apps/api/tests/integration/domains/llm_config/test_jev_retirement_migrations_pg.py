"""ADR-374's three migrations, on a real PostgreSQL.

What must hold: every retired switch and slot row goes and every other row stays (the code
that boots after them no longer declares those keys, and an unfiltered read of
``system_settings`` would raise ``LookupError``); the thresholds rows the new code may write
go on a downgrade, for the same reason in the other direction.
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

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.system_settings.models import SystemSettingKey

pytestmark = pytest.mark.integration

_VERSIONS = Path(__file__).resolve().parents[4] / "alembic" / "versions"
_KINDS = ("email", "event", "task", "file", "reminder", "ticket", "mcp", "document")
_KEPT_KEYS = ("JEV_ENABLED", "JEV_EMAIL_CLASSIFICATION_ENABLED")
_KEPT_SLOTS = ("jev_email_classification", "response")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREVIEWS = _load("2026_11_08_0100-9f4f6c3bb223_retire_collection_previews.py")
INITIATIVE = _load("2026_11_08_0200-2bd1b9347e2c_retire_jev_initiative_gate.py")
THRESHOLDS = _load("2026_11_08_0300-77a44a46135f_jev_threshold_settings.py")

RETIRED_KEYS = (
    *(f"JEV_FILTER_{kind.upper()}_ENABLED" for kind in _KINDS),
    "JEV_INITIATIVE_UTILITY_ENABLED",
)
RETIRED_SLOTS = (*(f"jev_filter_{kind}" for kind in _KINDS), "jev_initiative_utility")


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Run one direction of a revision on the test's own connection."""

    def _run(sync_session: Any) -> None:
        context = MigrationContext.configure(sync_session.connection())
        with Operations.context(context):
            step()

    await session.run_sync(_run)


async def _settings(session: AsyncSession) -> set[str]:
    return {row[0] for row in await session.execute(text("SELECT key FROM system_settings"))}


async def _slots(session: AsyncSession) -> set[str]:
    result = await session.execute(text("SELECT llm_type FROM llm_config_overrides"))
    return {row[0] for row in result}


async def _seed(session: AsyncSession, keys: tuple[str, ...], slots: tuple[str, ...]) -> None:
    await session.execute(
        text("DELETE FROM system_settings WHERE key = ANY(:k)"), {"k": list(keys)}
    )
    await session.execute(
        text("DELETE FROM llm_config_overrides WHERE llm_type = ANY(:s)"), {"s": list(slots)}
    )
    for key in keys:
        await session.execute(
            text(
                "INSERT INTO system_settings (id, key, value, created_at, updated_at) "
                "VALUES (:id, :key, 'true', now(), now())"
            ),
            {"id": uuid4(), "key": key},
        )
    for slot in slots:
        await session.execute(
            text(
                "INSERT INTO llm_config_overrides (id, llm_type, created_at, updated_at) "
                "VALUES (:id, :slot, now(), now())"
            ),
            {"id": uuid4(), "slot": slot},
        )


def test_the_retired_names_are_names_the_code_no_longer_reads() -> None:
    declared = {key.name for key in SystemSettingKey}
    assert not set(RETIRED_KEYS) & declared
    assert not set(RETIRED_SLOTS) & set(LLM_TYPES_REGISTRY)
    assert set(_KEPT_KEYS) <= declared


@pytest.mark.asyncio
async def test_the_retirements_take_their_rows_and_leave_every_other(
    async_session: AsyncSession,
) -> None:
    session = async_session
    await _seed(session, (*RETIRED_KEYS, *_KEPT_KEYS), (*RETIRED_SLOTS, *_KEPT_SLOTS))

    await _migrate(session, PREVIEWS.upgrade)
    await _migrate(session, INITIATIVE.upgrade)

    assert not await _settings(session) & set(RETIRED_KEYS)
    assert set(_KEPT_KEYS) <= await _settings(session)
    assert not await _slots(session) & set(RETIRED_SLOTS)
    assert set(_KEPT_SLOTS) <= await _slots(session)

    # The downgrades write nothing back: the former code reads a missing switch as off.
    await _migrate(session, INITIATIVE.downgrade)
    await _migrate(session, PREVIEWS.downgrade)
    assert not await _settings(session) & set(RETIRED_KEYS)


@pytest.mark.asyncio
async def test_a_downgrade_forgets_the_thresholds_the_former_code_cannot_read(
    async_session: AsyncSession,
) -> None:
    session = async_session
    stored = ("JEV_EMAIL_CLASSIFICATION_THRESHOLDS", "JEV_RADIO_VERIFICATION_THRESHOLDS")
    await _seed(session, (*stored, *_KEPT_KEYS), ())

    await _migrate(session, THRESHOLDS.upgrade)
    assert set(stored) <= await _settings(session)

    await _migrate(session, THRESHOLDS.downgrade)
    assert not await _settings(session) & set(stored)
    assert set(_KEPT_KEYS) <= await _settings(session)
