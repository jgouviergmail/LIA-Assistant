"""The 2026-11-06 extraction reaches an upgraded instance, and its rows are the seeds' rows.

Production never replays the seed bundle, so ``d2f6b8c4e1a7`` carries what the seeds gained to the
instances that upgrade. Two copies of the same rows drift unless something holds them equal.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_11_07_0100-d2f6b8c4e1a7_carry_extracted_models.py"
)
_SEEDS = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds"
_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_IMAGE = re.compile(
    r"'openai'::llm_provider_enum, '(?P<model>gpt-image-2\.[56]-flare)', '(?P<quality>\w+)', "
    r"'(?P<size>[0-9x]+)', (?P<price>[0-9.]+), NULL, '(?P<effective>[^']+)', (?P<active>true|false)"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("carry_extracted_models", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


def _active_tariff(model: str) -> re.Match[str]:
    text = (_SEEDS / "llm_pricing_seed.sql").read_text(encoding="utf-8")
    rows = [
        row for row in _TARIFF.finditer(text) if row["model"] == model and row["active"] == "true"
    ]
    assert len(rows) == 1, model
    return rows[0]


def test_it_follows_the_last_head() -> None:
    assert MIGRATION.down_revision == "c8e4a1f27b53"


def test_terra_is_the_seed_s_row() -> None:
    text = (_SEEDS / "llm_pricing_seed.sql").read_text(encoding="utf-8")
    ladder = json.dumps(MIGRATION.TERRA["reasoning_enum_values"])
    assert (
        f"('openai', 'gpt-6.1-terra', 922000, 128000, true, true, true, true, true, true, "
        f"false, false, false, false, 'chat', '{ladder}'::jsonb, NULL, true)"
    ) in text
    row = _active_tariff("gpt-6.1-terra")
    assert (
        float(row["input"]),
        float(row["cached"]),
        float(row["output"]),
    ) == MIGRATION.TERRA_TARIFF
    assert row["effective"] == MIGRATION.TERRA_EFFECTIVE_FROM.isoformat()


def test_drama_moves_to_the_seed_s_price_from_the_one_lia_shipped() -> None:
    row = _active_tariff("drama-3")
    assert float(row["input"]) == MIGRATION.DRAMA_INPUT
    assert row["effective"] == MIGRATION.DRAMA_EFFECTIVE_FROM.isoformat()
    shipped = (_API_ROOT / "alembic" / "versions").glob("*a9326a120b55*.py")
    source = next(shipped).read_text(encoding="utf-8")
    assert '"drama-3"' in source
    assert MIGRATION.DRAMA_SHIPPED_INPUT != MIGRATION.DRAMA_INPUT


def test_every_active_flare_price_of_the_seed_travels() -> None:
    text = (_SEEDS / "image_generation_pricing_seed.sql").read_text(encoding="utf-8")
    seeded = {
        (row["model"], row["quality"], row["size"], float(row["price"]), row["effective"])
        for row in _IMAGE.finditer(text)
        if row["active"] == "true"
    }
    assert set(MIGRATION.IMAGE_PRICES) == seeded
    assert len(MIGRATION.IMAGE_PRICES) == len(seeded)
