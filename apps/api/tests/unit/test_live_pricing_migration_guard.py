"""Guard: the live-pricing migration and the reference seed bundle describe the same rows.

Production never replays the seed bundle, so migration ``f1a3c5e7b9d2`` is what
an upgraded instance gets; a fresh install gets the bundle. If the two
drifted, the same live model would be priced two ways depending on how the
instance was born — the defect class ADR-228 closed for the chat models, and
the reason the deepseek-flash migration carries the same guard.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
#: Every migration that prices live models, with the head it chains after —
#: the ElevenLabs agents row joined in ADR-300 wave 4.
_MIGRATIONS: dict[str, tuple[str, str]] = {
    "2026_09_19_1500-f1a3c5e7b9d2_live_audio_pricing.py": ("f1a3c5e7b9d2", "d7f2a4c6e8b1"),
    "2026_09_19_2100-b7d1e3f5a9c2_elevenlabs_live_pricing.py": ("b7d1e3f5a9c2", "f1a3c5e7b9d2"),
    # The agents priced under their voice model (review 2026-09-20): the flat row retired.
    "2026_09_20_1200-a4c8e1f7b3d5_elevenlabs_v3_conversational_pricing.py": (
        "a4c8e1f7b3d5",
        "c9e2a4b6d8f1",
    ),
}
_AUDIO_MIGRATION = "2026_09_19_1500-f1a3c5e7b9d2_live_audio_pricing.py"
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"

_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_SEED_AUDIO_BLOCK = re.compile(
    r"UPDATE llm_model_pricing p\s+SET audio_input_unit_price = (?P<input>[0-9.]+),\s+"
    r"audio_output_unit_price = (?P<output>[0-9.]+)\s+FROM llm_models m\s+"
    r"WHERE m\.id = p\.model_id AND p\.is_active AND m\.model_name IN \((?P<names>[^)]*)\);",
    re.S,
)


def _load_migration(file_name: str = _AUDIO_MIGRATION) -> ModuleType:
    path = _API_ROOT / "alembic" / "versions" / file_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrated = pytest.mark.parametrize("file_name", sorted(_MIGRATIONS))


def _seed_tariffs() -> list[re.Match[str]]:
    return list(_SEED_TARIFF.finditer(_SEED.read_text(encoding="utf-8")))


def _later_migrations(file_name: str) -> list[str]:
    return [name for name in sorted(_MIGRATIONS) if name > file_name]


def _retired_by_a_later_migration(file_name: str) -> set[str]:
    """The tariffs a LATER migration of the chain retired (``SUPERSEDED``): no longer active in the seed."""
    return {
        model_name
        for name in _later_migrations(file_name)
        for model_name in getattr(_load_migration(name), "SUPERSEDED", {})
    }


def _deactivated_by_a_later_migration(file_name: str) -> set[str]:
    """The CATALOGUE rows a later migration deactivated (``RETIRED_CATALOGUE``): ``is_active`` false in the seed."""
    return {
        model_name
        for name in _later_migrations(file_name)
        for model_name in getattr(_load_migration(name), "RETIRED_CATALOGUE", ())
    }


def _decimal_or_none(raw: str) -> float | None:
    return None if raw == "NULL" else float(raw)


@migrated
def test_the_migration_chains_after_its_declared_head(file_name: str) -> None:
    module = _load_migration(file_name)
    revision, down_revision = _MIGRATIONS[file_name]
    assert module.revision == revision
    assert module.down_revision == down_revision


@migrated
def test_every_migrated_catalogue_row_equals_the_seed_row(file_name: str) -> None:
    module = _load_migration(file_name)
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    deactivated = _deactivated_by_a_later_migration(file_name)
    for model_name, (provider, _tariff) in module.LIVE_MODELS.items():
        seed_row = seed_rows[model_name]
        assert seed_row["provider"] == provider, model_name
        for column, value in module.CATALOGUE_DEFAULTS.items():
            if column == "is_active" and model_name in deactivated:
                # A later migration took the row out of the catalogue on purpose
                # (the agents platform is no model of ours); the seed says so.
                assert seed_row[column] == "false", model_name
                continue
            expected = "NULL" if value is None else str(value).lower()
            assert seed_row[column] == expected, (model_name, column)


@migrated
def test_every_migrated_tariff_equals_the_seed_bundles_active_row(file_name: str) -> None:
    module = _load_migration(file_name)
    active = {m.group("model"): m for m in _seed_tariffs() if m.group("active") == "true"}
    for model_name, (_provider, tariff) in module.LIVE_MODELS.items():
        if model_name in _retired_by_a_later_migration(file_name):
            continue  # a later migration retired this row on purpose; its own history test holds it
        bundle = active[model_name]
        assert bundle.group("effective") == module.EFFECTIVE_FROM, model_name
        assert bundle.group("unit") == tariff["unit"], model_name
        assert float(bundle.group("input")) == tariff["input"], model_name
        assert _decimal_or_none(bundle.group("cached")) == tariff["cached"], model_name
        assert float(bundle.group("output")) == tariff["output"], model_name


def test_the_seeds_audio_block_names_exactly_the_models_the_migration_pairs() -> None:
    """The bundle's temp table has no audio columns: the pair lives in ONE UPDATE block."""
    module = _load_migration()
    block = _SEED_AUDIO_BLOCK.search(_SEED.read_text(encoding="utf-8"))
    assert block is not None, "the seed carries no audio-rate block"
    named = set(re.findall(r"'([^']+)'", block.group("names")))
    paired = {
        name
        for name, (_provider, tariff) in module.LIVE_MODELS.items()
        if tariff["audio_input"] is not None
    }
    assert named == paired
    for name in paired:
        tariff = module.LIVE_MODELS[name][1]
        assert float(block.group("input")) == tariff["audio_input"], name
        assert float(block.group("output")) == tariff["audio_output"], name


