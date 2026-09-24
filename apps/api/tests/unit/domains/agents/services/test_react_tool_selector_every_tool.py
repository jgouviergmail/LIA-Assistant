"""For frequent exchanges, the loop binds EVERY available tool, in one order (ADR-308, ADR-311).

The relevance selection (ADR-293) binds the tools a question needs, so the list
changes from one turn to the next -- and a provider caches a prompt by prefix,
tools first on Anthropic and OpenAI: measured 2026-09-23, a turn read nothing of
the previous turn's cache. Bound whole and in registration order, the tools are
the same bytes on every turn and the previous turn's cache is read (-18 % to
-42 % per turn at production's measured gaps, with the context moved after the
question -- ``react_turn_layout``).

Every tool cannot always be bound: above the operator's cap, or when the schemas
would take more than the allowed share of the slot's context window. Then the
turn keeps the relevance selection -- a known-good turn -- and the fallback is
counted by reason, since a choice that silently does nothing is a choice nobody
can trust.

The selector reads the turn's rhythm as a parameter (``every_tool``), which the
setup node takes from the turn's state; the instance setting only supplies the
default of an account that never chose, upstream (``users.exchange_rhythm``).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.domains.agents.services import react_tool_selector as selector_module
from tests.unit.domains.agents.services.test_react_tool_selector_relevance import (
    _DOOR,
    _INDIVIDUAL,
    _SERVER,
    CATALOGUE,
    RANKING,
    _Harness,
    _Tool,
)

pytestmark = pytest.mark.unit

EVERY_TOOL = [name for name, _agent in CATALOGUE]


def _fallbacks(reason: str) -> float:
    value = REGISTRY.get_sample_value("react_cross_turn_cache_fallback_total", {"reason": reason})
    return value or 0.0


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    monkeypatch.setattr(settings, "react_agent_max_tools", 100)
    monkeypatch.setattr(settings, "react_tool_semantic_top_k", 6)
    monkeypatch.setattr(selector_module, "every_tool_token_budget", lambda: None)
    return _Harness()


class TestEveryTool:
    def test_every_tool_in_registration_order_whatever_the_turn(self, harness: _Harness) -> None:
        about_the_calendar, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=True)
        about_the_mail, _ = harness.select(
            domains=["email"], ranking=list(reversed(RANKING)), every_tool=True
        )
        assert about_the_calendar == EVERY_TOOL
        assert about_the_mail == EVERY_TOOL

    def test_the_approval_map_covers_every_bound_tool(self, harness: _Harness) -> None:
        bound, hitl_map = harness.select(domains=["event"], ranking=RANKING, every_tool=True)
        assert set(hitl_map) == set(bound)

    def test_an_expanded_server_is_bound_whole_with_its_door(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)
        harness.manifests.append(
            SimpleNamespace(
                name=_DOOR, agent="mcp_srv1_agent", permissions=SimpleNamespace(hitl_required=False)
            )
        )
        for name in (_DOOR, *_INDIVIDUAL):
            harness.ctx.tool_instances[name] = _Tool(name=name)
        bound, _ = harness.select(domains=["event"], ranking=[f"{_SERVER}_c"], every_tool=True)
        assert bound == [*EVERY_TOOL, *_INDIVIDUAL, _DOOR]

    def test_occasional_exchanges_keep_the_selection_by_relevance(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The instance default says « frequent »: the turn's own rhythm decides.
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)
        bound, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=False)
        assert bound != EVERY_TOOL
        assert bound[:3] == ["calendar_get", "calendar_search", "calendar_list"]
        assert "calendar_search" in bound and len(bound) < len(EVERY_TOOL)

    def test_the_instance_setting_alone_binds_nothing_more(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)
        bound, _ = harness.select(domains=["event"], ranking=RANKING)
        assert bound != EVERY_TOOL


class TestFallback:
    def _relevance(self, harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        bound, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=False)
        return bound

    def test_above_the_cap_the_turn_keeps_the_relevance_selection(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_agent_max_tools", len(EVERY_TOOL) - 1)
        expected = self._relevance(harness, monkeypatch)
        before = _fallbacks("cap")
        bound, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=True)
        assert bound == expected
        assert _fallbacks("cap") == before + 1

    def test_schemas_too_large_for_the_window_keep_the_relevance_selection(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected = self._relevance(harness, monkeypatch)
        monkeypatch.setattr(selector_module, "every_tool_token_budget", lambda: 1)
        before = _fallbacks("window")
        bound, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=True)
        assert bound == expected
        assert _fallbacks("window") == before + 1

    def test_at_the_cap_every_tool_is_still_bound(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_agent_max_tools", len(EVERY_TOOL))
        bound, _ = harness.select(domains=["event"], ranking=RANKING, every_tool=True)
        assert bound == EVERY_TOOL


class TestTokenBudget:
    @pytest.fixture(autouse=True)
    def _fraction(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        monkeypatch.setattr(settings, "react_cross_turn_cache_max_window_fraction", 0.5)
        yield

    def test_the_budget_is_the_slot_window_times_the_fraction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.core.llm_config_helper.get_effective_context_window_for_slot",
            lambda slot: 128_000 if slot == "react_agent" else 0,
        )
        assert selector_module.every_tool_token_budget() == 64_000

    def test_an_unknown_window_sets_no_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "src.core.llm_config_helper.get_effective_context_window_for_slot", lambda _slot: 0
        )
        assert selector_module.every_tool_token_budget() is None

    def test_an_unreadable_window_sets_no_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_slot: str) -> int:
            raise RuntimeError("catalogue unavailable")

        monkeypatch.setattr(
            "src.core.llm_config_helper.get_effective_context_window_for_slot", boom
        )
        assert selector_module.every_tool_token_budget() is None
