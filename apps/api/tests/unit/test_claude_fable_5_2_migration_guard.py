"""The Claude Fable 5.2 migration, the reference seed and Anthropic's pages agree.

Claude Fable 5.2 joined the Claude API on 2026-11-09. Production never replays the
seed bundle, so ``5cccb7a8d77f`` carries the row and its tariff to the instances
that upgrade; two copies of the same rows drift unless something holds them
equal.

Its name starts with Fable 5's, and every rule table of ADR-306 matches by
prefix: its surface, ladder and window are held here against what the vendor
published, so it cannot silently take the rules of ``claude-fable-5`` -- a
forced ``tool_choice`` it refuses with a 400, and a thinking block sent back
with no binding control on a generation whose prefix check applies to every
account.
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
from src.core.constants import (
    PROMPT_CACHE_EXTENDED_WRITE_MULTIPLIER,
    PROMPT_CACHE_WRITE_MULTIPLIER,
)
from src.core.reasoning_profiles import resolve_reasoning_profile
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _API_ROOT / "alembic" / "versions" / "2026_11_11_1700-5cccb7a8d77f_seed_claude_fable_5_2.py"
)
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)

FABLE = "claude-fable-5-2"

#: Read 2026-11-11, USD per million tokens: (input, cache read, output) --
#: platform.claude.com/docs/en/about-claude/pricing, the list price (the page
#: publishes no introductory rate for this model).
PUBLISHED_PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    FABLE: (Decimal("8"), Decimal("0.20"), Decimal("40")),
}

#: The same row of the same page: the 5-minute and the 1-hour cache writes.
FABLE_5_2_CACHE_WRITE_5M = Decimal("10")
FABLE_5_2_CACHE_WRITE_1H = Decimal("16")
#: « Cache reads (hits and refreshes) cost 0.025 times the base input price ».
FABLE_5_2_CACHE_READ_RATIO = Decimal("0.025")

#: (input, output) tokens: the model overview's context window and max output.
PUBLISHED_LIMITS: dict[str, tuple[int, int]] = {FABLE: (1_000_000, 128_000)}

#: « All five effort levels », and no off switch: thinking is always on.
PUBLISHED_LADDER = ("low", "medium", "high", "xhigh", "max")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_claude_fable_5_2", _MIGRATION)
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


def test_the_migration_chains_after_the_workboard_categories_migration() -> None:
    module = _load()
    assert module.revision == "5cccb7a8d77f"
    assert module.down_revision == "92fba8ef5778"


def test_every_migrated_catalogue_row_equals_its_seed_row() -> None:
    module = _load()
    seed_rows = {row["model_name"]: row for row in _catalogue_rows()}
    assert [row["model_name"] for row in module.CATALOGUE_ROWS] == [FABLE]
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


def test_every_tariff_is_the_seed_bundles_only_row_for_its_model() -> None:
    """One row, active, dated like the migration: a fresh install, where the
    migration runs first, and the bundle's upsert land on the same row."""
    module = _load()
    assert set(module.TARIFFS) == {row["model_name"] for row in module.CATALOGUE_ROWS}
    for name, tariff in module.TARIFFS.items():
        [bundle] = [m for m in _bundle_rows() if m.group("model") == name]
        assert bundle.group("active") == "true", name
        assert bundle.group("effective") == module.EFFECTIVE_FROM, name
        assert bundle.group("unit") == module.PRICING_UNIT, name
        assert _tariff(bundle) == _migrated(tariff), name


def test_the_rows_carry_what_the_vendor_published() -> None:
    module = _load()
    assert {name: _migrated(tariff) for name, tariff in module.TARIFFS.items()} == PUBLISHED_PRICES
    rows = {row["model_name"]: row for row in module.CATALOGUE_ROWS}
    assert set(rows) == set(PUBLISHED_LIMITS)
    for name, (max_in, max_out) in PUBLISHED_LIMITS.items():
        assert (rows[name]["max_input_tokens"], rows[name]["max_output_tokens"]) == (
            max_in,
            max_out,
        ), name
        assert tuple(rows[name]["reasoning_enum_values"]) == PUBLISHED_LADDER, name
        assert rows[name]["supports_vision"] is True, name


