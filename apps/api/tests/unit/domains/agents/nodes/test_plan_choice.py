"""« Which one? » before a plan acts on one of several items a lookup found (ADR-367 amendment).

Nothing shown, « reply to Marc's email » is planned as a lookup and an act on
its first result. When the lookup finds several, the first is a guess: the
lookup now runs first, the person is asked which one, and the plan acts on the
chosen item — nothing run twice, nothing acted on before the answer.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.domains.agents.constants import (
    NODE_REFERENCE_DISAMBIGUATION,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_CHOICE,
    STATE_KEY_PLAN_REJECTION_REASON,
)
from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.graph import route_from_orchestrator, route_from_reference_disambiguation
from src.domains.agents.nodes import plan_choice
from src.domains.agents.nodes.plan_choice import (
    NOT_CHOSEN,
    answered_choice,
    declined_choice,
    pending_choice,
    settle_plan_choice,
)
from src.domains.agents.nodes.reference_disambiguation_node import (
    asks_which_item,
    reference_disambiguation_node,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema
from src.domains.agents.tools import emails_tools  # noqa: F401 — registers "emails"

pytestmark = pytest.mark.unit

INTERRUPT = "src.domains.agents.nodes.reference_disambiguation_node.interrupt"

FOUND = [
    {"id": "m1", "from": "Marc <marc@example.com>", "subject": "Photos", "date_formatted": "mardi"},
    {
        "id": "m2",
        "from": "Marc <marc@example.com>",
        "subject": "Facture",
        "date_formatted": "lundi",
    },
    {"id": "m3", "from": "Marc <marc@example.com>", "subject": "Devis", "date_formatted": "jeudi"},
]


def _registry_id(message_id: str) -> str:
    return generate_registry_id(RegistryItemType.EMAIL, message_id)


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        user_id="u",
        steps=[
            ExecutionStep(
                step_id="find",
                step_type=StepType.TOOL,
                agent_name="email_agent",
                tool_name="get_emails_tool",
                parameters={"query": "from:marc", "max_results": 5},
            ),
            ExecutionStep(
                step_id="reply",
                step_type=StepType.TOOL,
                agent_name="email_agent",
                tool_name="create_mailbox_reply_draft_tool",
                parameters={"message_id": "$steps.find.emails[0].id"},
                depends_on=["find"],
            ),
        ],
    )


@dataclass
class _Outcome:
    completed_steps: dict[str, Any]
    registry: dict[str, Any] = field(default_factory=dict)


def _outcome(found: list[dict[str, Any]]) -> _Outcome:
    registry = {_registry_id(item["id"]): {"payload": item} for item in found}
    registry["contact_x"] = {"payload": {"name": "kept"}}
    return _Outcome({"find": {"emails": copy.deepcopy(found)}}, registry)


@pytest.fixture(autouse=True)
def _a_followed_turn_whose_reply_acts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_choice, "turn_follows_the_conversation", lambda: True)
    monkeypatch.setattr(plan_choice, "_acts", lambda tool: tool.startswith("create_"))


def _call(mock: AsyncMock) -> Any:
    """The mock's last await — which must have happened."""
    assert mock.await_args is not None
    return mock.await_args


def _state(**extra: Any) -> dict[str, Any]:
    return {"current_turn_id": 4, "user_language": "fr", **extra}


async def _settle(state: dict[str, Any], outcome: _Outcome | None) -> Any:
    with patch.object(plan_choice, "execute_steps_first", AsyncMock(return_value=outcome)) as first:
        result = await settle_plan_choice(_plan(), state, {}, "run", initial_registry={})
    return result, first


