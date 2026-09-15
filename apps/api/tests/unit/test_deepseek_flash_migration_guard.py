"""Guard: the deepseek-flash migration and the reference seed bundle describe the same rows.

Production never replays the seed bundle, so the migration is what an upgraded
instance gets; a fresh install gets the bundle. If the two drifted, the same
model would be priced or profiled two ways depending on how the instance was
born — the defect class ADR-228 closed for the chat models, and the reason
``seed_meetings_stt_pricing`` carries the same guard.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from src.infrastructure.llm.reasoning.profiles import (
    DEEPSEEK_THINKING_PREFIXES,
    resolve_reasoning_profile,
)
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_09_12_1500-e9b5d7f3a2c4_deepseek_flash_catalogue.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"

_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_SEED_WINDOWS = re.compile(
    r"UPDATE llm_model_pricing p\s+SET input_unit_price = (?P<input>[0-9.]+),\s+"
    r"cached_input_unit_price = (?P<cached>[0-9.]+),\s+output_unit_price = (?P<output>[0-9.]+),\s+"
    r"time_slots = '(?P<slots>\[.*?\])'::jsonb\s+FROM llm_models m\s+"
    r"WHERE m\.id = p\.model_id AND m\.model_name = 'deepseek-flash' AND p\.is_active;",
    re.S,
)


def _load_migration():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("deepseek_flash_catalogue", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_chains_after_the_bookmarks_head() -> None:
    module = _load_migration()
    assert module.revision == "e9b5d7f3a2c4"
    assert module.down_revision == "d8a4c6e2f7b1"


def test_the_migrated_catalogue_row_equals_the_seed_row() -> None:
    module = _load_migration()
    seed_row = {row["model_name"]: row for row in _catalogue_rows()}[module.MODEL_NAME]
    for column, value in module.CATALOGUE_ROW.items():
        if column == "reasoning_enum_values":
            assert seed_row[column].startswith(json.dumps(value)), column
        else:
            assert seed_row[column] == str(value).lower(), column


def test_the_migrated_tariff_equals_the_seed_bundle_row_and_its_windows() -> None:
    module = _load_migration()
    seed = _SEED.read_text(encoding="utf-8")
    bundle = next(
        m
        for m in _SEED_TARIFF.finditer(seed)
        if m.group("model") == module.MODEL_NAME and m.group("active") == "true"
    )
    assert bundle.group("effective") == module.EFFECTIVE_FROM
    assert bundle.group("unit") == module.PRICING_UNIT
    windows = _SEED_WINDOWS.search(seed)
    assert windows is not None, "the seed carries no UTC windows for deepseek-flash"
    assert float(windows.group("input")) == module.OFF_PEAK["input"]
    assert float(windows.group("cached")) == module.OFF_PEAK["cached"]
    assert float(windows.group("output")) == module.OFF_PEAK["output"]
    assert json.loads(windows.group("slots")) == module.TIME_SLOTS


def test_the_tariff_insert_never_overrides_an_administered_price() -> None:
    """The SQL adds a tariff only where none is active — never on top of an admin's."""
    sql = str(_load_migration()._INSERT_TARIFF)
    assert "NOT EXISTS" in sql and "p.is_active" in sql
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in sql
    assert "SET is_active = true" in sql


def test_the_catalogue_insert_never_overrides_an_existing_row() -> None:
    """Production created its row by hand (provenance ``verified``); it must stand."""
    sql = str(_load_migration()._INSERT_MODEL)
    assert "ON CONFLICT (model_name) DO NOTHING" in sql


def test_the_ladder_rewrite_targets_the_family_and_the_documented_ladder() -> None:
    """``low`` joins the family's declared ladders; anything else is left alone."""
    module = _load_migration()
    assert module.LADDER == list(resolve_reasoning_profile("deepseek", "deepseek-flash").levels)
    assert module.THINKING_PREFIXES == DEEPSEEK_THINKING_PREFIXES
    assert module._widen_ladder(["none", "high", "max"]) == ["none", "low", "high", "max"]
    # an administered narrowing that never carried the depths stays as it is
    assert module._widen_ladder(["none", "max"]) == ["none", "max"]
    assert module._widen_ladder(["none", "low", "high", "max"]) == ["none", "low", "high", "max"]
