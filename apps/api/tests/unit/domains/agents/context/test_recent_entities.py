"""Unit tests for recent-entity grounding (2026-07-23).

The response LLM gets no structured data on a turn that produced no registry
updates (``current_turn_registry`` is empty by design, and ``<History>`` drops
ToolMessages), so it could only recall entity values from prose — the
"16h instead of 11h15" class of error. These tests pin:

- the gate, including the REFERENCE exclusion which protects a data-leak
  fail-safe and must never be relaxed;
- selection by **recency** (not by the current query's domains: a follow-up
  routinely references an entity from a domain the query does not name, and
  response-routed turns often carry no domain at all);
- the bounds and the fail-safe behaviour on malformed state.

Thresholds are read from settings, never hardcoded.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.context.recent_entities import (
    build_recent_entities_context,
    should_ground_from_recent_entities,
)

pytestmark = [pytest.mark.unit]


def _item_lines(block: str) -> list[str]:
    """Item lines only.

    Since ADR-167 the block opens with a provenance legend when it carries
    third-party content, and that legend is prose. These assertions are about
    how many ENTITIES were serialised, so they count item lines — the same
    oracle as before, expressed on the right unit.
    """
    return [line for line in block.splitlines() if line.startswith("[")]


LANG = "fr"


def _item(summary: str, start: str = "2026-07-25T11:15:00+02:00") -> dict:
    """A registry item shaped like the ones produced by the calendar tools."""
    return {"type": "EVENT", "payload": {"summary": summary, "start_datetime": start}}


def _results(turn_id: int, item_ids: list[str]) -> dict:
    """agent_results entry for one turn, keyed '{turn}:{agent}'."""
    return {f"{turn_id}:plan_executor": {"registry_updates": dict.fromkeys(item_ids, {})}}


class TestGate:
    """should_ground_from_recent_entities — when grounding is allowed."""

    def test_allowed_when_no_current_turn_data(self):
        assert should_ground_from_recent_entities({}, "action") is True
        assert should_ground_from_recent_entities(None, "action") is True

    def test_refused_when_turn_has_its_own_data(self):
        assert should_ground_from_recent_entities({"event_1": {}}, "action") is False

    @pytest.mark.parametrize(
        "turn_type",
        ["reference", "REFERENCE", "reference_pure", "REFERENCE_PURE", "REFERENCE_ACTION"],
    )
    def test_refused_on_reference_turns_security(self, turn_type: str):
        """An empty registry on a REFERENCE turn is a data-leak fail-safe.

        Re-injecting entities there would defeat the control in
        filter_registry_by_current_turn. This must never be relaxed.
        """
        assert should_ground_from_recent_entities({}, turn_type) is False


class TestBuildContext:
    """build_recent_entities_context — recency-scoped, bounded, fail-safe."""

    def test_disabled_by_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "response_recent_entities_max_turn_age", 0)
        registry = {"event_a": _item("Rdv podologue")}
        assert build_recent_entities_context(registry, _results(4, ["event_a"]), 5, LANG) == ""

    @pytest.mark.parametrize(
        "registry,results,turn",
        [
            ({}, {"4:x": {"registry_updates": {"a": {}}}}, 5),
            ({"a": _item("X")}, {}, 5),
            ({"a": _item("X")}, {"4:x": {"registry_updates": {"a": {}}}}, None),
        ],
    )
    def test_empty_inputs_return_empty(self, registry, results, turn):
        assert build_recent_entities_context(registry, results, turn, LANG) == ""

    def test_recent_entity_is_injected_with_its_value(self):
        registry = {"event_a": _item("Rdv podologue", "2026-07-25T11:15:00+02:00")}
        out = build_recent_entities_context(registry, _results(4, ["event_a"]), 5, LANG)
        assert out
        assert "Rdv podologue" in out
        # The authoritative value must actually reach the prompt.
        assert "11:15" in out

    def test_stale_entity_is_skipped(self):
        max_age = settings.response_recent_entities_max_turn_age
        registry = {"event_a": _item("Vieux rendez-vous")}
        stale_turn = 10 - max_age - 1
        assert (
            build_recent_entities_context(registry, _results(stale_turn, ["event_a"]), 10, LANG)
            == ""
        )

    def test_boundary_age_is_still_injected(self):
        max_age = settings.response_recent_entities_max_turn_age
        registry = {"event_a": _item("Limite")}
        out = build_recent_entities_context(registry, _results(10 - max_age, ["event_a"]), 10, LANG)
        assert "Limite" in out

    def test_domain_of_current_query_is_irrelevant(self):
        """Selection is by recency only.

        The prod failure was a weather-focused follow-up whose answer misquoted
        an *event*: filtering by the query's domain would have surfaced nothing.
        """
        registry = {"event_a": _item("Rdv podologue")}
        out = build_recent_entities_context(registry, _results(4, ["event_a"]), 5, LANG)
        assert "Rdv podologue" in out

    def test_ids_absent_from_registry_are_skipped(self):
        registry = {"event_a": _item("Présent")}
        results = _results(4, ["event_a", "event_ghost"])
        out = build_recent_entities_context(registry, results, 5, LANG)
        assert "Présent" in out
        assert len(_item_lines(out)) == 1

    def test_total_is_capped_by_settings(self):
        cap = settings.tool_context_max_items
        ids = [f"event_{i}" for i in range(cap + 5)]
        registry = {i: _item(f"Evenement {i}") for i in ids}
        out = build_recent_entities_context(registry, _results(4, ids), 5, LANG)
        assert len(_item_lines(out)) == cap

    def test_most_recent_turn_comes_first(self):
        registry = {"old": _item("Ancien"), "new": _item("Recent")}
        results = {**_results(3, ["old"]), **_results(4, ["new"])}
        out = build_recent_entities_context(registry, results, 5, LANG)
        assert out.index("Recent") < out.index("Ancien")

    def test_malformed_keys_do_not_crash(self):
        registry = {"event_a": _item("Bon")}
        results = {
            "not-a-turn:agent": {"registry_updates": {"event_a": {}}},
            "4:plan_executor": {"registry_updates": {"event_a": {}}},
        }
        out = build_recent_entities_context(registry, results, 5, LANG)
        assert "Bon" in out

    def test_results_without_registry_updates_are_ignored(self):
        registry = {"event_a": _item("Bon")}
        results = {"4:agent": {"status": "ok"}, "4:other": {"registry_updates": None}}
        assert build_recent_entities_context(registry, results, 5, LANG) == ""

    def test_object_shaped_agent_result_is_supported(self):
        """agent_results may hold objects, not only dicts (state round-trips)."""

        class _Result:
            registry_updates = {"event_a": {}}

        registry = {"event_a": _item("ObjetOK")}
        out = build_recent_entities_context(registry, {"4:agent": _Result()}, 5, LANG)
        assert "ObjetOK" in out
