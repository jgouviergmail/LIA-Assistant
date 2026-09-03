"""Guard: the template-library migration (ADR-259) says on disk what the models say in code.

The migration is read as a FILE (never executed here): its chain, the columns
it adds, the index and column it drops, and the symmetry of its downgrade are
asserted against the SQLAlchemy models — a column present in the model but
absent from the migration would only fail on the next deployment.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from src.domains.meetings.models import Meeting, MeetingPreference, MeetingTemplate

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_09_03_1200-e0f1a2b3c4d5_meeting_template_library.py"
)

#: Columns the migration adds, per table — the model is the oracle below.
ADDED = {
    "meeting_templates": ("description", "category", "builtin_key"),
    "meeting_preferences": ("default_template_ref",),
    "meetings": (
        "template_ref",
        "template_name",
        "template_selection",
        "template_selection_reason",
        "source_meeting_id",
    ),
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("meeting_template_library", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function_source(name: str) -> str:
    tree = ast.parse(_MIGRATION.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(_MIGRATION.read_text(encoding="utf-8"), node) or ""
    raise AssertionError(f"{name}() not found in the migration")


def test_the_migration_chains_after_the_stt_pricing_seed() -> None:
    module = _load_migration()
    assert module.revision == "e0f1a2b3c4d5"
    assert module.down_revision == "c8d9e0f1a2b3"


def test_every_added_column_exists_in_the_model_and_in_upgrade() -> None:
    upgrade = _function_source("upgrade")
    models = {
        "meeting_templates": MeetingTemplate,
        "meeting_preferences": MeetingPreference,
        "meetings": Meeting,
    }
    for table, columns in ADDED.items():
        for column in columns:
            assert column in models[table].__table__.c, f"{table}.{column} missing in the model"
            assert f'"{column}"' in upgrade, f"{table}.{column} not added by upgrade()"


def test_upgrade_drops_the_single_default_contract_and_downgrade_restores_it() -> None:
    upgrade = _function_source("upgrade")
    downgrade = _function_source("downgrade")
    assert "uq_meeting_templates_one_default_per_user" in upgrade
    assert 'drop_column("meeting_templates", "is_default")' in upgrade
    assert "is_default" not in MeetingTemplate.__table__.c
    # Symmetry: what upgrade drops, downgrade recreates; what upgrade adds, downgrade drops.
    assert '"is_default"' in downgrade
    assert "uq_meeting_templates_one_default_per_user" in downgrade
    for table, columns in ADDED.items():
        for column in columns:
            assert f'drop_column("{table}", "{column}")' in downgrade, f"{table}.{column}"
    assert "ix_meetings_source" in upgrade and "ix_meetings_source" in downgrade


def test_the_derived_link_is_nullable_and_survives_the_source_deletion() -> None:
    column = Meeting.__table__.c.source_meeting_id
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "meetings"
    assert fk.ondelete == "SET NULL"


def test_template_rows_default_to_the_custom_category() -> None:
    column = MeetingTemplate.__table__.c.category
    assert column.nullable is False
    assert column.server_default is not None
    assert str(column.server_default.arg).strip("'") == "custom"
