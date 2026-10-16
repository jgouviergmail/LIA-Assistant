"""Upgrade/downgrade executes on a private PostgreSQL schema, with legacy data."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.psyche.efficacy_models import EfficacyEpisode

pytestmark = pytest.mark.integration


def _exercise(connection: Connection) -> None:
    schema = f"efficacy_migration_{uuid4().hex}"
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
    connection.execute(
        text(
            "CREATE TABLE psyche_states (id uuid PRIMARY KEY, user_id uuid REFERENCES users(id), self_efficacy jsonb)"
        )
    )
    owner, state = uuid4(), uuid4()
    connection.execute(text("INSERT INTO users (id) VALUES (:owner)"), {"owner": owner})
    connection.execute(
        text(
            "INSERT INTO psyche_states (id,user_id,self_efficacy) VALUES (:state,:owner,CAST(:legacy AS jsonb))"
        ),
        {"state": state, "owner": owner, "legacy": '{"technical":{"score":0.9,"weight":10}}'},
    )
    source = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_16_1100-c8d1f4260e77_psyche_efficacy_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("efficacy_evidence_migration", source)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
        inspector = inspect(connection)
        columns = {
            column["name"]: column for column in inspector.get_columns("psyche_efficacy_episodes")
        }
        assert set(columns) == set(EfficacyEpisode.__table__.columns.keys())
        assert {
            item["name"] for item in inspector.get_unique_constraints("psyche_efficacy_episodes")
        } == {"uq_efficacy_episode_run", "uq_efficacy_episode_message"}
        assert (
            connection.scalar(text("SELECT efficacy_generation IS NOT NULL FROM psyche_states"))
            is True
        )
        assert connection.scalar(text("SELECT efficacy_profile IS NULL FROM psyche_states")) is True
        assert connection.scalar(text("SELECT COUNT(*) FROM psyche_efficacy_episodes")) == 0
        assert (
            connection.scalar(
                text("SELECT self_efficacy->'technical'->>'score' FROM psyche_states")
            )
            == "0.9"
        )
        migration.downgrade()
        assert "psyche_efficacy_episodes" not in inspect(connection).get_table_names()
        assert {column["name"] for column in inspect(connection).get_columns("psyche_states")} == {
            "id",
            "user_id",
            "self_efficacy",
        }
        assert connection.scalar(text("SELECT COUNT(*) FROM psyche_states")) == 1
        migration.upgrade()
        assert connection.scalar(text("SELECT COUNT(*) FROM psyche_efficacy_episodes")) == 0
    connection.execute(text("SET LOCAL search_path TO public"))
    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


async def test_efficacy_migration_round_trip_preserves_legacy_without_inventing_evidence(
    async_session: AsyncSession,
) -> None:
    await async_session.run_sync(lambda db: _exercise(db.connection()))
