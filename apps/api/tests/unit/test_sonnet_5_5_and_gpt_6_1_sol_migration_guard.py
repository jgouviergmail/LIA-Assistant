"""The 2026-09-30 models migration, the reference seed and the vendors agree.

Production never replays the seed bundle, so ``fc0147eeb095`` carries Claude
Sonnet 5.5 and GPT-6.1 Sol to upgraded instances; two copies of the same rows
drift unless something holds them equal. Both names also START with an older
model's name (``claude-sonnet-5``, ``gpt-6``), and every rule table matches by
prefix: each is held here against the surface, ladder, cache family and window
its own vendor published, so neither can silently inherit its predecessor's.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.core.claude_surface import claude_surface
from src.core.config.llm import get_model_context_window
from src.core.reasoning_profiles import resolve_reasoning_profile
from src.infrastructure.llm.providers.openai_payload import supports_cache_breakpoints
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_09_30_1800-fc0147eeb095_seed_sonnet_5_5_and_gpt_6_1_sol.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)

#: Read 2026-09-30, USD per million tokens: (input, cached input, output) --
#: platform.claude.com/docs/en/about-claude/pricing (« cache hits and
#: refreshes ») and developers.openai.com/api/docs/pricing (Standard, short
#: context).
PUBLISHED_PRICES: dict[str, tuple[float, float, float]] = {
    "claude-sonnet-5-5": (2.0, 0.2, 10.0),
    "gpt-6.1-sol": (2.0, 0.1, 10.0),
}

#: (input, output) tokens: the Claude Models API's max_input_tokens / max_tokens,
#: and OpenAI's 1 050 000-token window minus the 128 000 output it reserves.
PUBLISHED_LIMITS: dict[str, tuple[int, int]] = {
    "claude-sonnet-5-5": (1_000_000, 128_000),
    "gpt-6.1-sol": (922_000, 128_000),
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_sonnet_5_5_and_gpt_6_1_sol", _MIGRATION)
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


def _price(text: str) -> float | None:
    """A seed price cell: ``NULL`` is the absence of a price, never zero."""
    return None if text == "NULL" else float(text)


def test_the_migration_chains_after_the_skill_provenance_migration() -> None:
    module = _load()
    assert module.revision == "fc0147eeb095"
    assert module.down_revision == "00c0324db6ae"


def test_every_migrated_catalogue_row_equals_its_seed_row() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    for row in module.CATALOGUE_ROWS:
        seed_row = seed_rows.get(row["model_name"])
        assert seed_row is not None, f"{row['model_name']} is migrated but not seeded"
        assert set(row) == set(seed_row), row["model_name"]
        mismatches = {
            column: (value, seed_row[column])
            for column, value in row.items()
            if _as_seed_text(column, value) != seed_row[column]
        }
        assert mismatches == {}, f"{row['model_name']}: {mismatches}"


def test_every_migrated_tariff_equals_the_seed_bundles_active_row() -> None:
    module = _load()
    seed = _SEED.read_text(encoding="utf-8")
    active = {
        m.group("model"): m for m in _SEED_TARIFF.finditer(seed) if m.group("active") == "true"
    }
    assert set(module.TARIFFS) == {row["model_name"] for row in module.CATALOGUE_ROWS}
    for name, (input_price, cached_price, output_price) in module.TARIFFS.items():
        bundle = active.get(name)
        assert bundle is not None, f"{name} has no active tariff in the seed bundle"
        assert bundle.group("effective") == module.EFFECTIVE_FROM, name
        assert bundle.group("unit") == module.PRICING_UNIT, name
        assert (
            _price(bundle.group("input")),
            _price(bundle.group("cached")),
            _price(bundle.group("output")),
        ) == (input_price, cached_price, output_price), name


def test_the_rows_carry_what_the_vendors_published() -> None:
    module = _load()
    rows = {row["model_name"]: row for row in module.CATALOGUE_ROWS}
    assert set(rows) == set(PUBLISHED_PRICES) == set(PUBLISHED_LIMITS)
    assert module.TARIFFS == PUBLISHED_PRICES
    for name, (max_in, max_out) in PUBLISHED_LIMITS.items():
        assert (rows[name]["max_input_tokens"], rows[name]["max_output_tokens"]) == (
            max_in,
            max_out,
        ), name


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands; a price already active stands."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    tariff = str(module.INSERT_TARIFF)
    assert "NOT EXISTS" in tariff and "p.is_active" in tariff
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in tariff


class TestNeitherModelInheritsItsPredecessorsRules:
    """Every rule table matches by prefix, and each new name starts an older one."""

    def test_sonnet_5_5_has_its_own_surface_and_off_switch(self) -> None:
        surface = claude_surface("claude-sonnet-5-5")
        assert surface.thinking == "between_tools"
        assert surface.accepts_forced_tool_choice is False
        assert surface.binds_thinking_to_conversation is True
        profile = resolve_reasoning_profile("anthropic", "claude-sonnet-5-5")
        assert profile.family == "anthropic_between_tools"
        assert profile.can_disable is True

    def test_gpt_6_1_sol_has_no_off_switch_and_its_own_cache_family(self) -> None:
        profile = resolve_reasoning_profile("openai", "gpt-6.1-sol")
        assert profile.can_disable is False
        assert "none" not in profile.levels
        assert supports_cache_breakpoints("gpt-6.1-sol")

    def test_each_ladder_is_the_one_its_family_translates(self) -> None:
        module = _load()
        for row in module.CATALOGUE_ROWS:
            profile = resolve_reasoning_profile(row["provider"], row["model_name"])
            assert tuple(row["reasoning_enum_values"]) == profile.levels, row["model_name"]

    @pytest.mark.parametrize(("model", "limits"), sorted(PUBLISHED_LIMITS.items()))
    def test_the_static_window_table_says_what_the_vendor_says(
        self, model: str, limits: tuple[int, int]
    ) -> None:
        """The fallback for a row that stays ``declared``: GPT-6.1 Sol used to fall
        to the 128K default, matching no key."""
        assert get_model_context_window(model) == limits[0]
