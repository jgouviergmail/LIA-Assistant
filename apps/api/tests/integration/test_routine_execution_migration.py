"""The real reservation DDL upgrades and downgrades without altering routine data."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_actual_reservation_migration_keeps_existing_rows_and_starts_unreserved(
    async_session: AsyncSession, test_user: User
) -> None:
    row = await ScheduledActionService(async_session).create(
        test_user.id,
        ScheduledActionCreate(
            title="Keep",
            action_prompt="Read tasks",
            trigger_kind="condition",
            condition_config=ConditionConfig(type="task_overdue"),
        ),
        "Europe/Paris",
    )
    await async_session.flush()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_07_2300-e47c0a52d9f1_routine_execution_reservation.py"
    )
    spec = importlib.util.spec_from_file_location("routine_execution_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def round_trip(db: Session) -> None:
        with Operations.context(MigrationContext.configure(db.connection())):
            migration.downgrade()
            assert (
                db.scalar(
                    text("SELECT title FROM scheduled_actions WHERE id = :id"), {"id": row.id}
                )
                == "Keep"
            )
            migration.upgrade()
            assert (
                db.scalar(
                    text("SELECT execution_token FROM scheduled_actions WHERE id = :id"),
                    {"id": row.id},
                )
                is None
            )
            assert (
                db.scalar(
                    text("SELECT action_prompt FROM scheduled_actions WHERE id = :id"),
                    {"id": row.id},
                )
                == "Read tasks"
            )

    await async_session.run_sync(round_trip)
