"""Export completeness + exclusion guards (security program D3).

Extends the Lot 0 classification guard to the archive builder: every table
classified FULL must be resolvable by the generic exporter (owner column or
parent route EXISTS in the metadata), redaction/decryption specs must
reference real columns, and EXCLUDED tables can never appear in the
exportable set — by construction AND by assertion.
"""

import pytest

from src.domains.account_export.builder import (
    _DECRYPTED_COLUMNS,
    _OWNER_COLUMN_OVERRIDES,
    _REDACTED_COLUMNS,
    _VIA_PARENT,
    exportable_tables,
)
from src.domains.users.user_data_map import TABLE_RULES, ExportPolicy
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base

import_all_models()


@pytest.mark.unit
class TestExportCoverage:
    """Every FULL table is exportable; no EXCLUDED table ever is."""

    def test_every_full_table_is_resolvable(self) -> None:
        """The generic exporter must know how to scope each FULL table."""
        unresolvable: list[str] = []
        for table_name in exportable_tables():
            table = Base.metadata.tables[table_name]
            if table_name in _VIA_PARENT:
                parent_name, fk_column, parent_owner = _VIA_PARENT[table_name]
                parent = Base.metadata.tables[parent_name]
                if fk_column not in table.c or parent_owner not in parent.c:
                    unresolvable.append(table_name)
                continue
            owner = _OWNER_COLUMN_OVERRIDES.get(table_name, "user_id")
            if owner not in table.c:
                unresolvable.append(table_name)
        assert not unresolvable, (
            f"FULL tables the exporter cannot scope: {unresolvable} — add an "
            "owner override or a _VIA_PARENT route in builder.py."
        )

    def test_no_excluded_table_in_exportable_set(self) -> None:
        """EXCLUDED tables (secret material) can never reach an archive."""
        excluded = {
            name for name, rule in TABLE_RULES.items() if rule.export is ExportPolicy.EXCLUDED
        }
        leak = excluded & set(exportable_tables())
        assert not leak, f"EXCLUDED tables leaked into the export set: {sorted(leak)}"

    def test_secret_tables_are_excluded(self) -> None:
        """The audited secret-material tables stay out of every archive."""
        exportable = set(exportable_tables())
        for secret_table in (
            "connectors",
            "user_mcp_servers",
            "health_metric_tokens",
            "user_fcm_tokens",
            "webauthn_credentials",
            "user_totp",
            "mfa_backup_codes",
        ):
            assert secret_table not in exportable, f"{secret_table} must never be exported"

    def test_redaction_and_decryption_specs_reference_real_columns(self) -> None:
        """A renamed column must break these specs loudly, not silently."""
        for spec in (_REDACTED_COLUMNS, _DECRYPTED_COLUMNS):
            for table_name, columns in spec.items():
                table = Base.metadata.tables[table_name]
                missing = columns - set(table.c.keys())
                assert not missing, f"{table_name}: unknown columns in spec: {sorted(missing)}"

    def test_narrative_domains_are_covered(self) -> None:
        """The dual-format promise covers the narrative domains."""
        exportable = set(exportable_tables())
        assert {"conversation_messages", "journal_entries", "memories"} <= exportable

    def test_markdown_renderer_references_real_columns(self) -> None:
        """A renamed column must break the readable rendering loudly.

        ``_render_markdown`` reads row keys with ``.get`` — a silently
        missing column would produce empty markdown instead of failing.
        """
        markdown_columns = {
            "conversation_messages": {"role", "content", "created_at"},
            "journal_entries": {"created_at", "content"},
            "memories": {"content"},
        }
        for table_name, columns in markdown_columns.items():
            table = Base.metadata.tables[table_name]
            missing = columns - set(table.c.keys())
            assert not missing, (
                f"{table_name}: _render_markdown reads missing columns {sorted(missing)} "
                "— update builder._render_markdown AND this pin together."
            )
