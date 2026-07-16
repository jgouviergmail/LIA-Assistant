"""Unit coverage for the structural-drift policy (audit F042).

These tests pin the *classification* logic — which objects are excluded and which
autogenerate operations count as cosmetic — without needing a live database. The
end-to-end structural equivalence itself is asserted by the from-scratch replay
gate (``scripts/db/check_migrations_replay.sh``, step 5).
"""

from src.infrastructure.database.schema_drift import (
    COSMETIC_DIFF_OPS,
    MIGRATION_BRIDGE_TABLES,
    RUNTIME_MANAGED_INDEXES,
    RUNTIME_MANAGED_TABLES,
    _op_name,
    include_object,
)


class TestIncludeObject:
    def test_excludes_runtime_managed_tables(self):
        for table in RUNTIME_MANAGED_TABLES:
            assert include_object(None, table, "table", True, None) is False

    def test_excludes_migration_bridge_tables(self):
        for table in MIGRATION_BRIDGE_TABLES:
            assert include_object(None, table, "table", True, None) is False

    def test_excludes_un_round_trippable_indexes(self):
        for index in RUNTIME_MANAGED_INDEXES:
            assert include_object(None, index, "index", True, None) is False

    def test_includes_ordinary_table_and_index(self):
        assert include_object(None, "users", "table", True, None) is True
        assert include_object(None, "ix_users_email", "index", True, None) is True

    def test_includes_non_table_non_index_types(self):
        # Columns, constraints, etc. are always compared.
        assert include_object(None, "some_column", "column", True, None) is True

    def test_filters_both_reflected_and_metadata_side(self):
        # DESC-ordered indexes live in the ORM too, so they must be excluded
        # regardless of the ``reflected`` flag (that is why include_object, not
        # include_name, is used).
        assert include_object(None, "ix_token_usage_logs_created_at", "index", True, None) is False
        assert include_object(None, "ix_token_usage_logs_created_at", "index", False, None) is False


class TestCosmeticClassification:
    def test_only_server_default_is_cosmetic(self):
        # Comments are now reconciled by migration (F042) and part of the
        # contract; only server_default remains cosmetic.
        assert COSMETIC_DIFF_OPS == {"modify_default"}

    def test_structural_ops_are_not_cosmetic(self):
        for structural in (
            "add_table",
            "remove_table",
            "add_column",
            "remove_column",
            "modify_type",
            "modify_nullable",
            "add_index",
            "remove_index",
            "add_constraint",
            "remove_constraint",
            # comments are now detected drift, not cosmetic:
            "modify_comment",
            "add_table_comment",
            "remove_table_comment",
        ):
            assert structural not in COSMETIC_DIFF_OPS

    def test_op_name_extracts_first_tuple_element(self):
        assert _op_name(("add_index", object())) == "add_index"
        assert _op_name(["modify_nullable", None, "t", "c"]) == "modify_nullable"

    def test_op_name_returns_none_for_non_op(self):
        assert _op_name(object()) is None
        assert _op_name(()) is None
        assert _op_name((123, "x")) is None
