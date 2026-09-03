"""Guard: the STT tariff migration and the reference seed bundle describe the same rows.

Production never replays the seed bundle, so the migration is what an upgraded
instance gets; a fresh install gets the bundle. If the two drifted, the same
model would be billed two different prices depending on how the instance was
born — the exact defect class ADR-228 closed for the chat models.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_09_03_0100-c8d9e0f1a2b3_seed_meetings_stt_pricing.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"

_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_SEED_MODEL = re.compile(r"^\s*\('openai',\s*'(?P<model>[^']+)',.*'(?P<kind>audio)',", re.M)


def _load_migration():
    spec = importlib.util.spec_from_file_location("seed_meetings_stt_pricing", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_chains_after_the_meetings_schema() -> None:
    module = _load_migration()
    assert module.revision == "c8d9e0f1a2b3"
    assert module.down_revision == "b7c8d9e0f1a2"


def test_every_migrated_tariff_equals_the_seed_bundle_row() -> None:
    module = _load_migration()
    seed = _SEED.read_text(encoding="utf-8")
    active_rows = {
        m.group("model"): m
        for m in _SEED_TARIFF.finditer(seed)
        if m.group("active") == "true" and m.group("model") in dict(module.STT_TARIFFS)
    }
    assert set(active_rows) == {name for name, _ in module.STT_TARIFFS}, "seed lacks a tariff row"
    for model_name, input_price in module.STT_TARIFFS:
        row = active_rows[model_name]
        assert float(row.group("input")) == input_price, model_name
        assert row.group("cached") == "NULL" and float(row.group("output")) == 0.0, model_name
        assert row.group("unit") == module.PRICING_UNIT, model_name
        assert row.group("effective") == module.EFFECTIVE_FROM, model_name


def test_every_migrated_model_is_an_audio_row_of_the_seed_catalogue() -> None:
    module = _load_migration()
    seed_models = {
        m.group("model") for m in _SEED_MODEL.finditer(_SEED.read_text(encoding="utf-8"))
    }
    for model_name, _ in module.STT_TARIFFS:
        assert model_name in seed_models, f"{model_name} is not an audio row of the seed catalogue"


def test_the_tariff_insert_never_overrides_an_administered_price() -> None:
    """The SQL adds a tariff only where none is active — never on top of an admin's."""
    sql = str(_load_migration()._INSERT_TARIFF)
    assert "NOT EXISTS" in sql and "p.is_active" in sql
    # A retired row of OURS (same instant) is re-activated, never skipped: a
    # downgrade/upgrade cycle must not leave the model without an active tariff.
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in sql
    assert "SET is_active = true" in sql
