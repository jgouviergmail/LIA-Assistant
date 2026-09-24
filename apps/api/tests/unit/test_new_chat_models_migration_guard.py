"""The 2026-09-23 chat-models migration and the reference seed are ONE source.

Production never replays the seed bundle, so ``f6c2a8e4b0d7`` carries the eight
models the seed gained to upgraded instances. Two copies of the same rows drift
unless something holds them equal: this guard reads both.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_09_23_1400-f6c2a8e4b0d7_seed_new_chat_models.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_new_chat_models", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_seed_text(column: str, value: Any) -> str:
    """How the seed's VALUES tuple spells a migration value."""
    if value is None:
        return "NULL"
    if column == "reasoning_enum_values":
        return f"{json.dumps(value)}'::jsonb"
    return str(value).lower()


def test_the_migration_chains_after_the_weekday_migration() -> None:
    module = _load()
    assert module.revision == "f6c2a8e4b0d7"
    assert module.down_revision == "e4a7c2f9b1d6"


def test_every_migrated_catalogue_row_equals_its_seed_row() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for row in module.CATALOGUE_ROWS:
        seed_row = seed_rows.get(row["model_name"])
        assert seed_row is not None, f"{row['model_name']} is migrated but not seeded"
        mismatches = {
            column: (value, seed_row[column])
            for column, value in row.items()
            if _as_seed_text(column, value) != seed_row[column]
        }
        assert mismatches == {}, f"{row['model_name']}: {mismatches}"


def test_every_migrated_tariff_equals_the_seed_bundles_active_row() -> None:
    module = _load()
    seed = _SEED.read_text(encoding="utf-8")
    active = {
        m.group("model"): m for m in _SEED_TARIFF.finditer(seed) if m.group("active") == "true"
    }
    assert set(module.TARIFFS) == {row["model_name"] for row in module.CATALOGUE_ROWS}
    for name, (input_price, cached_price, output_price) in module.TARIFFS.items():
        bundle = active.get(name)
        assert bundle is not None, f"{name} has no active tariff in the seed bundle"
        assert bundle.group("effective") == module.EFFECTIVE_FROM, name
        assert bundle.group("unit") == module.PRICING_UNIT, name
        assert (
            float(bundle.group("input")),
            float(bundle.group("cached")),
            float(bundle.group("output")),
        ) == (input_price, cached_price, output_price), name


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands; a price already active stands."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    tariff = str(module.INSERT_TARIFF)
    assert "NOT EXISTS" in tariff and "p.is_active" in tariff
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in tariff