def test_the_cache_read_is_a_fortieth_of_the_input_price() -> None:
    """Stored as the cached price: 0.025x, where most Claude models pay 0.1x."""
    input_price, cache_read, _output = PUBLISHED_PRICES[FABLE]
    assert cache_read == input_price * FABLE_5_2_CACHE_READ_RATIO


def test_fable_5_2_cache_writes_are_priced_by_the_provider_multipliers() -> None:
    """The 5-minute write is 1.25x the input price and the 1-hour one 2x: the
    multipliers the cost computation applies to every Anthropic tariff -- never
    a stored price."""
    input_price = PUBLISHED_PRICES[FABLE][0]
    assert input_price * Decimal(str(PROMPT_CACHE_WRITE_MULTIPLIER)) == FABLE_5_2_CACHE_WRITE_5M
    assert (
        input_price * Decimal(str(PROMPT_CACHE_EXTENDED_WRITE_MULTIPLIER))
        == FABLE_5_2_CACHE_WRITE_1H
    )


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands, and so does a price already active."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    tariff = str(module.INSERT_TARIFF)
    assert "NOT EXISTS" in tariff and "p.is_active" in tariff


def test_the_bundle_vouches_for_the_row_only_where_it_inserted_it() -> None:
    """Both doors give a row they create the same provenance; a row that stood
    before the bundle ran keeps whatever provenance it had."""
    module = _load()
    block = re.search(
        r"UPDATE llm_models\s+SET capability_provenance = '(?P<provenance>\w+)'\s+"
        rf"WHERE model_name = '{re.escape(FABLE)}'\s+"
        r"AND model_name IN \(SELECT model_name FROM _lia_inserted_models\)\s+"
        r"AND capability_provenance = 'declared';",
        _SEED.read_text(encoding="utf-8"),
    )
    assert block is not None, "the seed no longer vouches for the row it inserts"
    assert block["provenance"] == module.PROVENANCE


class TestFable52HasItsOwnRules:
    """Measured on the Claude API on 2026-11-11: the Models API, then validation requests."""

    def test_its_surface_is_declared_not_inherited_from_fable_5(self) -> None:
        surface = claude_surface(FABLE)
        assert surface.thinking == "always_on"
        assert surface.implicit_effort == "high"
        assert surface.accepts_sampling is False
        assert surface.accepts_forced_tool_choice is False
        assert surface.binds_thinking_to_conversation is True
        assert surface.preserves_prior_turn_thinking is True
        # The neighbour whose name starts its own, and whose rules it must not take.
        older = claude_surface("claude-fable-5")
        assert older.accepts_forced_tool_choice is True
        assert older.binds_thinking_to_conversation is False

    def test_its_sampling_flags_say_what_the_surface_says(self) -> None:
        module = _load()
        for row in module.CATALOGUE_ROWS:
            accepts = claude_surface(row["model_name"]).accepts_sampling
            assert row["supports_temperature"] is accepts, row["model_name"]
            assert row["supports_top_p"] is False, row["model_name"]

    def test_its_ladder_is_the_one_its_family_translates(self) -> None:
        module = _load()
        for row in module.CATALOGUE_ROWS:
            profile = resolve_reasoning_profile(row["provider"], row["model_name"])
            assert tuple(row["reasoning_enum_values"]) == profile.levels, row["model_name"]
            assert profile.can_disable is False
            assert profile.implicit_level == "high"

    @pytest.mark.parametrize(("model", "limits"), sorted(PUBLISHED_LIMITS.items()))
    def test_the_static_window_table_says_what_the_vendor_says(
        self, model: str, limits: tuple[int, int]
    ) -> None:
        """The fallback for a row that stays ``declared``."""
        assert get_model_context_window(model) == limits[0]
