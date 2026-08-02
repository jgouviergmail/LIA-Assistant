"""A question that only READS must not produce a plan that WRITES.

Production, 2026-08-01 — "de quand date mon dernier appel à ma femme ?":

    step_1 = get_contacts_tool(query="ma femme")
    step_2 = place_phone_call_tool(contact=$steps.step_1.contacts[0].name,
                                   objective="vérifier la date du dernier appel")

The user asked WHEN; the plan was to PHONE HER AND ASK. Nothing stopped it:
``should_trigger_semantic_validation`` skipped the whole review with reason
``well_formed_cross_domain_mutation`` — a two-step plan, chained by a $steps
reference, ending on a mutation is exactly the shape that exemption was written
for. The better-formed the plan, the less it was checked.

The guard added here is deterministic (no LLM, no token cost) and runs BEFORE
that trigger, next to the three other pre-LLM rules, so the exemption cannot
swallow it. It is the mirror image of a rule that already existed —
"mutation intent but no mutation tool" — which had no counterpart in the other
direction.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.orchestration.plan_predicates import plan_writes_without_write_intent
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.registry import reset_global_registry, set_global_registry
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _global_catalogue():
    """`tool_is_mutation` reads declared categories off the global catalogue."""
    from src.domains.agents.telephony.catalogue_manifests import (
        TELEPHONY_AGENT_MANIFEST,
        place_phone_call_catalogue_manifest,
    )

    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry.register_agent_manifest(TELEPHONY_AGENT_MANIFEST)
    registry.register_tool_manifest(place_phone_call_catalogue_manifest, override=True)
    set_global_registry(registry)
    yield registry
    # Leaving this registry in place would change `tool_is_mutation` for every
    # later test in the session: with the telephony manifest loaded,
    # place_phone_call_tool becomes a DECLARED mutation, which is exactly what
    # `test_single_step_phone_call_stays_trivial` asserts it is not (that test
    # runs without the flag). Same cleanup as the conftest fixtures.
    reset_global_registry()


def _step(step_id: str, tool: str, agent: str, params: dict | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name=agent,
        tool_name=tool,
        parameters=params or {},
        description=f"test {tool}",
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p", user_id="u", session_id="s", steps=list(steps), execution_mode="sequential"
    )


def _intelligence(*, mutation: bool) -> QueryIntelligence:
    return QueryIntelligence(
        original_query="q",
        english_query="q",
        immediate_intent="search",
        immediate_confidence=0.7,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="test",
        domains=["telephony", "contact"],
        primary_domain="telephony",
        domain_scores={},
        turn_type="ACTION",
        route_to="planner",
        bypass_llm=False,
        confidence=0.7,
        reasoning_trace=[],
        is_mutation_intent=mutation,
    )


CONTACTS = _step("step_1", "get_contacts_tool", "contact_agent", {"query": "ma femme"})
CALL = _step(
    "step_2",
    "place_phone_call_tool",
    "telephony_agent",
    {"contact": "$steps.step_1.contacts[0].name", "objective": "vérifier la date"},
)
SEND = _step("step_2", "send_email_tool", "email_agent", {"to": "x@y.z", "body": "hi"})
EMAILS = _step("step_2", "get_emails_tool", "email_agent", {"query": "from:x"})


class TestTheProductionDefect:
    def test_read_question_planning_a_phone_call_is_caught(self) -> None:
        offenders = plan_writes_without_write_intent(
            _plan(CONTACTS, CALL), _intelligence(mutation=False)
        )

        assert offenders == ["place_phone_call_tool"]


class TestLegitimatePlansAreUntouched:
    def test_send_an_email_to_marie(self) -> None:
        """Mutation intent detected: the plan is doing what was asked."""
        assert (
            plan_writes_without_write_intent(_plan(CONTACTS, SEND), _intelligence(mutation=True))
            == []
        )

    def test_call_marie(self) -> None:
        assert (
            plan_writes_without_write_intent(_plan(CONTACTS, CALL), _intelligence(mutation=True))
            == []
        )

    def test_read_question_with_a_read_plan(self) -> None:
        assert (
            plan_writes_without_write_intent(_plan(CONTACTS, EMAILS), _intelligence(mutation=False))
            == []
        )

    def test_single_step_read(self) -> None:
        assert (
            plan_writes_without_write_intent(_plan(CONTACTS), _intelligence(mutation=False)) == []
        )


class TestEdgeCases:
    def test_no_intelligence_never_fires(self) -> None:
        """Without an analyzer verdict there is no read intent to contradict."""
        assert plan_writes_without_write_intent(_plan(CONTACTS, CALL), None) == []

    def test_an_intelligence_carrying_no_verdict_never_fires(self) -> None:
        """**Absent is not False.**

        Only an EXPLICIT ``is_mutation_intent=False`` may contradict a writing
        plan. A payload that carries no verdict at all — a partially
        serialized state, a dict assembled by another layer, an older shape —
        says nothing about intent, and reading that silence as "the user only
        wanted to read" would send every legitimate ACTION back to the planner.

        The two forms must agree, because the state round-trips through both.
        """
        assert (
            plan_writes_without_write_intent(_plan(CONTACTS, CALL), {"domains": ["telephony"]})
            == []
        )
        assert (
            plan_writes_without_write_intent(
                _plan(CONTACTS, CALL), SimpleNamespace(domains=["telephony"])
            )
            == []
        )

    def test_empty_plan(self) -> None:
        """Dict form: ExecutionPlan itself forbids a stepless plan."""
        assert plan_writes_without_write_intent({"steps": []}, _intelligence(mutation=False)) == []

    def test_none_plan(self) -> None:
        assert plan_writes_without_write_intent(None, _intelligence(mutation=False)) == []

    def test_dict_serialized_intelligence(self) -> None:
        """LangGraph round-trips the state: the dict form must behave the same."""
        as_dict = {"is_mutation_intent": False, "domains": ["telephony"]}

        assert plan_writes_without_write_intent(_plan(CONTACTS, CALL), as_dict) == [
            "place_phone_call_tool"
        ]

    def test_every_offending_step_is_reported(self) -> None:
        """Not just the last one: a read plan must contain NO write at all."""
        send = _step("step_2", "send_email_tool", "email_agent", {"to": "x@y.z", "body": "hi"})
        call = _step("step_3", "place_phone_call_tool", "telephony_agent", {"contact": "x"})

        offenders = plan_writes_without_write_intent(
            _plan(CONTACTS, send, call), _intelligence(mutation=False)
        )

        assert offenders == ["send_email_tool", "place_phone_call_tool"]
