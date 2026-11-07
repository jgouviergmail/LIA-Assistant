"""The pricing seeds hold what production holds, and the models added to them are the vendors'.

Applying a seed writes what it says: a row that lags behind production would silently undo what the
operator changed. Production itself never replays the bundle on its own, so nothing else keeps the
two together between extractions. The two models added on 2026-11-06 are held to their vendors'
pages here, and each starts with an older name, while every rule table matches by prefix: neither
may inherit a neighbour's ladder, window or family.

The configuration seed answers to the same bundle: a fresh install runs each slot on what that seed
names, else on the slot's default, and a model with no active tariff costs nothing in every ledger.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

import pytest

from src.core.config.llm import get_model_context_window
from src.core.reasoning_profiles import resolve_reasoning_profile
from src.domains.image_generation.families import OPENAI_GPT_IMAGE, resolve_image_family
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.model_capabilities_cache import is_reasoning_model
from src.infrastructure.llm.providers.openai_payload import supports_cache_breakpoints
from src.infrastructure.llm.providers.responses_adapter import is_responses_api_eligible
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows
from tests.unit.seed_extraction import RETIRED_BY_THE_OPERATOR

pytestmark = pytest.mark.unit

_SEEDS = Path(__file__).resolve().parents[4] / "infrastructure" / "database" / "seeds"
_LLM_SEED = _SEEDS / "llm_pricing_seed.sql"
_IMAGE_SEED = _SEEDS / "image_generation_pricing_seed.sql"
_CONFIG_SEED = _SEEDS / "llm_config_seed.sql"
_CONFIG_ROW = re.compile(
    r"\(gen_random_uuid\(\), '(?P<slot>[a-z_0-9]+)', (?:NULL|'[a-z]+'), (?P<model>NULL|'[^']+'),"
)
_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)
_IMAGE_ROW = re.compile(
    r"'(?P<provider>\w+)'::llm_provider_enum, '(?P<model>[^']+)', '(?P<quality>[^']+)', "
    r"'(?P<size>[0-9x]+)', (?P<price>[0-9.]+), (?P<input>NULL|[0-9.]+), "
    r"'(?P<effective>[^']+)', (?P<active>true|false)"
)

#: developers.openai.com/api/docs/models/gpt-6.1-terra, read 2026-11-06.
_TERRA_LADDER = ("none", "low", "medium", "high", "xhigh", "max")
_TERRA_PRICE = (1.0, 0.05, 5.0)
_TERRA_LIMITS = ("922000", "128000")

#: developers.openai.com/api/docs/guides/image-generation#calculating-costs, read 2026-11-06.
_IMAGE_OUTPUT_PER_MILLION = 30
_FLARE_BASE = {"low": 16, "medium": 24, "high": 48}
_FLARE_FACTOR = {"low": 4.2, "medium": 3.3, "high": 1}


def _tariffs() -> list[re.Match[str]]:
    return list(_TARIFF.finditer(_LLM_SEED.read_text(encoding="utf-8")))


def _images() -> list[re.Match[str]]:
    return list(_IMAGE_ROW.finditer(_IMAGE_SEED.read_text(encoding="utf-8")))


def _config_rows() -> list[re.Match[str]]:
    rows = list(_CONFIG_ROW.finditer(_CONFIG_SEED.read_text(encoding="utf-8")))
    assert rows
    return rows


def _flare_price(quality: str, width: int, height: int) -> float:
    """The vendor's calculator, in Python: its output tokens at the published rate."""
    base = _FLARE_BASE[quality]
    ratio = base / (max(width, height) / min(width, height))
    floor = math.floor(ratio)
    short = floor + floor % 2 if ratio - floor == 0.5 else math.floor(ratio + 0.5)
    patches = (base if width >= height else short) * (short if width >= height else base)
    tokens = math.ceil(patches * (2_000_000 + width * height) / 4_000_000)
    billed = math.floor(tokens * _FLARE_FACTOR[quality] + 0.5)
    return round(billed * _IMAGE_OUTPUT_PER_MILLION / 1_000_000, 6)


def test_no_model_holds_two_active_tariffs() -> None:
    """Applying the bundle would break the partial unique index in the middle of the seed."""
    active = Counter(m["model"] for m in _tariffs() if m["active"] == "true")

    assert [model for model, count in active.items() if count > 1] == []