class TestTheLookupRunsFirst:
    async def test_several_found_hands_off_to_the_question_before_any_act(self) -> None:
        result, first = await _settle(_state(), _outcome(FOUND))

        first.assert_awaited_once()
        assert set(_call(first).args[1]) == {"find"}  # the lookup alone runs first
        context = result.ask[STATE_KEY_PLAN_CHOICE]
        assert result.ask[STATE_KEY_EXECUTION_PLAN].plan_id == "plan-1"
        assert context["pending"]["act"] == "reply"
        assert [c["id"] for c in context["pending"]["candidates"]] == ["m1", "m2", "m3"]
        assert context["turn_id"] == 4 and context["plan_id"] == "plan-1"

    async def test_the_question_offers_at_most_the_configured_candidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_max_candidates", 2)
        result, _ = await _settle(_state(), _outcome(FOUND))
        assert len(result.ask[STATE_KEY_PLAN_CHOICE]["pending"]["candidates"]) == 2

    async def test_one_found_runs_the_plan_on_it_without_running_the_lookup_again(self) -> None:
        result, _ = await _settle(_state(), _outcome(FOUND[:1]))

        assert result.ask is None
        assert result.completed["find"]["emails"][0]["id"] == "m1"

    async def test_a_turn_nobody_follows_runs_the_plan_as_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(plan_choice, "turn_follows_the_conversation", lambda: False)
        result, first = await _settle(_state(), _outcome(FOUND))
        assert result.ask is None and result.completed == {}
        first.assert_not_awaited()

    async def test_the_switch_off_runs_the_plan_as_written(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "entity_resolution_enabled", False)
        result, first = await _settle(_state(), _outcome(FOUND))
        assert result.ask is None
        first.assert_not_awaited()

    async def test_a_plan_with_no_act_on_a_first_item_runs_nothing_ahead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(plan_choice, "_acts", lambda _tool: False)
        result, first = await _settle(_state(), _outcome(FOUND))
        assert result.ask is None
        first.assert_not_awaited()


class TestTheAnswer:
    async def _asked(self) -> dict[str, Any]:
        result, _ = await _settle(_state(), _outcome(FOUND))
        context: dict[str, Any] = result.ask[STATE_KEY_PLAN_CHOICE]
        return context

    async def test_the_chosen_item_is_what_the_plan_acts_on(self) -> None:
        answered = answered_choice(await self._asked(), 2)
        result, first = await _settle(_state(**{STATE_KEY_PLAN_CHOICE: answered}), None)

        first.assert_not_awaited()  # the lookup's results are reused, never fetched again
        assert result.ask is None
        assert [item["id"] for item in result.completed["find"]["emails"]] == ["m2"]
        # The cards of the items not chosen are not drawn; everything else stays.
        assert _registry_id("m2") in result.registry and "contact_x" in result.registry
        assert _registry_id("m1") not in result.registry
        assert _registry_id("m3") not in result.registry

    async def test_a_second_pass_narrows_from_the_stored_lookup_once(self) -> None:
        state = _state(**{STATE_KEY_PLAN_CHOICE: answered_choice(await self._asked(), 3)})
        first, _ = await _settle(state, None)
        again, _ = await _settle(state, None)
        assert first.completed == again.completed
        assert [item["id"] for item in again.completed["find"]["emails"]] == ["m3"]

    async def test_a_declined_choice_leaves_the_act_unrun_and_the_lookup_whole(self) -> None:
        declined = declined_choice(await self._asked(), "none")
        result, first = await _settle(_state(**{STATE_KEY_PLAN_CHOICE: declined}), None)

        first.assert_not_awaited()
        assert result.ask is None
        assert result.not_run == {"reply": NOT_CHOSEN}
        # The lookup did run: what it found stays, for the answer to list.
        assert [item["id"] for item in result.completed["find"]["emails"]] == ["m1", "m2", "m3"]

    async def test_another_turn_s_choice_is_never_read(self) -> None:
        stale = {**answered_choice(await self._asked(), 2), "turn_id": 3}
        result, first = await _settle(_state(**{STATE_KEY_PLAN_CHOICE: stale}), _outcome(FOUND))
        first.assert_awaited_once()  # a new turn looks up afresh
        assert result.ask is not None


