"""Completeness guard for the user-data classification registry.

Closes the defect class where a new user-scoped table (or a new PII column on
``users``) silently escapes BOTH the account-deletion purge (ADR-067) and the
GDPR export: every SQLAlchemy table and every ``users`` column MUST be
deliberately classified in ``src/domains/users/user_data_map.py``, and the
classification MUST stay consistent with what the purge actually deletes.

Pattern: ADR-085 registry completeness assert, applied at CI level over the
full model metadata (total classification — a direct-FK census would miss
``conversation_messages``, which has no ``user_id`` column).
"""

import uuid

import pytest

from src.domains.users.account_deletion_service import build_purge_statements
from src.domains.users.models import User
from src.domains.users.user_data_map import (
    EXTERNAL_TABLES,
    TABLE_RULES,
    USER_COLUMNS,
    ExportPolicy,
    TableDataClass,
    UserColumnClass,
)
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base

import_all_models()


@pytest.mark.unit
class TestTableClassificationCompleteness:
    """Every metadata table is deliberately classified — no silent escapes."""

    def test_every_metadata_table_is_classified(self) -> None:
        """A new table not present in TABLE_RULES must fail CI loudly."""
        metadata_tables = set(Base.metadata.tables)
        unclassified = metadata_tables - set(TABLE_RULES)
        assert not unclassified, (
            f"Unclassified tables {sorted(unclassified)}: add a deliberate "
            "TableRule (purge + export decision) to user_data_map.TABLE_RULES."
        )

    def test_no_stale_classification_entries(self) -> None:
        """A dropped table must be removed from TABLE_RULES (no dead entries)."""
        metadata_tables = set(Base.metadata.tables)
        stale = set(TABLE_RULES) - metadata_tables
        assert not stale, (
            f"TABLE_RULES entries without a metadata table: {sorted(stale)} — "
            "remove them or fix the table name."
        )

    def test_external_tables_are_not_metadata_tables(self) -> None:
        """EXTERNAL_TABLES documents out-of-band tables only (LangGraph, alembic)."""
        overlap = EXTERNAL_TABLES & set(Base.metadata.tables)
        assert not overlap, (
            f"{sorted(overlap)} are SQLAlchemy metadata tables — classify them "
            "in TABLE_RULES, not EXTERNAL_TABLES."
        )


@pytest.mark.unit
class TestPurgeClassificationConsistency:
    """The purge statement list and the classification agree exactly."""

    def test_purged_tables_match_user_purged_classification(self) -> None:
        """USER_PURGED classification ⇔ an explicit DELETE in the purge."""
        purged = {name for name, _ in build_purge_statements(uuid.uuid4())}
        classified_purged = {
            name
            for name, rule in TABLE_RULES.items()
            if rule.data_class is TableDataClass.USER_PURGED
        }
        missing_delete = classified_purged - purged
        assert not missing_delete, (
            f"Classified USER_PURGED but not deleted by the purge: "
            f"{sorted(missing_delete)} — add the DELETE to build_purge_statements."
        )
        missing_rule = purged - classified_purged
        assert not missing_rule, (
            f"Deleted by the purge but not classified USER_PURGED: "
            f"{sorted(missing_rule)} — fix TABLE_RULES."
        )

    def test_cascade_tables_have_cascading_fk_to_purged_chain(self) -> None:
        """USER_CASCADE tables really cascade from a purged (or cascaded) parent.

        A USER_CASCADE classification with no ondelete=CASCADE FK into the
        purged chain would silently survive account deletion.
        """
        purged_or_cascaded = {
            name
            for name, rule in TABLE_RULES.items()
            if rule.data_class in (TableDataClass.USER_PURGED, TableDataClass.USER_CASCADE)
        }
        for name, rule in TABLE_RULES.items():
            if rule.data_class is not TableDataClass.USER_CASCADE:
                continue
            table = Base.metadata.tables[name]
            cascading_parents = {
                fk.column.table.name
                for fk in table.foreign_keys
                if fk.ondelete is not None and fk.ondelete.upper() == "CASCADE"
            }
            assert cascading_parents & purged_or_cascaded, (
                f"{name} is classified USER_CASCADE but has no ondelete=CASCADE "
                f"FK into the purged chain (found parents: {sorted(cascading_parents)})."
            )

    def test_users_row_is_scrubbed_class(self) -> None:
        """The users table is the special scrubbed-in-place row."""
        assert TABLE_RULES["users"].data_class is TableDataClass.USER_ROW_SCRUBBED

    def test_excluded_and_retained_rules_carry_a_reason(self) -> None:
        """Every non-obvious decision is auditable: reason is mandatory."""
        for name, rule in TABLE_RULES.items():
            if rule.export is ExportPolicy.EXCLUDED or rule.data_class in (
                TableDataClass.BILLING_RETAINED,
                TableDataClass.GLOBAL,
            ):
                assert rule.reason.strip(), f"{name}: empty reason on a non-obvious rule."


@pytest.mark.unit
class TestUserColumnClassificationCompleteness:
    """Every users column is deliberately classified (journal_portrait defect class)."""

    def test_every_user_column_is_classified(self) -> None:
        """A new users column must be classified before it can ship."""
        columns = set(User.__table__.columns.keys())
        unclassified = columns - set(USER_COLUMNS)
        assert not unclassified, (
            f"Unclassified users columns {sorted(unclassified)}: decide "
            "scrubbed/retained in user_data_map.USER_COLUMNS."
        )

    def test_no_stale_user_column_entries(self) -> None:
        """A dropped users column must leave USER_COLUMNS."""
        columns = set(User.__table__.columns.keys())
        stale = set(USER_COLUMNS) - columns
        assert not stale, f"USER_COLUMNS entries without a column: {sorted(stale)}."

    def test_scrubbed_set_is_nonempty_and_contains_known_pii(self) -> None:
        """Sanity: the scrub classification covers the audited PII columns."""
        scrubbed = {name for name, cls in USER_COLUMNS.items() if cls is UserColumnClass.SCRUBBED}
        assert {
            "hashed_password",
            "home_location_encrypted",
            "last_known_location_encrypted",
            "journal_portrait_full",
        } <= scrubbed
