"""The 2026-10-08 Claude migration, the reference seed and Anthropic's pages agree.

Claude Haiku 5.5 joined the Claude API on 2026-10-07, and the same day's release
note cut Claude Sonnet 5.5's cache read from 0.20 to 0.10 USD per million tokens
(0.05x the input price instead of 0.1x). Production never replays the seed
bundle, so ``36ecac9a51ea`` carries both; two copies of the same rows drift
unless something holds them equal, and a price correction must touch only the
value LIA itself shipped.

Haiku 5.5's name also sits beside older rules that match by prefix: its
surface, ladder and window are held here against what the vendor published, so
it cannot silently fall to a default (the static window table answered 128K).
"""

from __future__ import annotations

import importlib.util
import json
import re
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.core.claude_surface import claude_surface
from src.core.config.llm import get_model_context_window
from src.core.constants import PROMPT_CACHE_WRITE_MULTIPLIER
from src.core.reasoning_profiles import resolve_reasoning_profile
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT
    / "alembic"
    / "versions"
    / "2026_10_08_1200-36ecac9a51ea_haiku_5_5_and_sonnet_5_5_cache_read.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)

#: Read 2026-10-08, USD per million tokens: (input, cache read, output) --
#: platform.claude.com/docs/en/about-claude/pricing. Haiku 5.5 is priced by
#: prompt length; this is its tier « for prompts up to 100,000 tokens ».
PUBLISHED_PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.01"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("0.10"), Decimal("10")),
}

#: Haiku 5.5's 5-minute cache write, the same page and tier.
HAIKU_5_5_CACHE_WRITE_5M = Decimal("0.125")

#: (input, output) tokens: the model overview's context window and max output.
PUBLISHED_LIMITS: dict[str, tuple[int, int]] = {"claude-haiku-5-5": (1_000_000, 128_000)}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("haiku_5_5_and_sonnet_cache_read", _MIGRATION)
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


def _decimal(text: str | None) -> Decimal | None:
    """A price as a number: ``NULL``/None is the absence of a price, never zero."""
    return None if text in (None, "NULL") else Decimal(text)


def _tariff(match: re.Match[str]) -> tuple[Decimal | None, ...]:
    return tuple(_decimal(match.group(column)) for column in ("input", "cached", "output"))


def _migrated(tariff: Any) -> tuple[Decimal | None, ...]:
    return (_decimal(tariff.input), _decimal(tariff.cached), _decimal(tariff.output))


def _bundle_rows() -> list[re.Match[str]]:
    return list(_SEED_TARIFF.finditer(_SEED.read_text(encoding="utf-8")))


def test_the_migration_chains_after_the_routine_reservation_migration() -> None:
    module = _load()
    assert module.revision == "36ecac9a51ea"
    assert module.down_revision == "e47c0a52d9f1"


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


def test_every_new_tariff_is_the_seed_bundles_active_row() -> None:
    module = _load()
    active = {m.group("model"): m for m in _bundle_rows() if m.group("active") == "true"}
    assert set(module.TARIFFS) == {row["model_name"] for row in module.CATALOGUE_ROWS}
    for name, tariff in module.TARIFFS.items():
        bundle = active.get(name)
        assert bundle is not None, f"{name} has no active tariff in the seed bundle"
        assert bundle.group("effective") == module.EFFECTIVE_FROM, name
        assert bundle.group("unit") == module.PRICING_UNIT, name
        assert _tariff(bundle) == _migrated(tariff), name


def test_each_correction_lands_on_the_bundles_active_row_and_retires_what_it_shipped() -> None:
    """The published price is the bundle's active row, dated like the migration;
    every value the migration may retire is a row the bundle shipped and now
    carries inactive -- so a fresh install and an upgraded one end alike."""
    module = _load()
    rows = _bundle_rows()
    for correction in module.CORRECTIONS:
        mine = [m for m in rows if m.group("model") == correction.model_name]
        active = [m for m in mine if m.group("active") == "true"]
        assert len(active) == 1, correction.model_name
        assert active[0].group("effective") == module.EFFECTIVE_FROM, correction.model_name
        assert _tariff(active[0]) == _migrated(correction.published), correction.model_name
        retired = {_tariff(m) for m in mine if m.group("active") == "false"}
        for shipped in correction.shipped:
            assert _migrated(shipped) in retired, (correction.model_name, shipped)


def test_the_rows_carry_what_the_vendor_published() -> None:
    module = _load()
    published = {name: _migrated(tariff) for name, tariff in module.TARIFFS.items()} | {
        c.model_name: _migrated(c.published) for c in module.CORRECTIONS
    }
    assert published == PUBLISHED_PRICES
    rows = {row["model_name"]: row for row in module.CATALOGUE_ROWS}
    assert set(rows) == set(PUBLISHED_LIMITS)
    for name, (max_in, max_out) in PUBLISHED_LIMITS.items():
        assert (rows[name]["max_input_tokens"], rows[name]["max_output_tokens"]) == (
            max_in,
            max_out,
        ), name


def test_haiku_5_5_cache_writes_are_priced_by_the_provider_multiplier() -> None:
    """The 5-minute write is 1.25x the input price: the multiplier the cost
    computation applies to every Anthropic tariff -- never a stored price."""
    input_price = PUBLISHED_PRICES["claude-haiku-5-5"][0]
    assert input_price * Decimal(str(PROMPT_CACHE_WRITE_MULTIPLIER)) == HAIKU_5_5_CACHE_WRITE_5M


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands; a price already active stands; a
    correction retires only a tariff still holding a value LIA shipped."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    tariff = str(module.INSERT_TARIFF)
    assert "NOT EXISTS" in tariff and "p.is_active" in tariff
    retire = str(module.RETIRE_SHIPPED)
    for column in ("input_unit_price", "cached_input_unit_price", "output_unit_price"):
        assert f"p.{column}" in retire, column


class TestHaiku55HasItsOwnRules:
    """Read on the vendor's pages (2026-10-08), NOT measured: no Anthropic spend."""

    def test_its_surface_is_declared_not_inherited(self) -> None:
        surface = claude_surface("claude-haiku-5-5")
        assert surface.thinking == "default_on"
        assert surface.implicit_effort == "medium"
        assert surface.accepts_sampling is False
        assert surface.accepts_forced_tool_choice is True
        assert surface.binds_thinking_to_conversation is True

    def test_its_ladder_is_the_one_its_family_translates(self) -> None:
        module = _load()
        for row in module.CATALOGUE_ROWS:
            profile = resolve_reasoning_profile(row["provider"], row["model_name"])
            assert tuple(row["reasoning_enum_values"]) == profile.levels, row["model_name"]
            assert profile.can_disable is True

    @pytest.mark.parametrize(("model", "limits"), sorted(PUBLISHED_LIMITS.items()))
    def test_the_static_window_table_says_what_the_vendor_says(
        self, model: str, limits: tuple[int, int]
    ) -> None:
        """The fallback for a row that stays ``declared``: no key matched, so the
        128K default answered for a 1M window."""
        assert get_model_context_window(model) == limits[0]
