"""A native choice selects only an authorized fixed read plan; it invents no parameters."""

import importlib
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


def intelligence() -> QueryIntelligence:
    return QueryIntelligence(
        original_query="Mes emails non lus",
        english_query="My unread emails",
        immediate_intent="search",
        immediate_confidence=0.99,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="Read",
        domains=["email"],
        primary_domain="email",
        confidence=0.99,
    )


def attempt(key: str, confidence: float = 0.999) -> DecisionAttempt:
    return DecisionAttempt(
        outcome="success",
        answer=ChoiceAnswer(
            type="choice",
            choice=key,
            confidence=confidence,
            probabilities={key: 0.999, "other": 0.001},
        ),
    )


async def invoke(module, qi, verdict, *, allowed=True, policy=None):
    catalogue = FilteredCatalogue(
        [{"name": "get_emails_tool"}] if allowed else [], int(allowed), 100, ["email"], ["search"]
    )
    manifests = [
        SimpleNamespace(
            name="get_emails_tool",
            agent="email_agent",
            mutation_policy=policy,
            execution_modes={"pipeline"},
            permissions=SimpleNamespace(hitl_required=False),
            tool_category="search",
        )
    ]
    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(user_id=uuid4(), thread_id="t", conversation_id="t"),
        ),
        patch.object(module, "get_request_tool_manifests", return_value=manifests),
        patch.object(module, "choose_with_jev", AsyncMock(return_value=verdict)) as native,
    ):
        result = await module.try_consultation_plan(
            qi, {}, catalogue, journal_context="Full journal context"
        )
    return result, native


async def test_known_unread_plan_keeps_parameters_and_entire_query_context() -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    result, native = await invoke(module, intelligence(), attempt("email_unread"))
    assert result is not None and result.plan is not None
    assert [(step.tool_name, step.parameters) for step in result.plan.steps] == [
        ("get_emails_tool", {"query": "is:unread"})
    ]
    assert not result.plan.metadata.get("skip_semantic_validation")
    sent = native.call_args.kwargs["state"]
    assert sent["intelligence"]["english_query"] == "My unread emails"
    assert sent["intelligence"]["original_query"] == "Mes emails non lus"
    assert sent["journal_context"] == "Full journal context"
    assert result.tokens_saved == 0  # no fabricated savings


@pytest.mark.parametrize(
    "change",
    [
        {"is_mutation_intent": True},
        {"domains": ["email", "contact"]},
        {"has_temporal_reference": True},
        {"for_each_detected": True},
        {"has_cardinality_risk": True},
        {"detected_skill_name": "special"},
        {"turn_type": "REFERENCE_ACTION"},
        {"english_query": ""},
    ],
)
async def test_complex_queries_remain_with_existing_planner(change) -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    result, native = await invoke(
        module, replace(intelligence(), **change), attempt("email_unread")
    )
    assert result is None
    native.assert_not_awaited()


@pytest.mark.parametrize(
    "verdict",
    [
        attempt("other"),
        attempt("invented"),
        attempt("email_unread", 0.9),
        DecisionAttempt(outcome="timeout"),
        DecisionAttempt(outcome="disabled"),
    ],
)
async def test_uncertain_or_unavailable_decision_does_not_produce_a_plan(verdict) -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    result, _ = await invoke(module, intelligence(), verdict)
    assert result is None


@pytest.mark.parametrize("allowed,policy", [(False, None), (True, "confirm"), (True, "sandboxed")])
async def test_filtered_or_acting_tool_cannot_reenter_through_native_path(allowed, policy) -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    result, native = await invoke(
        module, intelligence(), attempt("email_unread"), allowed=allowed, policy=policy
    )
    assert result is None
    native.assert_not_awaited()


async def test_low_confidence_fallback_analysis_does_not_take_a_shortcut() -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    result, native = await invoke(
        module, replace(intelligence(), confidence=0.5), attempt("email_unread")
    )
    assert result is None
    native.assert_not_awaited()


@pytest.mark.parametrize("replan", [False, True])
async def test_service_integrates_after_exclusions_and_never_on_replan(replan) -> None:
    from unittest.mock import MagicMock

    from src.domains.agents.services.planner.planning_result import PlanningResult
    from src.domains.agents.services.smart_planner_service import SmartPlannerService

    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    service = SmartPlannerService()
    service.catalogue_service = MagicMock()
    filtered = FilteredCatalogue(
        [{"name": "get_emails_tool"}, {"name": "forbidden_tool"}], 2, 100, ["email"], ["search"]
    )
    service.catalogue_service.filter_for_intelligence.return_value = filtered
    fallback = SimpleNamespace(
        requires_catalogue=True,
        can_handle=AsyncMock(return_value=True),
        plan=AsyncMock(return_value=PlanningResult(plan=None, success=True)),
    )
    service.strategies = [fallback]
    expected = PlanningResult(plan=None, success=True)
    with (
        patch(
            "src.domains.agents.services.planner_capability_filter.merge_capability_exclusions",
            AsyncMock(return_value={"forbidden_tool"}),
        ),
        patch.object(module, "try_consultation_plan", AsyncMock(return_value=expected)) as native,
    ):
        result = await service.plan(
            intelligence(), {}, validation_feedback="Fix the original plan" if replan else None
        )
    if replan:
        native.assert_not_awaited()
        fallback.plan.assert_awaited_once()
    else:
        assert result is expected
        assert native.call_args.args[2].get_tool_names() == ["get_emails_tool"]
        fallback.plan.assert_not_awaited()


def test_every_fixed_path_matches_the_actual_executable_tool_contract() -> None:
    module = importlib.import_module("src.domains.agents.services.planner.jev_consultation")
    sources = {
        "email": "emails_tools",
        "contact": "google_contacts_tools",
        "file": "drive_tools",
        "task": "tasks_tools",
        "reminder": "reminder_tools",
    }
    for path in module.READ_PATHS.values():
        tool = getattr(
            importlib.import_module("src.domains.agents.tools." + sources[path.domain]), path.tool
        )
        schema = tool.tool_call_schema
        schema.model_validate(dict(path.parameters))
    question = module.consultation_question(module.READ_PATHS)
    assert set(question.criteria) == set(module.READ_PATHS) | {"other"}
