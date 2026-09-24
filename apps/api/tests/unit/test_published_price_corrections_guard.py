"""Every tariff the 2026-09-23 price audit found wrong is the published one, twice.

The audit read each vendor's pricing page against the tariffs LIA ships and found
eleven token tariffs wrong: a flagship at its predecessor's price, a retired alias
billed above the model that serves it, two Flash models at their Batch and 2027
prices, two speech models at a text model's price, and five cache rates far from
the vendor's rule — 20 % of the input price where the model has an implicit cache,
10 % (the explicit hit) where its only cache is explicit. Production never replays the seed
bundle, so migration ``d5f8b2a6c9e3`` corrects the rows an instance still holds at
a value WE shipped; this guard holds the bundle, the migration's target and the
values it replaces together.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from tests.unit.test_claude_models_migration_guard import _SEED, _SEED_TARIFF

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_09_23_2000-d5f8b2a6c9e3_published_price_corrections.py"
)
_SEED_WINDOWED = re.compile(
    r"SET input_unit_price = (?P<input>[0-9.]+),\s*"
    r"cached_input_unit_price = (?P<cached>[0-9.]+),\s*"
    r"output_unit_price = (?P<output>[0-9.]+),\s*"
    r"time_slots = '(?P<slots>\[.*?\])'::jsonb\s*"
    r"FROM llm_models m\s*"
    r"WHERE m\.id = p\.model_id AND m\.model_name = '(?P<model>[^']+)'",
    re.DOTALL,
)

Price = tuple[float, float | None, float]

#: USD per million tokens, (input, cached input, output), read 2026-09-23 on:
#: developers.openai.com/api/docs/pricing (Standard, short context);
#: api-docs.deepseek.com/quick_start/pricing (off-peak; a legacy name « billed at
#: the Flash price »); ai.google.dev/gemini-api/docs/pricing (Standard, paid tier,
#: prices valid through 2026-12-31; the speech models bill text in, audio out);
#: alibabacloud.com/help/en/model-studio/model-pricing (Germany (Frankfurt),
#: Global scope, first tier). The cache read follows the model's cache mode on that
#: scope (alibabacloud.com/help/en/model-studio/context-cache): 20 % of the input
#: price for an implicit hit (qwen3.7-plus, qwen3-max); 10 % for an explicit hit on
#: the models the implicit cache does not cover there (qwen3.5-flash, qwen3.5-plus,
#: qwen3.6-plus — measured: no cached token on two identical requests).
PUBLISHED: dict[str, Price] = {
    "gpt-5.6-sol": (4.0, 0.4, 20.0),
    "deepseek-v4-flash": (0.15, 0.003, 0.6),
    "gemini-3.7-flash": (0.75, 0.075, 3.75),
    "gemini-3.6-flash": (0.75, 0.075, 3.75),
    "gemini-2.5-flash-preview-tts": (0.5, None, 10.0),
    "gemini-2.5-pro-preview-tts": (1.0, None, 20.0),
    "qwen3.5-flash": (0.029, 0.0029, 0.287),
    "qwen3.5-plus": (0.115, 0.0115, 0.688),
    "qwen3.6-plus": (0.276, 0.0276, 1.651),
    "qwen3.7-plus": (0.276, 0.0552, 1.101),
    "qwen3-max": (0.359, 0.0718, 1.434),
}


#: USD per generated image, (quality, size) -> price: the output cost table of
#: developers.openai.com/api/docs/guides/image-generation, read 2026-09-23.
PUBLISHED_IMAGES: dict[tuple[str, str], float] = {
    ("low", "1024x1024"): 0.006,
    ("low", "1024x1536"): 0.005,
    ("low", "1536x1024"): 0.005,
    ("medium", "1024x1024"): 0.053,
    ("medium", "1024x1536"): 0.041,
    ("medium", "1536x1024"): 0.041,
    ("high", "1024x1024"): 0.211,
    ("high", "1024x1536"): 0.165,
    ("high", "1536x1024"): 0.165,
}
_IMAGE_SEED = _SEED.parent / "image_generation_pricing_seed.sql"
_IMAGE_ROW = re.compile(
    r"'(?P<provider>[a-z]+)'::llm_provider_enum, '(?P<model>[^']+)', '(?P<quality>[a-z]+)', "
    r"'(?P<size>[0-9x]+)', (?P<price>[0-9.]+), (?P<input>NULL|[0-9.]+), '(?P<effective>[^']+)'"
)


def _image_seed(model: str) -> dict[tuple[str, str], re.Match[str]]:
    rows = _IMAGE_ROW.finditer(_IMAGE_SEED.read_text(encoding="utf-8"))
    return {(m["quality"], m["size"]): m for m in rows if m["model"] == model}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("price_corrections", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _price(input_price: Any, cached: Any, output: Any) -> Price:
    return (
        float(input_price),
        None if cached in (None, "NULL") else float(cached),
        float(output),
    )


def _bundle_rows(model: str) -> list[re.Match[str]]:
    """The bundle's tariff rows of one model, in file order."""
    return [
        m for m in _SEED_TARIFF.finditer(_SEED.read_text(encoding="utf-8")) if m["model"] == model
    ]


