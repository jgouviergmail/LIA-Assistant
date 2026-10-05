"""A preview position must select the same original item at the real consumer."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from src.domains.agents.constants import STATE_KEY_FOR_EACH_HITL_CTX
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.nodes.for_each_preview_identity import (
    apply_filtered_source_items,
    replace_filtered_source_items,
    resolve_item_preview_indices,
)
from src.domains.agents.nodes.task_orchestrator_node import _handle_execution_plan
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.tools.runtime_helpers import extract_value_by_path
from tests.unit.domains.agents.nodes.test_for_each_confirm_replay import (
    _build_graph,
    _initial_input,
    _interrupt_payload,
    _make_ctx,
    _SpyFilter,
)
from tests.unit.domains.agents.nodes.test_task_orchestrator_for_each_helpers import _registry_item

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.mark.parametrize("selections", [[[1]], [[0, 1], [1]], [[1, 0], [0]]])
@pytest.mark.parametrize("field_path", ["emails", "data.emails", "data.0.emails"])
async def test_skipped_preview_keeps_original_identity_through_real_orchestrator(
    selections,
    field_path,
) -> None:
    """Provider → real prep → edit/checkpoint → approve → real executor input."""
    plan = ExecutionPlan(
        plan_id="identity-plan",
        user_id="synthetic-owner",
        steps=[
            ExecutionStep(
                step_id="delete",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name="delete_email_tool",
                for_each=f"$steps.get_emails.{field_path}",
                for_each_max=3,
            )
        ],
    )
    original = [
        {"id": "no-preview"},
        {"id": "first-visible", "subject": "First visible"},
        {"id": "selected-visible", "subject": "Selected visible"},
    ]
    provider_data = {
        "emails": {"emails": original},
        "data.emails": {"data": {"emails": original}},
        "data.0.emails": {"data": [{"emails": original}]},
    }[field_path]
    registry = dict(
        _registry_item(RegistryItemType.EMAIL, item["id"], item, "emails") for item in original
    )
    state = {"messages": [], "current_turn_id": 1, "user_language": "fr"}
    spy = _SpyFilter(selections)
    graph = _build_graph()
    config = {"configurable": {"thread_id": "preview-identity"}}
    with (
        patch(
            "src.domains.agents.nodes.task_orchestrator_node.pre_execute_for_each_providers",
            AsyncMock(
                return_value=(
                    {"get_emails": provider_data},
                    {f"$steps.get_emails.{field_path}": 3},
                    registry,
                )
            ),
        ) as pre_execute,
        patch(
            "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
            return_value=spy,
        ),
        patch(
            "src.domains.agents.orchestration.parallel_executor.execute_plan_parallel",
            AsyncMock(side_effect=RuntimeError("synthetic stop before any action")),
        ) as execute,
    ):
        prepared = await _handle_execution_plan(plan, state, "synthetic-run", config)
        ctx = prepared[STATE_KEY_FOR_EACH_HITL_CTX]
        assert ctx["item_previews"] == [
            {"subject": "First visible"},
            {"subject": "Selected visible"},
        ]
        await graph.ainvoke(_initial_input(ctx), config)
        for _ in selections:
            pending = await graph.ainvoke(
                Command(
                    resume={"decision": "EDIT", "exclude_criteria": "Keep the selected visible"}
                ),
                config,
            )
        assert _interrupt_payload(pending)["action_requests"][0]["item_previews"] == [
            {"subject": "Selected visible"}
        ]
        execute.assert_not_awaited()
        checkpoint = await graph.aget_state(config)
        assert checkpoint.values[STATE_KEY_FOR_EACH_HITL_CTX]["approved"] is False
        assert checkpoint.values[STATE_KEY_FOR_EACH_HITL_CTX]["item_preview_indices"] == [2]
        serializer = JsonPlusSerializer()
        roundtrip = serializer.loads_typed(
            serializer.dumps_typed(checkpoint.values[STATE_KEY_FOR_EACH_HITL_CTX])
        )
        assert roundtrip["item_preview_indices"] == roundtrip["filtered_indices"] == [2]
        assert resolve_item_preview_indices(roundtrip) == [2]
        approved = await graph.ainvoke(Command(resume={"decision": "APPROVE"}), config)
        await _handle_execution_plan(plan, {**state, **approved}, "synthetic-run", config)
    pre_execute.assert_awaited_once()
    execute.assert_awaited_once()
    assert extract_value_by_path(
        execute.await_args.kwargs["initial_completed_steps"]["get_emails"], field_path
    ) == [original[2]]
    assert len(execute.await_args.kwargs["pre_executed_registry"]) == 1
    assert spy.calls == ["Keep the selected visible"] * len(selections)


@pytest.mark.parametrize(
    "invalid",
    [[True, 1, 2, 3], [-1, 1, 2, 3], [4, 1, 2, 3], [0, 0, 2, 3], ["0", 1, 2, 3], [1, 0, 2, 3]],
)
async def test_invalid_preview_correspondence_never_calls_filter(invalid) -> None:
    ctx = _make_ctx()
    ctx["item_preview_indices"] = invalid
    spy = _SpyFilter([[0]])
    graph = _build_graph()
    config = {"configurable": {"thread_id": "invalid-correspondence"}}
    with patch(
        "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service", return_value=spy
    ):
        await graph.ainvoke(_initial_input(ctx), config)
        pending = await graph.ainvoke(
            Command(resume={"decision": "EDIT", "exclude_criteria": "Remove an item"}), config
        )
    assert (
        _interrupt_payload(pending)["action_requests"][0]["item_previews"] == ctx["item_previews"]
    )
    assert spy.calls == []
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["filtered_indices"] is None


@pytest.mark.parametrize("invalid", [[True], [-1], [2], [0, 0], ["0"]])
async def test_invalid_filter_selection_keeps_the_same_preview_and_source(invalid) -> None:
    ctx = _make_ctx(2)
    spy = _SpyFilter([invalid])
    graph = _build_graph()
    config = {"configurable": {"thread_id": "invalid-filter-selection"}}
    with patch(
        "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service", return_value=spy
    ):
        await graph.ainvoke(_initial_input(ctx), config)
        pending = await graph.ainvoke(
            Command(resume={"decision": "EDIT", "exclude_criteria": "Remove an item"}), config
        )
    assert (
        _interrupt_payload(pending)["action_requests"][0]["item_previews"] == ctx["item_previews"]
    )
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["filtered_indices"] is None
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["pre_executed_steps"] == ctx["pre_executed_steps"]


async def test_ambiguous_legacy_edited_checkpoint_requires_reconfirmation() -> None:
    ctx = _make_ctx(2)
    ctx["pre_executed_steps"]["get_emails"]["emails"][1]["subject"] = "item-0"
    ctx["item_previews"] = [{"subject": "item-0"}]
    ctx["filtered_indices"] = [0]
    assert resolve_item_preview_indices(ctx) is None
    graph = _build_graph()
    config = {"configurable": {"thread_id": "legacy-ambiguous"}}
    await graph.ainvoke(_initial_input(ctx), config)
    pending = await graph.ainvoke(Command(resume={"decision": "APPROVE"}), config)
    assert _interrupt_payload(pending)
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["approved"] is False


async def test_source_mutated_during_filter_does_not_apply_selection() -> None:
    ctx = _make_ctx(2)
    graph = _build_graph()
    config = {"configurable": {"thread_id": "identity-mutation"}}

    class MutatingFilter:
        async def filter(self, item_previews, **kwargs):
            item_previews[0]["subject"] = "Changed during judgement"
            return [0]

    with patch(
        "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
        return_value=MutatingFilter(),
    ):
        await graph.ainvoke(_initial_input(deepcopy(ctx)), config)
        pending = await graph.ainvoke(
            Command(resume={"decision": "EDIT", "exclude_criteria": "Remove an item"}), config
        )
    assert _interrupt_payload(pending)
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["filtered_indices"] is None
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["approved"] is False


@pytest.mark.parametrize(
    "changed",
    [
        "source",
        "provider",
        "step",
        "tool",
        "missing_provider",
        "missing_path",
        "not_list",
        "empty_list",
    ],
)
async def test_real_consumer_never_executes_unproven_approved_source(changed) -> None:
    ctx = _make_ctx(2)
    ctx.update(
        approved=True,
        item_previews=[{"subject": "item-1"}],
        item_preview_indices=[1],
        filtered_indices=[1],
    )
    plan = ExecutionPlan(
        plan_id=ctx["plan_id"],
        user_id="synthetic-owner",
        steps=[
            ExecutionStep(
                step_id="s1",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name="delete_email_tool",
                for_each="$steps.get_emails.emails",
                for_each_max=2,
            )
        ],
    )
    if changed == "source":
        plan.steps[0].for_each = "$steps.get_emails.other_emails"
        ctx["pre_executed_steps"]["get_emails"]["other_emails"] = [
            {"id": "other-0"},
            {"id": "other-1"},
        ]
    elif changed == "provider":
        plan.steps[0].for_each = "$steps.other.emails"
        ctx["pre_executed_steps"]["other"] = {"emails": [{"id": "other-0"}, {"id": "other-1"}]}
    elif changed == "step":
        plan.steps[0].step_id = "other-step"
    elif changed == "tool":
        plan.steps[0].tool_name = "send_email_tool"
    elif changed == "missing_provider":
        ctx["pre_executed_steps"] = {}
    elif changed == "missing_path":
        ctx["pre_executed_steps"]["get_emails"] = {}
    elif changed == "not_list":
        ctx["pre_executed_steps"]["get_emails"]["emails"] = "not a list"
    else:
        ctx["pre_executed_steps"]["get_emails"]["emails"] = []
    with patch(
        "src.domains.agents.orchestration.parallel_executor.execute_plan_parallel", AsyncMock()
    ) as execute:
        await _handle_execution_plan(
            plan,
            {"messages": [], "current_turn_id": 1, STATE_KEY_FOR_EACH_HITL_CTX: ctx},
            "synthetic-run",
            {},
        )
    execute.assert_not_awaited()


@pytest.mark.parametrize("field_path", ["emails", "data.emails", "data.0.emails"])
async def test_nested_setter_never_replaces_a_different_source_revision(field_path) -> None:
    original = [{"id": "original"}]
    data = {
        "emails": {"emails": original},
        "data.emails": {"data": {"emails": original}},
        "data.0.emails": {"data": [{"emails": original}]},
    }[field_path]
    before = deepcopy(data)
    with pytest.raises(ValueError, match="Unproven filtered source path"):
        replace_filtered_source_items(data, field_path, deepcopy(original), [])
    assert data == before
    replace_filtered_source_items(data, field_path, original, [])
    assert extract_value_by_path(data, field_path) == []


@pytest.mark.parametrize(
    "completed",
    [{}, {"get_emails": {}}, {"get_emails": {"emails": "wrong"}}, {"get_emails": {"emails": []}}],
)
async def test_missing_filtered_source_cannot_fall_through_to_unfiltered_execution(
    completed,
) -> None:
    with pytest.raises(ValueError):
        apply_filtered_source_items(
            completed, {}, [{"for_each_source": "$steps.get_emails.emails"}], [0], "synthetic-run"
        )


@pytest.mark.parametrize("same_source", [False, True])
async def test_real_consumer_filters_multiple_steps_only_with_one_proven_source(
    same_source,
) -> None:
    steps = [
        {
            "step_id": "first",
            "tool_name": "delete_email_tool",
            "for_each_max": 2,
            "for_each_source": "$steps.get_1.emails",
        },
        {
            "step_id": "second",
            "tool_name": "delete_email_tool",
            "for_each_max": 2,
            "for_each_source": "$steps.get_1.emails" if same_source else "$steps.get_2.emails",
        },
    ]
    originals = [{"id": "A", "subject": "First"}, {"id": "B", "subject": "Selected"}]
    other = [{"id": "C", "subject": "Other first"}, {"id": "D", "subject": "Other second"}]
    ctx = {
        **_make_ctx(2),
        "steps": steps,
        "approved": True,
        "item_previews": [{"subject": "Selected"}],
        "item_preview_indices": [1],
        "filtered_indices": [1],
        "pre_executed_steps": {"get_1": {"emails": originals}, "get_2": {"emails": other}},
    }
    plan = ExecutionPlan(
        plan_id=ctx["plan_id"],
        user_id="synthetic-owner",
        steps=[
            ExecutionStep(
                step_id=step["step_id"],
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name=step["tool_name"],
                for_each=step["for_each_source"],
                for_each_max=2,
            )
            for step in steps
        ],
    )
    with patch(
        "src.domains.agents.orchestration.parallel_executor.execute_plan_parallel",
        AsyncMock(side_effect=RuntimeError("synthetic stop before any action")),
    ) as execute:
        await _handle_execution_plan(
            plan,
            {"messages": [], "current_turn_id": 1, STATE_KEY_FOR_EACH_HITL_CTX: ctx},
            "synthetic-run",
            {},
        )
    if same_source:
        execute.assert_awaited_once()
        assert execute.await_args.kwargs["initial_completed_steps"]["get_1"]["emails"] == [
            originals[1]
        ]
    else:
        execute.assert_not_awaited()
        assert resolve_item_preview_indices(ctx) is None
        assert ctx["pre_executed_steps"]["get_1"]["emails"] == originals
        with pytest.raises(ValueError, match="Ambiguous approved sources"):
            apply_filtered_source_items(ctx["pre_executed_steps"], {}, steps, [1], "synthetic-run")
    assert ctx["pre_executed_steps"]["get_2"]["emails"] == other


async def test_multiple_source_edited_checkpoint_cannot_be_approved() -> None:
    ctx = _make_ctx(2)
    ctx.update(
        item_previews=[{"subject": "item-1"}], item_preview_indices=[1], filtered_indices=[1]
    )
    ctx["steps"].append(
        {
            "step_id": "second",
            "tool_name": "delete_email_tool",
            "for_each_source": "$steps.other.emails",
        }
    )
    ctx["pre_executed_steps"]["other"] = {"emails": [{"id": "other", "subject": "Other"}]}
    graph = _build_graph()
    config = {"configurable": {"thread_id": "multi-source-reconfirm"}}
    await graph.ainvoke(_initial_input(ctx), config)
    pending = await graph.ainvoke(Command(resume={"decision": "APPROVE"}), config)
    assert _interrupt_payload(pending)
    assert pending[STATE_KEY_FOR_EACH_HITL_CTX]["approved"] is False
