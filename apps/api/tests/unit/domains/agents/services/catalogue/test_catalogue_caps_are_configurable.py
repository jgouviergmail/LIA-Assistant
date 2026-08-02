"""The planner catalogue size is a deployment knob, not a literal.

Both caps used to be hard-coded — 10 in ``ToolFilter.from_intelligence``, 15 in
``PanicFilteringStrategy`` — so the only way to widen the catalogue as the
product grows was to edit code. They are now settings, with ONE invariant the
literals could never express:

    the panic cap is never SMALLER than the normal one.

Panic mode is the fallback for "the filtered catalogue left no runnable plan".
A panic cap below the normal cap would make the safety net narrower than what
already failed — the guard would be the restriction. Configuration cannot be
allowed to express that, so it fails at boot instead (same posture as
``react_repeated_call_terminal_threshold``).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.agents import AgentsSettings
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, ToolFilter, UserGoal

pytestmark = pytest.mark.unit


def _intelligence() -> QueryIntelligence:
    return QueryIntelligence(
        original_query="q",
        english_query="q",
        immediate_intent="search",
        immediate_confidence=0.8,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="test",
        domains=["contact"],
        primary_domain="contact",
        domain_scores={},
        turn_type="ACTION",
        route_to="planner",
        bypass_llm=False,
        confidence=0.8,
        reasoning_trace=[],
    )


class TestTheNormalCapComesFromSettings:
    def test_tool_filter_reads_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "planner_catalogue_max_tools", 14, raising=False)

        assert ToolFilter.from_intelligence(_intelligence()).max_tools == 14

    def test_the_dataclass_default_matches_the_setting(self) -> None:
        """A ToolFilter built by hand must not silently get a different cap —
        the old default was 5, four short of what every request actually used."""
        from src.core.config import settings

        assert ToolFilter(domains=["contact"], categories=[]).max_tools == (
            settings.planner_catalogue_max_tools
        )


class TestThePanicCapComesFromSettings:
    def test_panic_strategy_reads_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings
        from src.domains.agents.services.catalogue.strategies import panic_filtering

        monkeypatch.setattr(settings, "planner_catalogue_panic_max_tools", 21, raising=False)

        assert panic_filtering._panic_max_tools() == 21


class TestTheSafetyNetIsNeverNarrowerThanTheNormalPath:
    def test_a_panic_cap_below_the_normal_one_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="planner_catalogue_panic_max_tools"):
            AgentsSettings(planner_catalogue_max_tools=12, planner_catalogue_panic_max_tools=8)

    def test_equal_caps_are_allowed(self) -> None:
        """Equal is a deliberate "no widening on panic", not an inversion."""
        settings_obj = AgentsSettings(
            planner_catalogue_max_tools=12, planner_catalogue_panic_max_tools=12
        )

        assert settings_obj.planner_catalogue_panic_max_tools == 12

    def test_the_shipped_defaults_satisfy_the_invariant(self) -> None:
        settings_obj = AgentsSettings()

        assert (
            settings_obj.planner_catalogue_panic_max_tools
            >= settings_obj.planner_catalogue_max_tools
        )