def _windowed() -> dict[str, re.Match[str]]:
    """The bundle's UPDATE blocks that set a model's windowed tariff."""
    return {m["model"]: m for m in _SEED_WINDOWED.finditer(_SEED.read_text(encoding="utf-8"))}


def _seed_active_price(model: str) -> Price:
    """What a fresh install bills: the windowed block when there is one, else the active row."""
    windowed = _windowed().get(model)
    if windowed is not None:
        return _price(windowed["input"], windowed["cached"], windowed["output"])
    [active] = [m for m in _bundle_rows(model) if m["active"] == "true"]
    return _price(active["input"], active["cached"], active["output"])


def test_the_migration_chains_after_the_claude_models_head() -> None:
    module = _load()
    assert module.revision == "d5f8b2a6c9e3"
    assert module.down_revision == "c3e7a1f5d9b2"


def test_every_corrected_tariff_is_the_published_price_in_both_sources() -> None:
    corrections = {c.model_name: c for c in _load().CORRECTIONS}

    assert set(corrections) == set(PUBLISHED)
    for name, published in PUBLISHED.items():
        assert _price(*corrections[name].published) == published, name
        assert _seed_active_price(name) == published, name


def test_the_migration_replaces_the_value_the_bundle_used_to_ship() -> None:
    """The row a correction retires is one LIA shipped -- never an administrator's.

    The bundle keeps what it superseded as an inactive row: the most recent of
    them is the value an upgraded instance still holds.
    """
    for correction in _load().CORRECTIONS:
        superseded = [m for m in _bundle_rows(correction.model_name) if m["active"] == "false"]
        assert superseded, correction.model_name
        last = superseded[-1]
        shipped = {_price(*value) for value in correction.shipped}
        assert (
            _price(last["input"], last["cached"], last["output"]) in shipped
        ), correction.model_name


def test_the_legacy_deepseek_name_is_billed_like_the_model_that_serves_it() -> None:
    """« deepseek-v4-flash » is served by DeepSeek-V4.1-Flash « and billed at the Flash price »."""
    windowed = _windowed()
    legacy, current = windowed["deepseek-v4-flash"], windowed["deepseek-flash"]
    [correction] = [c for c in _load().CORRECTIONS if c.model_name == "deepseek-v4-flash"]

    assert _seed_active_price("deepseek-v4-flash") == _seed_active_price("deepseek-flash")
    assert json.loads(legacy["slots"]) == json.loads(current["slots"])
    assert correction.time_slots == json.loads(current["slots"])


def test_gpt_image_2_costs_its_own_published_price_per_image_in_both_sources() -> None:
    """It carried gpt-image-1's nine prices: a copy, not a reading."""
    corrections = {(c.quality, c.size): c for c in _load().IMAGE_CORRECTIONS}
    seeded = _image_seed("gpt-image-2")

    assert set(corrections) == set(PUBLISHED_IMAGES) == set(seeded)
    for key, published in PUBLISHED_IMAGES.items():
        assert float(corrections[key].published) == published, key
        assert float(seeded[key]["price"]) == published, key
        assert seeded[key]["effective"] == _load().EFFECTIVE_FROM, key


def test_the_image_correction_replaces_the_price_copied_from_gpt_image_1() -> None:
    """What an instance still holds is gpt-image-1's row: the migration retires that value only."""
    gpt_image_1 = _image_seed("gpt-image-1")
    for correction in _load().IMAGE_CORRECTIONS:
        key = (correction.quality, correction.size)
        assert float(correction.shipped) == float(gpt_image_1[key]["price"]), key


def test_every_google_price_the_migration_writes_is_the_seed_row() -> None:
    """Street View's correction and the Routes tiers travel to upgraded instances."""
    from tests.unit.test_google_api_pricing_seed_guard import _load_seed_rows

    seed = _load_seed_rows()
    for row in _load().GOOGLE_PRICES:
        assert seed[(row.api_name, row.endpoint)] == (row.sku_name, float(row.price)), row
