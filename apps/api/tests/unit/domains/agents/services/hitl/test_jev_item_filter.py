"""Native HITL exclusion is atomic, positional and never authorizes an action."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


def answer(choice, confidence=0.999):
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={choice: confidence, "uncertain": 1 - confidence},
    )


async def call(items, answers, *, outcome="success", mutate=False):
    from src.domains.agents.services.hitl import jev_item_filter as module

    async def native(**kwargs):
        if mutate:
            items.reverse()
        return DecisionAttempt(outcome=outcome, answers=answers)

    with (
        patch.object(
            module, "runtime_context_if_running", return_value=SimpleNamespace(user_id=uuid4())
        ),
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=native)) as request,
        patch.object(module, "record_action", AsyncMock()) as debug,
    ):
        result = await module.try_filter_items(items, "Exclude newsletters", "run")
    return result, request, debug


async def test_full_previews_shared_in_one_batch_and_original_indices_kept():
    items = [
        {"id": "a", "subject": "same", "body": "a" * 500},
        {"id": "b", "subject": "same", "read": False},
    ]
    result, request, debug = await call(
        items, {"item_0": answer("exclude"), "item_1": answer("keep")}
    )
    assert result == [1] and request.await_count == 1
    assert request.call_args.kwargs["state"]["items"]["item_0"]["body"] == "a" * 500
    assert request.call_args.kwargs["state"]["items"]["item_1"]["read"] is False
    assert "items.item_0" in request.call_args.kwargs["questions"]["item_0"].instructions
    assert debug.call_args.kwargs["target"] == "human_reconfirmation"
    assert len(items) == 2


@pytest.mark.parametrize(
    "answers",
    [
        {"item_0": answer("exclude"), "item_1": answer("keep", 0.6)},
        {"item_0": answer("exclude"), "item_1": answer("uncertain")},
        {"item_0": answer("exclude")},
        {"item_0": answer("exclude"), "item_1": answer("invented")},
    ],
)
async def test_one_ambiguous_or_missing_answer_falls_back_for_entire_list(answers):
    result, _, debug = await call([{"subject": "a"}, {"subject": "b"}], answers)
    assert result is None and debug.call_args.kwargs["action"] == "fallback"


@pytest.mark.parametrize("outcome", ["disabled", "timeout", "invalid_response", "unavailable"])
async def test_native_unavailability_leaves_existing_filter(outcome):
    assert (await call([{"subject": "a"}], {}, outcome=outcome))[0] is None


async def test_all_exclusions_are_distinct_from_failure():
    assert (await call([{"subject": "a"}], {"item_0": answer("exclude")}))[0] == []


async def test_changed_input_never_receives_a_stale_native_decision():
    assert (
        await call(
            [{"subject": "a"}, {"subject": "b"}],
            {"item_0": answer("exclude"), "item_1": answer("keep")},
            mutate=True,
        )
    )[0] is None


async def test_over_limit_batch_never_qualifies_only_a_subset():
    result, request, _ = await call([{"subject": str(i)} for i in range(25)], {})
    assert result is None
    request.assert_not_awaited()


async def test_real_service_shortcut_and_fallback_share_the_existing_contract():
    from src.domains.agents.services.hitl import item_filter as service_module
    from src.domains.agents.services.hitl import jev_item_filter as module

    llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(text="[1]")))
    with patch.object(service_module, "get_llm", return_value=llm):
        service = service_module.ItemFilterService()
    with patch.object(module, "try_filter_items", AsyncMock(return_value=[1])):
        assert await service.filter([{"title": "a"}, {"title": "b"}], "a", "r") == [1]
        llm.ainvoke.assert_not_awaited()
    with patch.object(module, "try_filter_items", AsyncMock(return_value=None)):
        assert await service.filter([{"title": "a"}, {"title": "b"}], "b", "r") == [0]
        llm.ainvoke.assert_awaited_once()


async def test_real_native_filter_is_checkpointed_and_reconfirmation_stays_mandatory():
    from langgraph.types import Command

    from src.domains.agents.constants import STATE_KEY_FOR_EACH_HITL_CTX
    from src.domains.agents.services.hitl import item_filter as service_module
    from src.domains.agents.services.hitl import jev_item_filter as module
    from tests.unit.domains.agents.nodes.test_for_each_confirm_replay import (
        _build_graph,
        _initial_input,
        _interrupt_payload,
        _make_ctx,
    )

    llm = SimpleNamespace(ainvoke=AsyncMock())
    with patch.object(service_module, "get_llm", return_value=llm):
        service = service_module.ItemFilterService()
    graph = _build_graph()
    config = {"configurable": {"thread_id": "jev-real-filter-replay"}}
    verdicts = [
        DecisionAttempt(
            outcome="success",
            answers={f"item_{i}": answer("exclude" if i == 1 else "keep") for i in range(4)},
        ),
        DecisionAttempt(
            outcome="success",
            answers={f"item_{i}": answer("exclude" if i == 0 else "keep") for i in range(3)},
        ),
    ]
    with (
        patch(
            "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
            return_value=service,
        ),
        patch.object(
            module, "runtime_context_if_running", return_value=SimpleNamespace(user_id=uuid4())
        ),
        patch.object(module, "choose_many_with_jev", AsyncMock(side_effect=verdicts)) as native,
    ):
        await graph.ainvoke(_initial_input(_make_ctx()), config)
        for criterion in ("Remove the second item", "Remove the first remaining item"):
            pending = await graph.ainvoke(
                Command(resume={"decision": "EDIT", "exclude_criteria": criterion}), config
            )
            _interrupt_payload(pending)
            checkpoint = await graph.aget_state(config)
            assert checkpoint.values[STATE_KEY_FOR_EACH_HITL_CTX]["approved"] is False
        assert [
            p["label"] for p in _interrupt_payload(pending)["action_requests"][0]["item_previews"]
        ] == ["item-2", "item-3"]
        approved = await graph.ainvoke(Command(resume={"decision": "APPROVE"}), config)
    assert approved[STATE_KEY_FOR_EACH_HITL_CTX]["filtered_indices"] == [2, 3]
    assert native.await_count == 2
    llm.ainvoke.assert_not_awaited()
