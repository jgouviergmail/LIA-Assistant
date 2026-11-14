"""The model the image slot names has a catalogue row, on every instance.

The configuration seed is the production configuration, and its ``image_generation``
slot names ``gpt-image-2.6-flare``: priced, served by its image family, and absent
from ``llm_models`` -- the slot then resolves to the conservative default profile,
the defect ADR-244 closed for ``gpt-image-2`` (``b1c2d3e4f5a6``) and that a newer
image model reopened. Production never replays the seed bundle, so ``45cf916cc02f``
carries the row; two copies of one row drift unless something holds them equal.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.domains.image_generation.families import OPENAI_GPT_IMAGE, resolve_image_family
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_11_11_2000-45cf916cc02f_catalogue_row_for_the_image_slot_model.py"
)
_SEEDS = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds"
_CONFIG_ROW = re.compile(
    r"^\s*\(gen_random_uuid\(\),\s*'(?P<slot>[^']+)',\s*(?:NULL|'[^']*'),\s*(?P<model>NULL|'[^']*'),",
    re.M,
)
_IMAGE_PRICE = re.compile(
    r"'(?P<provider>\w+)'::llm_provider_enum, '(?P<model>[^']+)', '(?P<quality>[^']+)', "
    r"'(?P<size>[0-9x]+)', (?P<price>[0-9.]+), (?P<input>NULL|[0-9.]+), "
    r"'(?P<effective>[^']+)', (?P<active>true|false)"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("catalogue_row_for_the_image_slot", _MIGRATION)
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


def test_the_migration_chains_after_the_catalogue_alignment() -> None:
    module = _load()
    assert module.revision == "45cf916cc02f"
    assert module.down_revision == "43891b5db14c"


def test_the_row_is_the_one_the_configuration_seed_names_for_the_image_slot() -> None:
    """The reason the row exists: a slot of every fresh install points at it."""
    module = _load()
    text = (_SEEDS / "llm_config_seed.sql").read_text(encoding="utf-8")
    named = {m["slot"]: m["model"].strip("'") for m in _CONFIG_ROW.finditer(text)}
    assert named["image_generation"] == module.CATALOGUE_ROW["model_name"]


def test_the_migrated_row_equals_its_seed_row() -> None:
    module = _load()
    row = module.CATALOGUE_ROW
    seed_row = next(r for r in _catalogue_rows() if r["model_name"] == row["model_name"])
    assert set(row) == set(seed_row)
    mismatches = {
        column: (value, seed_row[column])
        for column, value in row.items()
        if _as_seed_text(column, value) != seed_row[column]
    }
    assert mismatches == {}


def test_the_row_is_an_image_model_its_family_serves_and_the_bundle_prices() -> None:
    module = _load()
    row = module.CATALOGUE_ROW
    assert row["kind"] == "image" and row["is_active"] is True
    assert resolve_image_family(row["provider"], row["model_name"]) is OPENAI_GPT_IMAGE
    text = (_SEEDS / "image_generation_pricing_seed.sql").read_text(encoding="utf-8")
    active = [
        m
        for m in _IMAGE_PRICE.finditer(text)
        if m["model"] == row["model_name"] and m["active"] == "true"
    ]
    assert active, "the image slot would name a model no active price covers"


def test_the_placeholders_claim_no_capability_anyone_read() -> None:
    """An image model's window and sampling columns are consulted by no reader:
    the row keeps the provenance of a declaration nobody curated."""
    module = _load()
    assert module.PROVENANCE == "declared"


def test_a_row_an_administrator_holds_stands() -> None:
    statement = " ".join(str(_load().INSERT_MODEL).split())
    assert statement.endswith("ON CONFLICT (model_name) DO NOTHING")
