"""Prove the icon-style rollout and account persistence on real PostgreSQL.

The revision runs both ways on the test's rolled-back transaction. Its server
default reaches pre-existing rows and SQL inserts, independently of ORM defaults.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.constants import USER_ICON_STYLE_DEFAULT, USER_ICON_STYLES
from src.domains.users.models import User
from src.domains.users.schemas import UserProfile, UserUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_11_08_0500-a4c92e7b6d81_user_icon_style.py"
)


def _load_migration() -> ModuleType:
    """Load the production revision, never a restated DDL approximation."""
    spec = importlib.util.spec_from_file_location("user_icon_style", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _migrate(session: AsyncSession, step: Callable[[], None]) -> None:
    """Execute the revision inside the disposable transaction owned by the test."""

    def run(sync_session: Session) -> None:
        with Operations.context(MigrationContext.configure(sync_session.connection())):
            step()

    await session.run_sync(run)


async def test_rollout_backfills_existing_accounts_and_defaults_new_sql_inserts(
    async_session: AsyncSession,
) -> None:
    """Upgrade and re-upgrade populate every row and enforce the closed vocabulary."""
    migration = _load_migration()
    existing = [User(email=f"icons-{uuid4().hex}@example.com") for _ in range(2)]
    async_session.add_all(existing)
    await async_session.flush()
    ids = [user.id for user in existing]
    await _migrate(async_session, migration.downgrade)
    await _migrate(async_session, migration.upgrade)
    values = (
        (
            await async_session.execute(
                text("SELECT icon_style FROM users WHERE id IN (:a, :b)"),
                {"a": ids[0], "b": ids[1]},
            )
        )
        .scalars()
        .all()
    )
    assert values == [USER_ICON_STYLE_DEFAULT, USER_ICON_STYLE_DEFAULT]

    inserted = await async_session.scalar(
        text(
            "INSERT INTO users (id, email, is_active, is_verified, is_superuser, created_at, updated_at) "
            "VALUES (:id, :email, false, false, false, now(), now()) RETURNING icon_style"
        ),
        {"id": uuid4(), "email": f"icons-new-{uuid4().hex}@example.com"},
    )
    assert inserted == USER_ICON_STYLE_DEFAULT
    for invalid in (None, "iconpark"):
        with pytest.raises(IntegrityError):
            async with async_session.begin_nested():
                await async_session.execute(
                    text("UPDATE users SET icon_style = :style WHERE id = :id"),
                    {"style": invalid, "id": ids[0]},
                )


async def test_profile_updates_are_persisted_per_account(async_session: AsyncSession) -> None:
    """A chosen style reaches the profile response and leaves the other account alone."""
    first = User(email=f"icons-first-{uuid4().hex}@example.com", is_active=True)
    second = User(email=f"icons-second-{uuid4().hex}@example.com", is_active=True)
    async_session.add_all([first, second])
    await async_session.flush()
    service = UserService(async_session)
    for style in USER_ICON_STYLES:
        profile = await service.update_user(
            first.id, UserUpdate.model_validate({"icon_style": style})
        )
        assert profile.icon_style == style
        await async_session.refresh(first)
        await async_session.refresh(second)
        assert UserProfile.model_validate(first).icon_style == style
        assert second.icon_style == USER_ICON_STYLE_DEFAULT
