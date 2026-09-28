"""A broadcast's source language survives the upgrade — on real PostgreSQL (ADR-323).

Migration ``343c834a3a07`` adds ``admin_broadcasts.source_language`` nullable,
labels every existing row with the only language the previous code ever
translated from, then requires the column. The schema this suite builds is the
POST-upgrade one, so the test re-opens the column inside the per-test outer
transaction — PostgreSQL DDL is transactional and ``async_session`` rolls the
whole transaction back at teardown — writes a row the way the previous code
did, and runs the migration's own statement: what is proven is what the upgrade
runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.notifications.models import AdminBroadcast
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_09_25_1800-343c834a3a07_broadcast_source_language.py"
)


def _load_migration() -> ModuleType:
    """The migration module itself, so its backfill SQL is what gets proven."""
    spec = importlib.util.spec_from_file_location("broadcast_source_language", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_older_broadcasts_are_labelled_and_the_column_can_then_be_required(
    async_session: AsyncSession,
) -> None:
    admin = User(
        email=f"admin-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=True,
        full_name="Admin",
    )
    async_session.add(admin)
    await async_session.flush()
    await async_session.execute(
        text("ALTER TABLE admin_broadcasts ALTER COLUMN source_language DROP NOT NULL")
    )
    # Written as the previous code wrote it: no source language at all.
    legacy = AdminBroadcast(message="Sent before the column existed", sent_by=admin.id)
    # A row that already carries its language — an upgrade resumed after the
    # backfill must never relabel it.
    labelled = AdminBroadcast(message="Already labelled", sent_by=admin.id, source_language="en")
    async_session.add_all([legacy, labelled])
    await async_session.flush()

    await async_session.execute(text(_load_migration().BACKFILL_STATEMENT))
    # The upgrade's last step: it only succeeds when no row was left unlabelled.
    await async_session.execute(
        text("ALTER TABLE admin_broadcasts ALTER COLUMN source_language SET NOT NULL")
    )
    await async_session.refresh(legacy)
    await async_session.refresh(labelled)

    assert legacy.source_language == "fr"
    assert labelled.source_language == "en"