class TestTheQuestionNode:
    async def _pending_state(self) -> dict[str, Any]:
        result, _ = await _settle(_state(), _outcome(FOUND))
        return _state(**result.ask)

    async def test_the_pending_choice_is_asked_with_the_found_header(self) -> None:
        state = await self._pending_state()
        assert asks_which_item(state) and pending_choice(state) is not None
        with patch(INTERRUPT, return_value={"action": "select", "selected_index": 3}) as ask:
            update = await reference_disambiguation_node(state, {})

        request = ask.call_args.args[0]["action_requests"][0]
        assert request["found"] is True and len(request["candidates"]) == 3
        assert "Devis" in request["candidates"][2]["label"]
        assert update[STATE_KEY_PLAN_CHOICE]["answered"] == {"find": 3}
        assert update[STATE_KEY_PLAN_CHOICE]["pending"] is None

    @pytest.mark.parametrize("answer", [{"action": "none"}, {"action": "cancel"}])
    async def test_declining_is_never_a_rejected_plan(self, answer: dict[str, Any]) -> None:
        """The lookup ran: the plan-rejection directive's « nothing was read » would lie."""
        with patch(INTERRUPT, return_value=answer):
            update = await reference_disambiguation_node(await self._pending_state(), {})

        assert update[STATE_KEY_PLAN_CHOICE]["declined"] == answer["action"]
        assert STATE_KEY_PLAN_APPROVED not in update
        assert STATE_KEY_PLAN_REJECTION_REASON not in update


class TestTheRoute:
    async def test_the_orchestrator_hands_a_pending_choice_to_the_question(self) -> None:
        result, _ = await _settle(_state(), _outcome(FOUND))
        assert route_from_orchestrator(_state(**result.ask)) == NODE_REFERENCE_DISAMBIGUATION

    async def test_a_chosen_item_resumes_the_plan(self) -> None:
        result, _ = await _settle(_state(), _outcome(FOUND))
        answered = answered_choice(result.ask[STATE_KEY_PLAN_CHOICE], 1)
        state = _state(**{STATE_KEY_PLAN_CHOICE: answered})
        assert route_from_reference_disambiguation(state) == NODE_TASK_ORCHESTRATOR

    async def test_a_declined_choice_resumes_the_plan_without_its_act(self) -> None:
        result, _ = await _settle(_state(), _outcome(FOUND))
        declined = declined_choice(result.ask[STATE_KEY_PLAN_CHOICE], "cancel")
        state = _state(**{STATE_KEY_PLAN_CHOICE: declined})
        assert route_from_reference_disambiguation(state) == NODE_TASK_ORCHESTRATOR


class TestTheOrchestrator:
    """The orchestrator asks before executing anything, then resumes on the lookups."""

    async def _handle(
        self, choice: Any, held_plan_of: Any = None
    ) -> tuple[dict[str, Any], AsyncMock]:
        node = import_module("src.domains.agents.nodes.task_orchestrator_node")
        from src.domains.agents.orchestration import parallel_executor

        execute = AsyncMock(return_value=object())
        with (
            patch.object(node, "settle_plan_choice", AsyncMock(return_value=choice)),
            patch.object(parallel_executor, "execute_plan_parallel", execute),
            patch.object(node, "state_after_execution", lambda *a, **k: {"ran": True}),
            patch.object(node, "held_plan_of", held_plan_of or (lambda *a, **k: None)),
        ):
            update = await node._handle_execution_plan(_plan(), _state(), "run", {})
        return update, execute

    async def test_a_question_is_handed_off_with_nothing_executed(self) -> None:
        ask = {STATE_KEY_PLAN_CHOICE: {"pending": {"act": "reply"}}}
        update, execute = await self._handle(plan_choice.ChoicePass(ask=ask))
        assert update == ask
        execute.assert_not_awaited()

    async def test_an_act_nobody_chose_an_item_for_never_runs_and_is_said(self) -> None:
        captured: dict[str, Any] = {}

        def held(plan: Any, outcome: Any, *, previous: Any) -> None:
            captured["previous"] = previous

        choice = plan_choice.ChoicePass(
            completed={"find": {"emails": FOUND}}, not_run={"reply": NOT_CHOSEN}
        )
        _, execute = await self._handle(choice, held_plan_of=held)

        ran = _call(execute).kwargs["execution_plan"]
        assert [step.step_id for step in ran.steps] == ["find"]
        assert captured["previous"] == {"not_run": {"reply": NOT_CHOSEN}}

    async def test_the_plan_resumes_from_the_lookups_already_run(self) -> None:
        completed = {"find": {"emails": [FOUND[1]]}}
        registry = {_registry_id("m2"): {"payload": FOUND[1]}}
        update, execute = await self._handle(
            plan_choice.ChoicePass(completed=completed, registry=registry)
        )
        assert update == {"ran": True}
        kwargs = _call(execute).kwargs
        assert kwargs["initial_completed_steps"] == completed
        assert kwargs["pre_executed_registry"] == registry


