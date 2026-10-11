"""Qualify the journal revision migration on disposable PostgreSQL only."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_journal_revision_upgrade_preserves_history_and_invalidates_legacy_portrait(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = next((Path(__file__).resolve().parents[2] / "alembic/versions").glob("*a92d4e713b60*"))
    spec = importlib.util.spec_from_file_location("journal_revision_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "f19c83e2a6b0"

    item = JournalEntry(
        id=uuid4(),
        user_id=test_user.id,
        theme="learnings",
        title="Legacy rule",
        content="WHEN preparing a report DO cite its sources.",
        mood="reflective",
        status="active",
        source="conversation",
        char_count=50,
        confidence="high",
        evidence_count=17,
        contradiction_count=2,
        injection_count=23,
        level="L1",
    )
    async_session.add(item)
    test_user.journal_portrait_full = "LEGACY FULL"
    test_user.journal_portrait_brief = "LEGACY BRIEF"
    test_user.journal_portrait_compiled_at = datetime.now(UTC)
    test_user.journal_portrait_sources = {"version": 1, "journal_entries": 1, "sources": {}}
    await async_session.flush()
    entry_id, user_id = item.id, test_user.id

    def qualify(connection: Connection) -> None:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        before = inspect(connection)
        assert "journal_evidence_events" not in before.get_table_names()
        assert "revision" not in {c["name"] for c in before.get_columns("journal_entries")}
        assert "journal_revision" not in {c["name"] for c in before.get_columns("users")}

        for _ in range(2):
            migration.upgrade()
            inspector = inspect(connection)
            for table_name, model, column_names in (
                ("journal_entries", JournalEntry, ("revision",)),
                (
                    "users",
                    User,
                    (
                        "journal_revision",
                        "journal_consolidated_revision",
                        "journal_last_attempted_at",
                        "journal_last_attempt_status",
                        "journal_consolidation_owner",
                        "journal_consolidation_held_until",
                    ),
                ),
            ):
                actual = {column["name"]: column for column in inspector.get_columns(table_name)}
                for name in column_names:
                    declared = model.__table__.columns[name]
                    assert actual[name]["nullable"] == declared.nullable
                    assert str(actual[name]["type"].compile(dialect=connection.dialect)) == str(
                        declared.type.compile(dialect=connection.dialect)
                    )
            event_columns = {c["name"]: c for c in inspector.get_columns("journal_evidence_events")}
            assert set(event_columns) == set(JournalEvidenceEvent.__table__.columns.keys())
            for column in JournalEvidenceEvent.__table__.columns:
                assert event_columns[column.name]["nullable"] == column.nullable
                assert str(
                    event_columns[column.name]["type"].compile(dialect=connection.dialect)
                ) == str(column.type.compile(dialect=connection.dialect))
            indexes = {
                index["name"]: index for index in inspector.get_indexes("journal_evidence_events")
            }
            assert indexes["uq_journal_evidence_rule_event"]["unique"] is True
            assert indexes["uq_journal_evidence_rule_event"]["column_names"] == [
                "journal_entry_id",
                "rule_revision",
                "event_key",
            ]
            assert indexes["ix_journal_evidence_user"]["column_names"] == ["user_id"]
            foreign_keys = {
                tuple(fk["constrained_columns"]): fk
                for fk in inspector.get_foreign_keys("journal_evidence_events")
            }
            assert foreign_keys[("user_id",)]["options"]["ondelete"] == "CASCADE"
            assert foreign_keys[("journal_entry_id",)]["options"]["ondelete"] == "CASCADE"
            assert foreign_keys[("source_conversation_id",)]["options"]["ondelete"] == "SET NULL"
            for columns, referenced_table in (
                (("user_id",), "users"),
                (("journal_entry_id",), "journal_entries"),
                (("source_conversation_id",), "conversations"),
            ):
                assert foreign_keys[columns]["referred_table"] == referenced_table
                assert foreign_keys[columns]["referred_columns"] == ["id"]
            checks = {c["name"] for c in inspector.get_check_constraints("journal_evidence_events")}
            assert {
                constraint.name
                for constraint in JournalEvidenceEvent.__table__.constraints
                if constraint.name and str(constraint.name).startswith("ck_")
            } <= checks

            event_insert = text(
                "INSERT INTO journal_evidence_events "
                "(id, user_id, journal_entry_id, rule_revision, event_key, outcome, captured_at) "
                "VALUES (:id, :user_id, :entry_id, :revision, :event_key, :outcome, now())"
            )
            valid_event = {
                "id": uuid4(),
                "user_id": user_id,
                "entry_id": entry_id,
                "revision": 1,
                "event_key": "reaction:one",
                "outcome": "evidence",
            }
            connection.execute(event_insert, valid_event)
            for invalid_values in (
                {"event_key": "bad-outcome", "outcome": "unsupported"},
                {"event_key": "bad-revision", "revision": 0},
                {},  # the same event identity cannot qualify this revision twice
            ):
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(
                            event_insert, {**valid_event, "id": uuid4(), **invalid_values}
                        )

            rule = connection.execute(
                text(
                    "SELECT revision, confidence, evidence_count, contradiction_count, injection_count "
                    "FROM journal_entries WHERE id=:entry_id"
                ),
                {"entry_id": entry_id},
            ).one()
            assert tuple(rule) == (1, "medium", 17, 2, 23)
            user = connection.execute(
                text(
                    "SELECT journal_revision, journal_consolidated_revision, journal_portrait_full, "
                    "journal_portrait_brief, journal_portrait_compiled_at, journal_portrait_sources "
                    "FROM users WHERE id=:user_id"
                ),
                {"user_id": user_id},
            ).one()
            assert tuple(user) == (0, None, None, None, None, None)
            migration.downgrade()
        migration.upgrade()

    await (await async_session.connection()).run_sync(qualify)