def test_no_tariff_is_listed_twice() -> None:
    dates = Counter((m["model"], m["effective"]) for m in _tariffs())

    assert [key for key, count in dates.items() if count > 1] == []


def test_every_catalogue_row_has_a_tariff_row_or_none_at_all_on_purpose() -> None:
    """A tariff under a name the catalogue does not know joins nothing, in silence."""
    catalogue = {row["model_name"] for row in _catalogue_rows()}

    assert {m["model"] for m in _tariffs()} - catalogue == set()


def test_a_model_the_operator_retired_is_inactive_with_no_active_tariff() -> None:
    rows = {row["model_name"]: row for row in _catalogue_rows()}
    active = {m["model"] for m in _tariffs() if m["active"] == "true"}

    for name in RETIRED_BY_THE_OPERATOR:
        assert rows[name]["is_active"] == "false", name
        assert name not in active, name


def test_gpt_6_1_terra_is_the_vendors_row() -> None:
    row = next(row for row in _catalogue_rows() if row["model_name"] == "gpt-6.1-terra")

    assert (row["max_input_tokens"], row["max_output_tokens"]) == _TERRA_LIMITS
    assert row["supports_vision"] == "true" and row["is_reasoning_model"] == "true"
    assert row["is_active"] == "true"
    assert get_model_context_window("gpt-6.1-terra") == int(_TERRA_LIMITS[0])
    [tariff] = [m for m in _tariffs() if m["model"] == "gpt-6.1-terra"]
    assert tariff["active"] == "true" and tariff["unit"] == "per_1m_tokens"
    assert (
        float(tariff["input"]),
        float(tariff["cached"]),
        float(tariff["output"]),
    ) == _TERRA_PRICE


def test_gpt_6_1_terra_keeps_its_own_ladder_and_runs_on_the_responses_api() -> None:
    """« Tool calling requires the Responses API », and unlike 6.1 Sol it accepts ``none``."""
    profile = resolve_reasoning_profile("openai", "gpt-6.1-terra")

    assert profile is not None
    assert tuple(profile.levels) == _TERRA_LADDER
    assert profile.can_disable is True
    assert is_reasoning_model("gpt-6.1-terra")
    assert is_responses_api_eligible("gpt-6.1-terra")
    assert supports_cache_breakpoints("gpt-6.1-terra")


def test_gpt_image_2_6_flare_is_a_model_the_family_serves_at_every_row() -> None:
    assert resolve_image_family("openai", "gpt-image-2.6-flare") is OPENAI_GPT_IMAGE
    rows = [m for m in _images() if m["model"] == "gpt-image-2.6-flare"]

    assert len(rows) == 9
    for row in rows:
        assert row["provider"] == "openai" and row["active"] == "true"
        assert (
            OPENAI_GPT_IMAGE.pricing_refusal(row["quality"], row["size"], has_input_price=False)
            is None
        )


def test_gpt_image_2_6_flare_costs_what_the_vendors_calculator_says() -> None:
    for row in (m for m in _images() if m["model"] == "gpt-image-2.6-flare"):
        width, height = (int(side) for side in row["size"].split("x"))

        assert float(row["price"]) == _flare_price(row["quality"], width, height), row.group(0)


def test_no_image_price_is_active_twice() -> None:
    active = Counter(
        (m["model"], m["quality"], m["size"]) for m in _images() if m["active"] == "true"
    )

    assert [key for key, count in active.items() if count > 1] == []


def test_every_slot_of_a_fresh_install_runs_on_a_priced_model() -> None:
    """A model with no active tariff is counted at zero: the euros stop being seen, in silence."""
    priced = {m["model"] for m in (*_tariffs(), *_images()) if m["active"] == "true"}
    fresh = {slot: config.model for slot, config in LLM_DEFAULTS.items()}
    fresh.update({m["slot"]: m["model"].strip("'") for m in _config_rows() if m["model"] != "NULL"})

    assert {slot: model for slot, model in fresh.items() if model not in priced} == {}


def test_the_configuration_seed_names_only_slots_that_exist() -> None:
    """A row for a slot nobody declares is configuration nobody reads, on every fresh install."""
    assert {m["slot"] for m in _config_rows()} - set(LLM_DEFAULTS) == set()
