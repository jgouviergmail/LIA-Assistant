"""The 2026-09-26 Gemini catalogue alignment, the seed and the vendor table are ONE source.

``70fd39bf9e8d`` carries to upgraded instances what Google's site and API
state: the sixteen models of the pricing page, the shutdown dates of the
deprecations page, and the models the API no longer serves. The seed bundle
carries the same for a fresh install, and ``vendor_announcements`` the same
dates for the catalogue sync. Three copies drift unless something holds them
equal: this guard reads all three.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue.vendor_announcements import VENDOR_SHUTDOWNS
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_09_26_1800-70fd39bf9e8d_align_gemini_catalogue_on_google.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*[0-9.]+,\s*(?:NULL|[0-9.]+),\s*[0-9.]+,\s*'[a-z_0-9]+',"
    r"\s*'[^']+',\s*(?P<active>true|false)\)",
    re.M,
)
_SEED_SHUTDOWN = re.compile(
    r"^\s*\('(?P<model>[^']+)', (?P<day>NULL|'\d{4}-\d{2}-\d{2}')\),?$", re.M
)

#: The models ai.google.dev/gemini-api/docs/pricing lists (read 2026-09-26)
#: whose rows the catalogue holds, speech models included.
_PRICING_PAGE_MODELS: frozenset[str] = frozenset(
    {
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts",
        "gemini-3.1-flash-tts-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-preview-tts",
        "gemini-2.5-pro-preview-tts",
    }
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("align_gemini_catalogue", _MIGRATION)
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


def _seed_text() -> str:
    return _SEED.read_text(encoding="utf-8")


def test_the_migration_chains_after_the_new_gemini_models() -> None:
    module = _load()
    assert module.revision == "70fd39bf9e8d"
    assert module.down_revision == "7b3e9d1f5c2a"


def test_it_covers_exactly_the_models_the_pricing_page_lists() -> None:
    assert set(_load().CATALOGUE) == _PRICING_PAGE_MODELS


def test_every_catalogue_row_equals_its_seed_row_column_for_column() -> None:
    """The migration inserts a missing row whole, so every column must agree."""
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for name in module.CATALOGUE:
        seed_row = seed_rows.get(name)
        assert seed_row is not None, f"{name} is aligned but not seeded"
        params = {**module.CATALOGUE[name], "model_name": name}
        assert set(params) == set(seed_row), name
        mismatches = {
            column: (value, seed_row[column])
            for column, value in params.items()
            if _as_seed_text(column, value) != seed_row[column]
        }
        assert mismatches == {}, f"{name}: {mismatches}"


def test_the_shutdown_dates_are_the_vendor_tables_and_the_seeds() -> None:
    module = _load()
    vendor = {model: day for (provider, model), day in VENDOR_SHUTDOWNS.items()}
    assert {provider for provider, _ in VENDOR_SHUTDOWNS} == {"gemini"}
    assert module.SHUTDOWN_DATES == vendor
    seeded = {
        m.group("model"): (
            None if m.group("day") == "NULL" else date.fromisoformat(m.group("day")[1:-1])
        )
        for m in _SEED_SHUTDOWN.finditer(_seed_text())
    }
    assert seeded == vendor


def test_only_the_announced_shutdowns_of_the_sixteen_are_dated() -> None:
    """Among the pricing page's models, one shutdown is announced."""
    module = _load()
    dated = {
        name: module.SHUTDOWN_DATES[name]
        for name in module.CATALOGUE
        if module.SHUTDOWN_DATES.get(name) is not None
    }
    assert dated == {"gemini-3.1-flash-lite": date(2027, 5, 7)}


def test_a_model_the_api_no_longer_serves_is_inactive_in_the_seed_too() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    active_tariffs = {
        m.group("model") for m in _SEED_TARIFF.finditer(_seed_text()) if m.group("active") == "true"
    }
    for name in module.NOT_SERVED:
        assert name not in module.CATALOGUE, name
        if name in seed_rows:
            assert seed_rows[name]["is_active"] == "false", name
        assert name not in active_tariffs, name


def test_no_default_slot_runs_on_a_model_the_api_no_longer_serves() -> None:
    """The migration spares a model a slot is configured on; a code default is
    the one reference it cannot see."""
    module = _load()
    defaults = {config.model for config in LLM_DEFAULTS.values()}
    assert defaults.isdisjoint(module.NOT_SERVED)


def test_google_embeddings_are_filed_under_gemini() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for name in module.GOOGLE_EMBEDDINGS:
        assert seed_rows[name]["provider"] == "gemini", name


def test_a_human_decision_stands() -> None:
    """A curated row keeps its capabilities; a referenced model stays active."""
    module = _load()
    assert "capability_provenance <>" in str(module.ALIGN_CAPABILITIES)
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    deactivate = str(module.DEACTIVATE_NOT_SERVED)
    assert "NOT EXISTS" in deactivate and "llm_config_overrides" in deactivate