async def test_a_list_holding_something_no_record_is_not_asked_about() -> None:
    """The answer's position indexes the list itself: a stray value would shift it."""
    outcome = _outcome(FOUND)
    outcome.completed_steps["find"]["emails"].insert(1, "not a record")
    result, _ = await _settle(_state(), outcome)
    assert result.ask is None


class TestThePersonSaysWhichOne:
    """« Marc's latest email » keeps the planner's cap of one; it never silences a choice.

    Measured 2026-10-31 on four model families: one capped « reply to Marc's email »
    at one result three times in four, which hid the choice — so a cap of one is
    widened when nobody said which. A position word only keeps that cap: « last »
    is also in « last week », a date that leaves several e-mails open.
    """

    @staticmethod
    def _asking(query: str, language: str = "fr") -> dict[str, Any]:
        return _state(user_language=language, query_intelligence={"original_query": query})

    @pytest.mark.parametrize(
        ("query", "language"),
        [
            ("Réponds au dernier mail de Marc", "fr"),
            ("Réponds au mail le plus récent de Marc", "fr"),
            ("Reply to Marc's latest email", "en"),
            ("Antworte auf die neueste Mail von Marc", "de"),
            ("回复马克最新的邮件", "zh-CN"),
        ],
    )
    async def test_a_position_in_the_request_keeps_the_planner_s_cap_of_one(
        self, query: str, language: str
    ) -> None:
        plan = _plan()
        plan.steps[0].parameters["max_results"] = 1
        with patch.object(
            plan_choice, "execute_steps_first", AsyncMock(return_value=_outcome(FOUND[:1]))
        ) as first:
            result = await settle_plan_choice(
                plan, self._asking(query, language), {}, "run", initial_registry={}
            )
        assert _call(first).args[0].steps[0].parameters["max_results"] == 1
        assert result.ask is None

    @pytest.mark.parametrize(
        ("query", "language"),
        [
            ("Réponds au mail de Marc de la semaine dernière", "fr"),
            ("Reply to Marc's email from last week", "en"),
        ],
    )
    async def test_a_position_word_never_silences_several_found(
        self, query: str, language: str
    ) -> None:
        result, _ = await _settle(self._asking(query, language), _outcome(FOUND))
        assert result.ask is not None

    async def test_a_lookup_capped_at_one_is_widened_when_nobody_said_which(self) -> None:
        plan = _plan()
        plan.steps[0].parameters["max_results"] = 1
        with patch.object(
            plan_choice, "execute_steps_first", AsyncMock(return_value=_outcome(FOUND))
        ) as first:
            result = await settle_plan_choice(
                plan, self._asking("Réponds au mail de Marc"), {}, "run", initial_registry={}
            )
        widened = _call(first).args[0]
        assert (
            widened.steps[0].parameters["max_results"] == settings.entity_resolution_max_candidates
        )
        assert plan.steps[0].parameters["max_results"] == 1  # the plan itself is untouched
        assert result.ask is not None

    async def test_the_widened_cap_stays_within_the_tool_s_published_maximum(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Widening runs after the planner's bound repair: it must not undo it."""
        maximum = settings.entity_resolution_max_candidates - 1
        schema = ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="",
            constraints=[ParameterConstraint(kind="maximum", value=maximum)],
        )
        monkeypatch.setattr(
            plan_choice,
            "resolve_tool_manifest_named",
            lambda name: (SimpleNamespace(parameters=[schema]), name),
        )
        plan = _plan()
        plan.steps[0].parameters["max_results"] = 1
        with patch.object(
            plan_choice, "execute_steps_first", AsyncMock(return_value=_outcome(FOUND))
        ) as first:
            await settle_plan_choice(
                plan, self._asking("Réponds au mail de Marc"), {}, "run", initial_registry={}
            )
        assert _call(first).args[0].steps[0].parameters["max_results"] == maximum
