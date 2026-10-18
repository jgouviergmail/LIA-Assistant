"""The 2026-09-26 Gemini catalogue alignment, the seed and the vendor table are ONE source.

``70fd39bf9e8d`` carries to upgraded instances what Google's site and API
state: the sixteen models of the pricing page, the shutdown dates of the
deprecations page, and the models the API no longer serves; ``754351d42c74``
the six dates the page changed by 2026-10-17. The seed bundle carries the same
for a fresh install, and ``vendor_announcements`` the same dates for the
catalogue sync. The copies drift unless something holds them equal: this guard
reads them all.
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
#: The shutdown dates Google changed after the alignment (page read 2026-10-17).
_SHUTDOWN_UPDATE = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_10_17_2000-754351d42c74_gemini_shutdowns_2026_10_17.py"
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


def _load(path: Path = _MIGRATION) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
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
    google = {
        model: day for (provider, model), day in VENDOR_SHUTDOWNS.items() if provider == "gemini"
    }
    # An upgraded instance runs both migrations, the later one last.
    assert {**module.SHUTDOWN_DATES, **_load(_SHUTDOWN_UPDATE).SHUTDOWN_DATES} == google
    seeded = {
        m.group("model"): (
            None if m.group("day") == "NULL" else date.fromisoformat(m.group("day")[1:-1])
        )
        for m in _SEED_SHUTDOWN.finditer(_seed_text())
    }
    # Every date the seed states is a vendor's announcement, whichever the vendor
    # (Fish Audio joined in ADR-345; its migration is held to its entries apart).
    assert seeded == {model: day for (_, model), day in VENDOR_SHUTDOWNS.items()}


def test_only_the_announced_shutdowns_of_the_sixteen_are_dated() -> None:
    """Among the pricing page's models, one shutdown was announced on 2026-09-26 —
    and the three speech previews joined it by 2026-10-17."""
    module = _load()
    dated = {
        name: module.SHUTDOWN_DATES[name]
        for name in module.CATALOGUE
        if module.SHUTDOWN_DATES.get(name) is not None
    }
    assert dated == {"gemini-3.1-flash-lite": date(2027, 5, 7)}
    now = {**module.SHUTDOWN_DATES, **_load(_SHUTDOWN_UPDATE).SHUTDOWN_DATES}
    assert {name: now[name] for name in module.CATALOGUE if now.get(name) is not None} == {
        "gemini-3.1-flash-lite": date(2027, 5, 7),
        "gemini-3.1-flash-tts-preview": date(2026, 11, 17),
        "gemini-2.5-flash-preview-tts": date(2026, 11, 17),
        "gemini-2.5-pro-preview-tts": date(2026, 11, 17),
    }


def test_the_update_chains_on_its_head_and_re_dates_only_rows_the_alignment_knew() -> None:
    later = _load(_SHUTDOWN_UPDATE)
    aligned = _load().SHUTDOWN_DATES

    assert (later.revision, later.down_revision) == ("754351d42c74", "1ed6c591761a")
    assert set(later.SHUTDOWN_DATES) <= set(aligned)
    # Each entry is a change the page made, never a restatement.
    assert all(aligned[name] != day for name, day in later.SHUTDOWN_DATES.items())


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
