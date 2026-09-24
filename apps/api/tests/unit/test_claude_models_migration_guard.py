"""The Claude models migration, the reference seed and the Claude surface agree.

Production never replays the seed bundle, so ``c3e7a1f5d9b2`` carries the
Claude models the seed gained (ADR-306) to upgraded instances; two copies of
the same rows drift unless something holds them equal. And a catalogue row
publishes what the admin UI offers — a temperature field the API refuses, or a
ladder the family cannot translate, is the published-vs-enforced gap ADR-184
forbids — so every Claude row is also held against ``core/claude_surface.py``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from src.core.claude_surface import UNDECLARED_CLAUDE, claude_surface
from src.core.config.llm import get_model_context_window
from src.core.reasoning_profiles import resolve_reasoning_profile
from tests.unit.infrastructure.llm.reasoning.test_family_coverage import _catalogue_rows

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = _API_ROOT / "alembic" / "versions" / "2026_09_23_1800-c3e7a1f5d9b2_claude_models.py"
_SEED = _API_ROOT.parents[1] / "infrastructure" / "database" / "seeds" / "llm_pricing_seed.sql"
_SEED_TARIFF = re.compile(
    r"^\s*\('(?P<model>[^']+)',\s*(?P<input>[0-9.]+),\s*(?P<cached>NULL|[0-9.]+),\s*"
    r"(?P<output>[0-9.]+),\s*'(?P<unit>[a-z_0-9]+)',\s*'(?P<effective>[^']+)',\s*(?P<active>true|false)\)",
    re.M,
)

#: Read on platform.claude.com/docs/en/about-claude/pricing (2026-09-23), USD per
#: million tokens: (input, cache hits and refreshes, output).
PUBLISHED_PRICES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 0.25, 50.0),
    "claude-fable-5": (10.0, 1.0, 50.0),
    "claude-opus-5-5": (4.0, 0.2, 20.0),
    "claude-opus-5": (5.0, 0.5, 25.0),
    "claude-opus-4-8": (5.0, 0.5, 25.0),
    "claude-opus-4-7": (5.0, 0.5, 25.0),
    "claude-sonnet-5": (2.0, 0.2, 10.0),
    "claude-sonnet-4-5": (3.0, 0.3, 15.0),
}

#: The Models API's max_input_tokens / max_tokens (2026-09-23), except Sonnet
#: 4.5's window: 200K per the context-windows documentation, where the Models
#: API reports 1M -- the smaller figure is the one no request can overrun.
PUBLISHED_LIMITS: dict[str, tuple[int, int]] = {
    "claude-fable-5-1": (1_000_000, 128_000),
    "claude-fable-5": (1_000_000, 128_000),
    "claude-opus-5-5": (1_000_000, 128_000),
    "claude-opus-5": (1_000_000, 128_000),
    "claude-opus-4-8": (1_000_000, 128_000),
    "claude-opus-4-7": (1_000_000, 128_000),
    "claude-sonnet-5": (1_000_000, 128_000),
    "claude-sonnet-4-5": (200_000, 64_000),
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("claude_models", _MIGRATION)
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


def _seeded_claude_rows() -> dict[str, dict[str, str]]:
    return {row["model_name"]: row for row in _catalogue_rows() if row["provider"] == "anthropic"}


def test_the_migration_chains_after_the_image_migration() -> None:
    module = _load()
    assert module.revision == "c3e7a1f5d9b2"
    assert module.down_revision == "a9d3f1c7e5b2"


def test_the_migration_carries_exactly_the_published_models() -> None:
    module = _load()
    assert {row["model_name"] for row in module.CATALOGUE_ROWS} == set(PUBLISHED_PRICES)
    assert set(module.TARIFFS) == set(PUBLISHED_PRICES)


def test_every_migrated_catalogue_row_equals_its_seed_row() -> None:
    module = _load()
    seed_rows = _seeded_claude_rows()
    for row in module.CATALOGUE_ROWS:
        seed_row = seed_rows.get(row["model_name"])
        assert seed_row is not None, f"{row['model_name']} is migrated but not seeded"
        mismatches = {
            column: (value, seed_row[column])
            for column, value in row.items()
            if _as_seed_text(column, value) != seed_row[column]
        }
        assert mismatches == {}, f"{row['model_name']}: {mismatches}"


def test_every_tariff_is_the_published_price_in_both_sources() -> None:
    module = _load()
    seed = _SEED.read_text(encoding="utf-8")
    active = {
        m.group("model"): m for m in _SEED_TARIFF.finditer(seed) if m.group("active") == "true"
    }
    for name, published in PUBLISHED_PRICES.items():
        assert module.TARIFFS[name] == published, name
        bundle = active.get(name)
        assert bundle is not None, f"{name} has no active tariff in the seed bundle"
        assert bundle.group("effective") == module.EFFECTIVE_FROM, name
        assert bundle.group("unit") == module.PRICING_UNIT, name
        seeded = (
            float(bundle.group("input")),
            float(bundle.group("cached")),
            float(bundle.group("output")),
        )
        assert seeded == published, name


def test_the_limits_are_the_models_apis() -> None:
    module = _load()
    for row in module.CATALOGUE_ROWS:
        expected = PUBLISHED_LIMITS[row["model_name"]]
        assert (row["max_input_tokens"], row["max_output_tokens"]) == expected, row["model_name"]


def test_nothing_an_administrator_set_is_overridden() -> None:
    """A curated catalogue row stands; a price already active stands."""
    module = _load()
    assert "ON CONFLICT (model_name) DO NOTHING" in str(module.INSERT_MODEL)
    tariff = str(module.INSERT_TARIFF)
    assert "NOT EXISTS" in tariff and "p.is_active" in tariff
    assert "ON CONFLICT (model_id, effective_from) DO UPDATE" in tariff


class TestEveryClaudeRowPublishesWhatTheApiAccepts:
    """The admin UI shows a sampling field iff the row says the model takes it."""

    @pytest.mark.parametrize("model", sorted(PUBLISHED_PRICES))
    def test_a_new_model_is_declared_by_the_surface(self, model: str) -> None:
        assert claude_surface(model) is not UNDECLARED_CLAUDE

    def test_the_sampling_flags_match_the_surface(self) -> None:
        for name, row in _seeded_claude_rows().items():
            accepts = claude_surface(name).accepts_sampling
            assert row["supports_temperature"] == str(accepts).lower(), name
            # top_p never reaches a Claude model: the adapter drops it (4.5 on).
            if name in PUBLISHED_PRICES:
                assert row["supports_top_p"] == "false", name

    def test_a_declared_ladder_only_names_depths_the_family_translates(self) -> None:
        for name, row in _seeded_claude_rows().items():
            ladder = row["reasoning_enum_values"]
            if ladder == "NULL":
                continue
            declared = json.loads(ladder.removesuffix("'::jsonb"))
            family = resolve_reasoning_profile("anthropic", name)
            assert set(declared) <= set(family.levels) | {"none"}, (name, declared)
            if not family.can_disable:
                assert "none" not in declared, name


@pytest.mark.parametrize(
    ("model", "window"),
    [
        ("claude-fable-5-1", 1_000_000),
        ("claude-fable-5", 1_000_000),
        ("claude-opus-5-5", 1_000_000),
        ("claude-opus-5", 1_000_000),
        ("claude-sonnet-5", 1_000_000),
        ("claude-opus-4-8", 1_000_000),
        ("claude-opus-4-7", 1_000_000),
        ("claude-opus-4-6", 1_000_000),
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-sonnet-4-5", 200_000),
        ("claude-opus-4-5", 200_000),
        ("claude-haiku-4-5", 200_000),
    ],
)
def test_the_static_window_table_says_what_the_vendor_says(model: str, window: int) -> None:
    """The fallback for a ``declared`` row: ``claude-opus-4`` used to hand 200K
    to Opus 4.7/4.8 by prefix, and the 4.6 pair carried 200K for a 1M window."""
    assert get_model_context_window(model) == window