@migrated
def test_a_minute_billed_live_model_declares_no_audio_pair(file_name: str) -> None:
    module = _load_migration(file_name)
    for name, (_provider, tariff) in module.LIVE_MODELS.items():
        if tariff["unit"] != "per_1m_tokens":
            assert tariff["audio_input"] is None and tariff["audio_output"] is None, name
        else:
            assert (tariff["audio_input"] is None) == (tariff["audio_output"] is None), name


@pytest.mark.parametrize(
    "file_name",
    [name for name in sorted(_MIGRATIONS) if hasattr(_load_migration(name), "SUPERSEDED")],
)
def test_the_superseded_row_is_kept_as_history_in_the_seed(file_name: str) -> None:
    """The bundle retires the old tariff (is_active=false) rather than deleting it."""
    module = _load_migration(file_name)
    for model_name, old in module.SUPERSEDED.items():
        history = [
            m
            for m in _seed_tariffs()
            if m.group("model") == model_name and m.group("effective") == old["effective_from"]
        ]
        assert len(history) == 1, model_name
        assert history[0].group("active") == "false"
        assert float(history[0].group("input")) == old["input"]
        assert float(history[0].group("output")) == old["output"]


@pytest.mark.parametrize(
    "file_name",
    [name for name in sorted(_MIGRATIONS) if hasattr(_load_migration(name), "RETIRED_CATALOGUE")],
)
def test_a_retired_catalogue_row_is_kept_inactive_in_the_seed(file_name: str) -> None:
    """The agents platform leaves the catalogue as history (is_active=false), never deleted."""
    module = _load_migration(file_name)
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for model_name in module.RETIRED_CATALOGUE:
        assert seed_rows[model_name]["is_active"] == "false", model_name
        # No active tariff may stand under a row no slot can run.
        active = [
            m
            for m in _seed_tariffs()
            if m.group("model") == model_name and m.group("active") == "true"
        ]
        assert active == [], model_name


def test_the_tariff_insert_never_overrides_an_administered_price() -> None:
    sql = str(_load_migration()._INSERT_TARIFF)
    assert "NOT EXISTS" in sql and "p.is_active" in sql
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in sql
    assert "SET is_active = true" in sql


def test_the_superseded_retirement_matches_the_whole_old_row() -> None:
    """Only OUR old row is retired: an administered price standing at that instant stays."""
    sql = str(_load_migration()._RETIRE_SUPERSEDED)
    for column in (
        "p.effective_from = ",
        "p.input_unit_price = ",
        "p.cached_input_unit_price IS NULL",
        "p.output_unit_price = ",
        "p.audio_input_unit_price IS NULL",
        "p.audio_output_unit_price IS NULL",
    ):
        assert column in sql, column


def test_the_catalogue_insert_never_overrides_an_existing_row() -> None:
    sql = str(_load_migration()._INSERT_MODEL)
    assert "ON CONFLICT (model_name) DO NOTHING" in sql
