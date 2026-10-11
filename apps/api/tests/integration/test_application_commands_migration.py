"""Execute the real migration twice, proving its schema matches the ORM owner."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_models import ApplicationCommand

pytestmark = pytest.mark.integration


async def test_application_command_upgrade_downgrade_and_reupgrade(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_06_1800-c29fba860e13_application_commands.py"
    )
    spec = importlib.util.spec_from_file_location("application_commands_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    origin_path = path.with_name("2026_10_07_1330-d38fa76219bc_application_command_origin.py")
    origin_spec = importlib.util.spec_from_file_location(
        "application_origin_migration", origin_path
    )
    assert origin_spec is not None and origin_spec.loader is not None
    origin_module = importlib.util.module_from_spec(origin_spec)
    origin_spec.loader.exec_module(origin_module)

    def qualify(connection: Connection) -> None:
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(connection)))
        monkeypatch.setattr(origin_module, "op", Operations(MigrationContext.configure(connection)))
        # Existing fixtures start at the current ORM schema. Qualify both historical
        # base creation and its additive successor without weakening parity checks.
        origin_module.downgrade()
        module.downgrade()
        assert "application_commands" not in inspect(connection).get_table_names()
        for _ in range(2):
            module.upgrade()
            origin_module.upgrade()
            inspector = inspect(connection)
            columns = {
                column["name"]: column for column in inspector.get_columns("application_commands")
            }
            assert set(columns) == set(ApplicationCommand.__table__.columns.keys())
            for column in ApplicationCommand.__table__.columns:
                assert columns[column.name]["nullable"] == column.nullable
            assert (
                inspector.get_foreign_keys("application_commands")[0]["options"]["ondelete"]
                == "CASCADE"
            )
            assert inspector.get_unique_constraints("application_commands")[0]["column_names"] == [
                "draft_id"
            ]
            indexes = {
                index["name"]: index for index in inspector.get_indexes("application_commands")
            }
            assert indexes["ix_application_commands_actor_phase"]["column_names"] == [
                "actor_id",
                "phase",
            ]
            origin_module.downgrade()
            module.downgrade()
        module.upgrade()
        origin_module.upgrade()

    await (await async_session.connection()).run_sync(qualify)
