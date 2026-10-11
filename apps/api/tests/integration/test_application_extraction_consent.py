"""Explicit consent changes invalidate already-running extraction leases."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_consent_revision_migration_can_upgrade_rollback_and_reupgrade(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_06_1900-f19c83e2a6b0_extraction_revision.py"
    )
    spec = importlib.util.spec_from_file_location("extraction_revision_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def qualify(connection: Connection) -> None:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        module.downgrade()
        assert "extraction_revision" not in {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        for _ in range(2):
            module.upgrade()
            column = next(
                column
                for column in inspect(connection).get_columns("users")
                if column["name"] == "extraction_revision"
            )
            assert not column["nullable"]
            assert str(column["type"]) == "BIGINT"
            assert column["default"] in {"0", "'0'::bigint"}
            module.downgrade()
        module.upgrade()

    await (await async_session.connection()).run_sync(qualify)


async def test_reenabled_memory_does_not_reauthorize_an_old_extraction(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    test_user.memory_enabled = True
    await async_session.commit()
    before = await snapshot_extraction_consent(async_session, test_user.id, ExtractionKind.MEMORY)
    assert before is not None
    await update_assistant_preferences(
        async_session, test_user.id, AssistantPreferencePatch(memory_enabled=False)
    )
    assert (
        await snapshot_extraction_consent(async_session, test_user.id, ExtractionKind.MEMORY)
        is None
    )
    await update_assistant_preferences(
        async_session, test_user.id, AssistantPreferencePatch(memory_enabled=True)
    )
    after = await snapshot_extraction_consent(async_session, test_user.id, ExtractionKind.MEMORY)
    assert after is not None and after > before
    assert (
        await snapshot_extraction_consent(
            async_session,
            test_user.id,
            ExtractionKind.MEMORY,
            expected_revision=before,
            lock=True,
        )
        is None
    )
