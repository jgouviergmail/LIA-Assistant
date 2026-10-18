"""Qualify the additive transfer schema in both directions on real PostgreSQL."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.capability_models import (
    PeerCapabilityComponent,
    PeerCapabilityTransfer,
)

pytestmark = pytest.mark.integration


async def test_peer_capability_upgrade_downgrade_reupgrade(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_18_1800-a94e30f821b6_peer_capability_transfers.py"
    )
    spec = importlib.util.spec_from_file_location("peer_capability_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    offline_spec = importlib.util.spec_from_file_location(
        "offline_install_migration",
        path.with_name("2026_10_18_1830-b05f41e932c7_offline_capability_installation.py"),
    )
    assert offline_spec is not None and offline_spec.loader is not None
    offline = importlib.util.module_from_spec(offline_spec)
    offline_spec.loader.exec_module(offline)

    def qualify(connection: Connection) -> None:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        monkeypatch.setattr(offline, "op", Operations(MigrationContext.configure(connection)))
        offline.downgrade()
        migration.downgrade()
        for _ in range(2):
            assert "peer_capability_transfers" not in inspect(connection).get_table_names()
            migration.upgrade()
            offline.upgrade()
            inspector = inspect(connection)
            for model in (PeerCapabilityTransfer, PeerCapabilityComponent):
                actual = {
                    column["name"]: column for column in inspector.get_columns(model.__tablename__)
                }
                assert set(actual) == set(model.__table__.columns.keys())
                assert {name: column["nullable"] for name, column in actual.items()} == {
                    column.name: column.nullable for column in model.__table__.columns
                }
            assert "peer_authored" in {column["name"] for column in inspector.get_columns("skills")}
            offline.downgrade()
            migration.downgrade()
        migration.upgrade()
        offline.upgrade()

    await (await async_session.connection()).run_sync(qualify)
