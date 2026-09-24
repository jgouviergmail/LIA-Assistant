"""The ADR-305 migration and the reference seeds are ONE source.

Production never replays the seed bundle, so ``a9d3f1c7e5b2`` carries the Qwen
image models to upgraded instances. Two copies of the same rows drift unless
something holds them equal: this guard reads both — and holds every seeded image
price to its family's own rules, so the bundle can never ship a row the running
code would refuse or mis-bill.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.domains.image_generation.families import resolve_image_family
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_09_23_1600-a9d3f1c7e5b2_multi_provider_image_generation.py"
)
_IMAGE_SEED = (
    _API_ROOT.parents[1]
    / "infrastructure"
    / "database"
    / "seeds"
    / "image_generation_pricing_seed.sql"
)
_SEED_PRICE = re.compile(
    r"^\s*\(gen_random_uuid\(\), '(?P<provider>[a-z]+)'::llm_provider_enum, "
    r"'(?P<model>[^']+)', '(?P<quality>[^']+)', '(?P<size>[^']+)', "
    r"(?P<output>[0-9.]+), (?P<input>NULL|[0-9.]+), '(?P<effective>[^']+)', "
    r"(?P<active>true|false), NOW\(\), NOW\(\)\)",
    re.M,
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("multi_provider_image", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_prices() -> list[re.Match[str]]:
    return list(_SEED_PRICE.finditer(_IMAGE_SEED.read_text(encoding="utf-8")))


def _as_seed_text(value: Any) -> str:
    """How the seed's VALUES tuple spells a migration value."""
    return "NULL" if value is None else str(value).lower()


def test_the_migration_chains_after_the_chat_models_migration() -> None:
    module = _load()
    assert module.revision == "a9d3f1c7e5b2"
    assert module.down_revision == "f6c2a8e4b0d7"


def test_the_seed_parser_reads_every_row() -> None:
    """A parser that matched nothing would make every check below vacuous."""
    rows = _seed_prices()
    assert len(rows) == _IMAGE_SEED.read_text(encoding="utf-8").count("gen_random_uuid()")
    assert {row.group("provider") for row in rows} == {"openai", "qwen"}


def test_every_migrated_catalogue_row_equals_its_seed_row() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for row in module.CATALOGUE_ROWS:
        seed_row = seed_rows.get(row["model_name"])
        assert seed_row is not None, f"{row['model_name']} is migrated but not seeded"
        mismatches = {
            column: (value, seed_row[column])
            for column, value in row.items()
            if _as_seed_text(value) != seed_row[column]
        }
        assert mismatches == {}, f"{row['model_name']}: {mismatches}"


def test_every_migrated_price_equals_its_seed_row() -> None:
    module = _load()
    seeded = {
        (row.group("model"), row.group("quality"), row.group("size")): row
        for row in _seed_prices()
        if row.group("provider") == "qwen"
    }
    migrated = {
        (model, module.QUALITY, size): output
        for model, sizes in module.TARIFFS.items()
        for size, output in sizes
    }
    assert set(migrated) == set(seeded)
    for key, output in migrated.items():
        row = seeded[key]
        assert float(row.group("output")) == output, key
        assert float(row.group("input")) == module.INPUT_IMAGE_PRICE, key
        assert row.group("effective") == module.EFFECTIVE_FROM, key
        assert row.group("active") == "true", key


def test_every_seeded_price_is_one_its_family_accepts() -> None:
    """Quality, size and the reference-image price, row by row, OpenAI included."""
    for row in _seed_prices():
        provider, model = row.group("provider"), row.group("model")
        family = resolve_image_family(provider, model)
        assert family is not None, f"{model} is not servable"
        refusal = family.pricing_refusal(
            row.group("quality"), row.group("size"), has_input_price=row.group("input") != "NULL"
        )
        assert refusal is None, f"{model} {row.group('quality')} {row.group('size')}: {refusal}"


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands; a price already active stands."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    price = str(module.INSERT_PRICE)
    assert "NOT EXISTS" in price and "p.is_active" in price
    assert "ON CONFLICT (model, quality, size, effective_from) DO UPDATE" in price
