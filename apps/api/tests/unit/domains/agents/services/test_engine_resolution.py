"""Which engine plans a turn, and why (ADR-070, automatic mode).

The rule was qualified on the 2026-11-15 held-out corpus
(``scripts/agents/execution_mode_corpus.py``): the pipeline plans a turn only when
the analysis shows no shape it cannot finish in one plan AND the decision provider
judged the three loop properties absent. Every doubt goes to the loop, because a
complete answer comes before a fast one.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.services.engine_resolution import (
    EngineReason,
    EngineResolution,
    resolve_engine,
)

pytestmark = pytest.mark.unit


def _planned(**fields: object) -> QueryIntelligence:
    base = QueryIntelligence(
        original_query="q",
        english_query="q",
        immediate_intent="search",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="",
        domains=["event"],
        route_to="planner",
    )
    return replace(base, **fields)


def _resolve(
    requested: str, intelligence: QueryIntelligence, verdict: EngineReason, *, loop: bool = True
) -> EngineResolution:
    return resolve_engine(requested, intelligence, verdict, loop_enabled=loop)


class TestAnExplicitChoiceIsObeyed:
    @pytest.mark.parametrize("requested", ["pipeline", "react"])
    def test_the_engine_asked_for_runs(self, requested: str) -> None:
        resolution = _resolve(
            requested, _planned(is_mutation_intent=True), EngineReason.NO_DECISION
        )

        assert (resolution.engine, resolution.reason) == (requested, EngineReason.REQUESTED)

    def test_an_unreadable_choice_plans_in_the_pipeline_like_the_edge(self) -> None:
        resolution = _resolve("garbage", _planned(), EngineReason.DIRECT)

        assert (resolution.engine, resolution.reason) == ("pipeline", EngineReason.REQUESTED)

    @pytest.mark.parametrize("requested", ["react", "auto"])
    def test_the_loop_switched_off_plans_in_the_pipeline(self, requested: str) -> None:
        resolution = _resolve(requested, _planned(), EngineReason.COMPUTED, loop=False)

        assert (resolution.engine, resolution.reason) == ("pipeline", EngineReason.LOOP_DISABLED)

    def test_the_pipeline_asked_with_the_loop_off_is_still_a_choice(self) -> None:
        resolution = _resolve("pipeline", _planned(), EngineReason.DIRECT, loop=False)

        assert resolution.reason is EngineReason.REQUESTED


class TestTheAnalysisSendsShapesToTheLoop:
    """Shapes the analysis reads: they win over any verdict, a direct one included."""

    @pytest.mark.parametrize(
        ("fields", "reason"),
        [
            ({"is_mutation_intent": True}, EngineReason.ACT),
            ({"for_each_detected": True}, EngineReason.ITEM_WISE),
            ({"detected_skill_name": "daily_brief"}, EngineReason.SKILL),
            ({"turn_type": "REFERENCE_ACTION"}, EngineReason.REFERENCE),
            ({"domains": ["calculation", "event"]}, EngineReason.CALCULATION),
        ],
    )
    def test_a_shape_the_plan_cannot_finish(
        self, fields: dict[str, object], reason: EngineReason
    ) -> None:
        resolution = _resolve("auto", _planned(**fields), EngineReason.DIRECT)

        assert (resolution.engine, resolution.reason) == ("react", reason)

    def test_a_calculation_alone_is_no_such_shape(self) -> None:
        """« 15 % of 2,480 »: every number is in the request, one tool computes it."""
        resolution = _resolve("auto", _planned(domains=["calculation"]), EngineReason.DIRECT)

        assert resolution.engine == "pipeline"

    def test_the_calculation_domain_is_the_registry_s(self) -> None:
        """A renamed domain would silently stop the rule from reading it."""
        from src.domains.agents.constants import AGENT_CALCULATION, DOMAIN_CALCULATION
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        assert AGENT_CALCULATION in DOMAIN_REGISTRY[DOMAIN_CALCULATION].agent_names


class TestTheVerdictDecidesTheRest:
    @pytest.mark.parametrize(
        "verdict",
        [
            EngineReason.COMPUTED,
            EngineReason.CROSS_CHECK,
            EngineReason.OPEN_ENDED,
            EngineReason.NAMED_IN_TEXT,
            EngineReason.NO_DECISION,
        ],
    )
    def test_any_doubt_goes_to_the_loop(self, verdict: EngineReason) -> None:
        resolution = _resolve("auto", _planned(), verdict)

        assert (resolution.engine, resolution.reason) == ("react", verdict)

    def test_a_direct_shape_plans_in_the_pipeline(self) -> None:
        resolution = _resolve("auto", _planned(), EngineReason.DIRECT)

        assert (resolution.engine, resolution.reason) == ("pipeline", EngineReason.DIRECT)

    @pytest.mark.parametrize(
        "reason",
        [EngineReason.REQUESTED, EngineReason.LOOP_DISABLED, EngineReason.ACT],
    )
    def test_a_verdict_is_only_ever_a_judgement_of_the_shape(self, reason: EngineReason) -> None:
        """A caller handing the resolver what is not a verdict is a programming error."""
        with pytest.raises(ValueError):
            _resolve("auto", _planned(), reason)
