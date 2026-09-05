"""Every incident the platform can open has a declared evidence recipe.

Four diagnoses out of four said "insufficient evidence" between 2026-09-02 and
2026-09-05 while Loki and Prometheus held the answer (a quota, then a
deterministic `500 INTERNAL` on one embedding path). The recipe is the
declaration of WHAT to fetch for WHICH incident; the boot assert refuses a
registry that leaves an incident without one, or names a query or an event
that does not exist — a recipe pointing at nothing is the silent failure this
module exists to remove (ADR-085 doctrine).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.domains.diagnostics import evidence_recipes as recipes_module
from src.domains.diagnostics.checks import IN_PROCESS_CHECKS, PROM_CHECKS
from src.domains.diagnostics.evidence_recipes import (
    EVIDENCE_RECIPES,
    EvidenceRecipe,
    LogRecipe,
    assert_evidence_recipes_completeness,
    recipe_for,
)
from src.domains.diagnostics.logql import DiagService
from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

#: An event is EMITTED when it is the first argument of a structlog call or the
#: `log_event` of an exception class. A bare literal is not enough: `stream_error`
#: existed as an `error_type` metadata value and matched nothing in Loki.
_EVENT_LITERAL = re.compile(
    r'(?:logger\.(?:debug|info|warning|error|exception|critical)\(\s*|log_event=)"([a-z0-9_.]{1,64})"'
)


def _core_alertnames() -> set[str]:
    """The alertnames Prometheus actually loads: `prometheus.yml` lists only
    `alerts-core.yml` — the legacy files are disabled (ADR-119)."""
    root = repo_root_or_skip()
    rendered = yaml.safe_load(
        (root / "infrastructure" / "observability" / "prometheus" / "alerts-core.yml").read_text(
            encoding="utf-8"
        )
    )
    return {
        rule["alert"] for group in rendered["groups"] for rule in group["rules"] if "alert" in rule
    }


def _event_literals_in_source() -> set[str]:
    """Every event name `src/` actually emits (structlog first argument or an
    exception class's `log_event`) — a metadata value is not an event."""
    src = Path(recipes_module.__file__).resolve().parents[2]
    assert src.name == "src", "scan the application source only — never the venv or the tests"
    found: set[str] = set()
    for path in src.rglob("*.py"):
        found.update(_EVENT_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


class TestTheRegistryPassesItsOwnBootAssert:
    def test_real_registry_passes(self) -> None:
        assert_evidence_recipes_completeness()

    def test_keys_match_their_recipe(self) -> None:
        for key, recipe in EVIDENCE_RECIPES.items():
            assert key == recipe.correlation_key


class TestEveryIncidentHasARecipe:
    def test_every_check_correlation_key_has_one(self) -> None:
        for check in (*PROM_CHECKS, *IN_PROCESS_CHECKS):
            key = check.alertname or check.check_id
            assert key in EVIDENCE_RECIPES, f"check {check.check_id} opens incidents under {key!r}"

    def test_every_loaded_core_alert_has_one(self) -> None:
        """The webhook route sends EVERY critical/warning alert to the API."""
        missing = _core_alertnames() - set(EVIDENCE_RECIPES)
        assert not missing, f"core alerts with no evidence recipe: {sorted(missing)}"


class TestARecipeNamesOnlyThingsThatExist:
    def test_every_prom_query_is_in_the_catalogue(self) -> None:
        for recipe in EVIDENCE_RECIPES.values():
            for query_id in recipe.prom_queries:
                assert query_id in QUERY_CATALOGUE, f"{recipe.correlation_key}: {query_id}"

    def test_every_log_event_is_a_literal_in_source(self) -> None:
        """A recipe naming an event nobody emits fetches nothing, forever."""
        literals = _event_literals_in_source()
        for recipe in EVIDENCE_RECIPES.values():
            if recipe.logs is None:
                continue
            for event in recipe.logs.events:
                assert event in literals, f"{recipe.correlation_key}: no code emits {event!r}"

    def test_every_windowed_query_accepts_the_recipe_window(self) -> None:
        for recipe in EVIDENCE_RECIPES.values():
            for query_id in recipe.prom_queries:
                for param in QUERY_CATALOGUE[query_id].params:
                    assert param.min_value <= recipe.window_minutes <= param.max_value


class TestAnEmptyRecipeMustSayWhy:
    def test_the_real_registry_has_no_silent_empty_recipe(self) -> None:
        for recipe in EVIDENCE_RECIPES.values():
            if not recipe.prom_queries and recipe.logs is None:
                assert (
                    recipe.reason_for_none
                ), f"{recipe.correlation_key} fetches nothing and says why not"

    def test_a_silent_empty_recipe_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="fetches nothing"):
            assert_evidence_recipes_completeness(
                {"X": EvidenceRecipe(correlation_key="X")}, required_keys=frozenset({"X"})
            )

    def test_an_unknown_query_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="unknown catalogue"):
            assert_evidence_recipes_completeness(
                {"X": EvidenceRecipe(correlation_key="X", prom_queries=("no_such_query",))},
                required_keys=frozenset({"X"}),
            )

    def test_a_missing_required_key_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="no evidence recipe"):
            assert_evidence_recipes_completeness({}, required_keys=frozenset({"RedisDown"}))

    def test_a_key_mismatch_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="key"):
            assert_evidence_recipes_completeness(
                {"A": EvidenceRecipe(correlation_key="B", reason_for_none="test")},
                required_keys=frozenset(),
            )


class TestLookup:
    def test_recipe_for_returns_the_declared_recipe(self) -> None:
        recipe = recipe_for("EmbeddingOperationsFailing")
        assert recipe is not None
        assert "embedding_errors_by_reason" in recipe.prom_queries
        assert recipe.logs is not None
        assert recipe.logs.service is DiagService.API
        assert "gemini_embedding_failed" in recipe.logs.events

    def test_recipe_for_an_unknown_key_is_none_not_an_error(self) -> None:
        """An incident opened under a key added by a newer alert file than this
        build must still be diagnosed — with the runtime block alone."""
        assert recipe_for("SomethingNobodyDeclared") is None

    def test_a_log_recipe_without_events_means_every_line_of_the_service(self) -> None:
        assert LogRecipe(service=DiagService.POSTGRES_BACKUP).events == ()


class TestBootWiring:
    def test_failfast_validations_wire_the_recipes_assert(self) -> None:
        import inspect

        from src.infrastructure.startup import registries

        assert "assert_evidence_recipes_completeness" in inspect.getsource(
            registries._validate_diagnostics_registries
        )
