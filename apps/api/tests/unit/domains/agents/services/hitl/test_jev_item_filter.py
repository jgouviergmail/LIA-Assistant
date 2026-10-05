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


def clear_answers(items):
    return {**items, "reference_scope": answer("clear", 0.8)}


async def call(items, answers, *, outcome="success", mutate=False, criteria="Exclude newsletters"):
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
        result = await module.try_filter_items(items, criteria, "run")
    return result, request, debug


async def test_full_previews_shared_in_one_batch_and_original_indices_kept():
    items = [
        {"id": "a", "subject": "same", "body": "a" * 500},
        {"id": "b", "subject": "same", "read": False},
    ]
    result, request, debug = await call(
        items, clear_answers({"item_0": answer("exclude"), "item_1": answer("keep")})
    )
    assert result == [1] and request.await_count == 1
    assert request.call_args.kwargs["state"]["items"]["item_0"]["body"] == "a" * 500
    assert request.call_args.kwargs["state"]["items"]["item_1"]["read"] is False
    assert "items.item_0" in request.call_args.kwargs["questions"]["item_0"].instructions
    assert set(request.call_args.kwargs["questions"]) == {"item_0", "item_1", "reference_scope"}
    assert (
        "`exclude_criteria`"
        in request.call_args.kwargs["questions"]["reference_scope"].instructions
    )
    assert debug.call_args.kwargs["target"] == "human_reconfirmation"
    assert (
        debug.call_args.kwargs["decision_labels"]["reference_scope"] == "Exclusion reference scope"
    )
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
    result, _, debug = await call([{"subject": "a"}, {"subject": "b"}], clear_answers(answers))
    assert result is None and debug.call_args.kwargs["action"] == "fallback"


@pytest.mark.parametrize("outcome", ["disabled", "timeout", "invalid_response", "unavailable"])
async def test_native_unavailability_leaves_existing_filter(outcome):
    assert (await call([{"subject": "a"}], {}, outcome=outcome))[0] is None


async def test_all_exclusions_are_distinct_from_failure():
    assert (await call([{"subject": "a"}], clear_answers({"item_0": answer("exclude")})))[0] == []


async def test_changed_input_never_receives_a_stale_native_decision():
    assert (
        await call(
            [{"subject": "a"}, {"subject": "b"}],
            clear_answers({"item_0": answer("exclude"), "item_1": answer("keep")}),
            mutate=True,
        )
    )[0] is None


@pytest.mark.parametrize("count", [24, 25])
async def test_over_limit_batch_never_qualifies_only_a_subset(count):
    result, request, _ = await call([{"subject": str(i)} for i in range(count)], {})
    assert result is None
    request.assert_not_awaited()


async def test_twenty_three_items_share_the_last_question_with_reference_scope():
    items = [{"subject": str(i)} for i in range(23)]
    verdicts = clear_answers({f"item_{i}": answer("keep") for i in range(23)})
    result, request, debug = await call(items, verdicts)
    assert result == list(range(23))
    assert request.await_count == 1
    assert len(request.call_args.kwargs["questions"]) == 24
    labels = debug.call_args.kwargs["decision_labels"]
    assert len(labels) == 24 and labels["item_22"] == "22"
    assert labels["reference_scope"] == "Exclusion reference scope"


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"reference_scope": answer("clear", 0.799)},
        {"reference_scope": answer("uncertain")},
        {"reference_scope": answer("invented")},
        {"arbitrary_scope": answer("clear")},
        {"reference_scope": answer("clear"), "foreign": answer("keep")},
    ],
    ids=[
        "missing",
        "low-confidence",
        "ambiguous",
        "unknown-choice",
        "foreign-name",
        "extra-answer",
    ],
)
async def test_missing_ambiguous_or_foreign_scope_never_applies_confident_items(scope):
    result, request, debug = await call(
        [{"subject": "a"}, {"subject": "b"}],
        {"item_0": answer("exclude"), "item_1": answer("keep"), **scope},
    )
    assert result is None and request.await_count == 1
    assert debug.call_args.kwargs["action"] == "fallback"
    assert debug.call_args.kwargs["outcome"] == "uncertain"


@pytest.mark.parametrize("name", ["Robin", "Keala", "Zoë", "光"])
async def test_duplicate_names_cannot_expand_singular_exclusion_when_scope_is_ambiguous(name):
    items = [{"id": "a", "from": name}, {"id": "b", "from": name}]
    result, _, debug = await call(
        items,
        {
            "item_0": answer("exclude"),
            "item_1": answer("exclude"),
            "reference_scope": answer("uncertain"),
        },
        criteria=f"Exclude the email from {name}.",
    )
    assert result is None and items == [{"id": "a", "from": name}, {"id": "b", "from": name}]
    assert debug.call_args.kwargs["target"] == "item_filter"


async def test_clear_scope_does_not_lower_the_individual_item_threshold():
    result, _, _ = await call(
        [{"subject": "a"}],
        {"item_0": answer("exclude", 0.989), "reference_scope": answer("clear", 0.99)},
    )
    assert result is None


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
            answers=clear_answers(
                {f"item_{i}": answer("exclude" if i == 1 else "keep") for i in range(4)}
            ),
        ),
        DecisionAttempt(
            outcome="success",
            answers=clear_answers(
                {f"item_{i}": answer("exclude" if i == 0 else "keep") for i in range(3)}
            ),
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
            p["subject"] for p in _interrupt_payload(pending)["action_requests"][0]["item_previews"]
        ] == ["item-2", "item-3"]
        approved = await graph.ainvoke(Command(resume={"decision": "APPROVE"}), config)
    assert approved[STATE_KEY_FOR_EACH_HITL_CTX]["filtered_indices"] == [2, 3]
    assert native.await_count == 2
    llm.ainvoke.assert_not_awaited()
