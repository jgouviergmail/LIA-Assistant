"""Native execution evidence: checkpoints, isolated concurrent reads and fresh reuse."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.requested_outcomes import GoalRequirement
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.google_contacts.catalogue_manifests import get_contacts_catalogue_manifest
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes import react_nodes, react_read_reuse
from src.domains.agents.nodes.react_execution import pending_calls
from src.domains.agents.nodes.react_observed_gaps import observed_gaps, requested_coverage
from src.domains.agents.nodes.react_recovery import recovery_report, should_recover
from src.domains.agents.python_sandbox.catalogue_manifests import run_python_catalogue_manifest
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.services.outcome_evidence import (
    GoalCoverage,
    OutcomeStatus,
    coverage_has_gap,
)
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import get_tool, register_external_tool
from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skills.executor import ScriptResult, SkillScriptExecutor
from tests.unit.domains.agents.nodes.react_execution_harness import execution_graph, state_result

pytestmark = pytest.mark.unit
USER = UUID("11111111-2222-3333-4444-555555555555")


@dataclass
class Calls:
    seen: list[str] = field(default_factory=list)
    active: int = 0
    maximum: int = 0
    tool_name: str = "unknown_tool"
    delay: float = 0.01

    async def read(self, query: str = "Ada", force_refresh: bool = False) -> UnifiedToolOutput:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.seen.append(query)
        try:
            await asyncio.sleep(self.delay)
            return _contacts(query, self.tool_name)
        finally:
            self.active -= 1


def _contacts(query: str, tool_name: str = "unknown_tool") -> UnifiedToolOutput:
    fixture: dict[str, object] = {
        "resourceName": f"people/{query}",
        "names": [{"displayName": query}],
        "emailAddresses": [{"value": f"{query.lower()}@example.org"}],
        "addresses": [{"formattedValue": "12 rue de la Paix, Nancy, France"}],
    }
    builder = ToolOutputMixin()
    builder.tool_name = tool_name
    return builder.build_contacts_output([fixture], query=query)


def _register(
    coroutine: Callable[[str], Awaitable[UnifiedToolOutput]],
    *,
    safe: bool = True,
    ttl: int | None = 30,
    exclusive: str | None = None,
    mutation: bool = False,
) -> ToolManifest:
    name = f"get_semantic_probe_{uuid4().hex}_tool"
    tool = StructuredTool.from_function(
        coroutine=coroutine, name=name, description="native fixture"
    )
    register_external_tool(tool)
    return replace(
        get_contacts_catalogue_manifest,
        name=name,
        concurrency_safe=safe,
        result_reuse_ttl_seconds=ttl,
        exclusive_scope=exclusive,
        tool_category="update" if mutation else "search",
    )


def _call(manifest: ToolManifest, call_id: str, query: str = "Ada") -> ToolCall:
    return {"name": manifest.name, "id": call_id, "args": {"query": query}, "type": "tool_call"}


def _state(*calls: ToolCall) -> MessagesState:
    state = create_initial_state(USER, session_id="fixture", run_id="fixture")
    state["messages"] = [AIMessage(content="", id="model-1", tool_calls=list(calls))]
    state["react_tool_names"] = list(dict.fromkeys(call["name"] for call in calls))
    state["react_hitl_map"] = dict.fromkeys(state["react_tool_names"], False)
    state["react_iteration"] = 1
    return state


def _context(thread: str = "fixture", user: UUID = USER) -> LiaRuntimeContext:
    return LiaRuntimeContext(
        user_id=user, thread_id=thread, conversation_id=thread, execution_mode="react"
    )


def _config(thread: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread}, "recursion_limit": 100}


def _assert_read_checkpoint(state: MessagesState, reads: Calls, writes: Calls) -> None:
    assert reads.seen == ["Ada", "Grace"]
    assert writes.seen == []
    assert [
        message.tool_call_id for message in state["messages"] if isinstance(message, ToolMessage)
    ] == ["r1", "r2"]
    assert len(state["react_read_results"]) == 2
    assert len(state["semantic_source_observations"]) == 2


def _assert_resumed_state(state: MessagesState, reads: Calls, writes: Calls) -> None:
    assert reads.seen == ["Ada", "Grace"]
    assert writes.seen == ["Done"]
    answers = [message for message in state["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in answers] == ["r1", "r2", "w1"]
    assert all(message.status == "success" for message in answers)
    assert state["react_read_results"] == {}, "a mutation must invalidate previous reads"
    assert state["semantic_source_observations"] == {}
    assert state["semantic_value_bindings"] == []
    assert state["semantic_source_valid_after"] is not None


@pytest.fixture(autouse=True)
def no_services(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def no_store() -> None:
        return None

    monkeypatch.setattr("src.domains.agents.context.store.get_tool_context_store", no_store)
    with treatment_collector():
        yield


@pytest.fixture
def contracts() -> Iterator[list[ToolManifest]]:
    manifests: list[ToolManifest] = []
    token = request_tool_manifests_ctx.set(manifests)
    try:
        yield manifests
    finally:
        request_tool_manifests_ctx.reset(token)


async def test_reads_are_checkpointed_before_approval_and_not_replayed_by_another_worker(
    contracts: list[ToolManifest],
) -> None:
    reads, writes = Calls(), Calls()
    read = _register(reads.read)
    reads.tool_name = read.name
    write = _register(writes.read, safe=False, ttl=None, mutation=True)
    contracts.extend([read, write])
    state = _state(_call(read, "r1", "Ada"), _call(read, "r2", "Grace"), _call(write, "w1", "Done"))
    state["react_hitl_map"][write.name] = True
    saver = InMemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
    )
    first_worker = execution_graph(saver)
    config, context = _config("resume"), _context("resume")

    await first_worker.ainvoke(state, config, context=context)
    saved = await first_worker.aget_state(config)
    _assert_read_checkpoint(state_result(saved.values), reads, writes)
    assert saved.tasks[0].interrupts

    # Recompile the graph, as a fresh worker does; only the serialized saver is shared.
    second_worker = execution_graph(saver)
    result = await second_worker.ainvoke(
        Command(resume={"action": "confirm"}), config, context=context
    )
    _assert_resumed_state(state_result(result), reads, writes)


def _assert_isolated_answers(answers: list[ToolMessage]) -> None:
    for index, answer in enumerate(answers):
        assert f"person{index}@example.org" in str(answer.content)
        assert all(
            f"person{other}@example.org" not in str(answer.content)
            for other in range(len(answers))
            if other != index
        )


async def test_parallel_reads_are_bounded_and_each_call_keeps_its_own_registry(
    contracts: list[ToolManifest],
) -> None:
    monitor = Calls()
    read = _register(monitor.read)
    contracts.append(read)
    state = _state(*(_call(read, f"c{i}", f"Person{i}") for i in range(9)))
    result = await execution_graph().ainvoke(state, context=_context())

    assert monitor.maximum == 4
    assert len(monitor.seen) == 9
    answers = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in answers] == [f"c{i}" for i in range(9)]
    _assert_isolated_answers(answers)
    assert len(result["registry"]) == 9
    assert result["react_productive_iterations"] == 1, "segments do not buy multiple iterations"


@pytest.mark.parametrize(
    "exclusive,mutation,safe",
    [("browser_session", False, True), (None, True, True), (None, False, False)],
)
async def test_exclusive_unknown_and_mutating_calls_remain_serial(
    contracts: list[ToolManifest],
    exclusive: str | None,
    mutation: bool,
    safe: bool,
) -> None:
    monitor = Calls()
    read = _register(monitor.read, exclusive=exclusive, mutation=mutation, safe=safe)
    contracts.append(read)
    await execution_graph().ainvoke(
        _state(_call(read, "c1", "Ada"), _call(read, "c2", "Grace")), context=_context()
    )
    assert monitor.maximum == 1
    assert monitor.seen == ["Ada", "Grace"]


async def test_exact_reads_reuse_fresh_data_without_buying_progress(
    contracts: list[ToolManifest],
) -> None:
    monitor = Calls()
    read = _register(monitor.read)
    contracts.append(read)
    result = await execution_graph().ainvoke(
        _state(_call(read, "c1"), _call(read, "c2")), context=_context()
    )
    answers = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert monitor.seen == ["Ada"]
    assert [message.tool_call_id for message in answers] == ["c1", "c2"]
    assert answers[0].content == answers[1].content
    assert result["react_productive_iterations"] == 1
    assert len(result["react_read_observations"]) == 1
    assert result["requested_outcome_evidence"] == [], "no explicit goal duplicates no payload"


@pytest.mark.parametrize("changed", ["expired", "account", "schema", "refresh"])
async def test_stale_other_account_other_schema_and_refresh_reads_are_not_reused(
    contracts: list[ToolManifest],
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(react_read_reuse.time, "time", lambda: clock[0])
    monitor = Calls()
    read = _register(monitor.read)
    contracts.append(read)
    graph = execution_graph()
    first = await graph.ainvoke(_state(_call(read, "c1")), context=_context())
    state = _state(_call(read, "c2"))
    state["react_read_results"] = first["react_read_results"]
    context = _context()
    if changed == "expired":
        clock[0] += 31
    elif changed == "account":
        context = _context(user=uuid4())
    elif changed == "schema":
        # A new public schema under the same name must not share an old signature.
        async def new_read(query: str = "Ada", detail: str = "full") -> UnifiedToolOutput:
            return await monitor.read(query)

        replacement = StructuredTool.from_function(
            coroutine=new_read, name=read.name, description="changed schema"
        )
        registered = get_tool(read.name)
        assert registered is not None
        monkeypatch.setattr(registered, "args_schema", replacement.args_schema)
    else:
        state["messages"] = [
            AIMessage(
                content="",
                tool_calls=[{**_call(read, "c2"), "args": {"query": "Ada", "force_refresh": True}}],
            )
        ]
    await graph.ainvoke(state, context=context)
    assert monitor.seen == ["Ada", "Ada"]


async def _partial_failure_response(query: str = "Ada") -> UnifiedToolOutput:
    if query == "timeout":
        await asyncio.sleep(1)
    if query == "error":
        raise RuntimeError("fixture unavailable")
    result = _contacts(query)
    if query == "partial":
        result.metadata["partial"] = True
    return result


async def test_failures_partial_and_timeout_do_not_hide_successful_siblings(
    contracts: list[ToolManifest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _register(_partial_failure_response)
    contracts.append(read)
    monkeypatch.setattr(react_nodes, "compute_step_timeout", lambda _name, _bound: 0.03)
    result = await execution_graph().ainvoke(
        _state(*(_call(read, kind, kind) for kind in ("Ada", "error", "partial", "timeout"))),
        context=_context(),
    )
    answers = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.status for message in answers] == ["success", "error", "success", "error"]
    assert "ada@example.org" in str(answers[0].content)
    assert len(result["registry"]) == 2
    assert len(result["react_read_results"]) == 1
    assert sorted(item["outcome"] for item in result["react_read_observations"].values()) == [
        "failed",
        "failed",
        "obtained",
        "partial",
    ]


def test_observed_failure_survives_a_final_message_that_drops_its_gap() -> None:
    state = _state()
    state["messages"] = [
        ToolMessage("unavailable", tool_call_id="c1", id="t1", status="error"),
        AIMessage("Done.", id="final"),
    ]
    state["react_read_observations"] = {
        "signature": {"tool_name": "get_emails_tool", "signature": "signature", "outcome": "failed"}
    }
    assert observed_gaps(state)
    assert should_recover(state)
    state["react_recovery_passes"] = [
        {"anchor_id": "t1", "draft": "Earlier.", "unresolved": ["email"]}
    ]
    report = recovery_report(state, state["messages"][-1], cut=False)
    assert report["recovery"]["outcome"] == "still_unresolved"


def test_a_page_cut_at_the_tool_s_cap_is_not_an_observed_gap() -> None:
    """A read the tool cut at its cap — ``truncated``, a next page — answered what
    it was asked, and the cut is already stated to the model (ADR-286). Counted as a
    gap, it forced a recovery pass the model could not resolve: 4 dev turns of 4 and
    21 production turns of 65 on 2026-10-12, 14 of them fruitless, two model calls
    and 10 to 15 s each. Only a read that FAILED is an observed gap; a goal that
    demands completeness keeps its own ``partial`` verdict (``requested_coverage``)."""
    state = _state()
    state["messages"] = [
        ToolMessage("25 events (cut at the cap)", tool_call_id="c1", id="t1"),
        AIMessage("Here are your meetings.", id="final"),
    ]
    state["react_read_observations"] = {
        "signature": {
            "tool_name": "get_events_tool",
            "signature": "signature",
            "outcome": "partial",
        }
    }
    assert observed_gaps(state) == ()
    assert not should_recover(state)
    state["react_recovery_passes"] = [
        {"anchor_id": "t1", "draft": "Earlier.", "unresolved": ["a declared fact"]}
    ]
    report = recovery_report(state, state["messages"][-1], cut=False)
    assert report["recovery"]["outcome"] == "resolved"


def test_an_empty_read_does_not_invent_a_missing_objective() -> None:
    state = _state()
    state["react_read_observations"] = {
        "signature": {"tool_name": "get_events_tool", "signature": "signature", "outcome": "empty"}
    }
    assert not observed_gaps(state)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("satisfied", False),
        ("missing", True),
        ("failed", True),
        ("partial", True),
        ("pending_confirmation", False),
        ("unknown", False),
    ],
)
def test_requested_goal_status_has_its_own_closed_gap_vocabulary(
    status: OutcomeStatus, expected: bool
) -> None:
    goal = GoalRequirement(domain="contact", label="Ada", source_quote="Ada")
    assert coverage_has_gap(GoalCoverage(requirement=goal, status=status)) is expected


def test_native_read_sidecars_preserve_exact_values_with_production_checkpoint_serializer() -> None:
    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
    original = {
        "react_read_results": {
            "hmac": {"content": "canonical reply", "registry": {}, "expires_at": 1234567.5}
        },
        "react_read_observations": {
            "hmac": {"tool_name": "get_contacts_tool", "signature": "hmac", "outcome": "obtained"}
        },
        "semantic_source_valid_after": "2026-10-06T19:00:00+00:00",
    }
    restored = serde.loads_typed(serde.dumps_typed(original))
    assert restored == original


@pytest.mark.parametrize(
    "marker",
    [{"has_more": True}, {"nextPageToken": "next"}, {"complete": False}, {"truncated": True}],
)
def test_explicit_incomplete_reads_are_not_cacheable(marker: dict[str, object]) -> None:
    assert react_read_reuse.read_evidence({"success": True, "data": {"items": [1], **marker}}) == {
        "outcome": "partial"
    }


def _requested_state(call: ToolCall, goal: GoalRequirement) -> MessagesState:
    state = _state(call)
    state["query_intelligence"] = {
        "original_query": goal.source_quote,
        "domains": [goal.domain],
        "requested_outcomes": [goal.model_dump(mode="json")],
    }
    return state


@pytest.mark.parametrize(
    "empty,minimum,expected",
    [(False, 1, "satisfied"), (True, 1, "missing"), (True, None, "satisfied")],
)
async def test_actual_read_callback_and_finalize_follow_requested_counts(
    contracts: list[ToolManifest], empty: bool, minimum: int | None, expected: str
) -> None:
    async def response(query: str = "Ada") -> UnifiedToolOutput:
        if empty:
            return ToolOutputMixin().build_contacts_output([], query=query)
        return _contacts(query)

    read = _register(response)
    contracts.append(read)
    goal = GoalRequirement(
        domain="contact",
        label="contacts",
        source_quote="trouve 1 contact Ada",
        collection_key="contacts",
        min_count=minimum,
    )
    result = _requested_state(_call(read, "c1"), goal)
    result = state_result(await execution_graph().ainvoke(result, context=_context()))
    assert len(result["requested_outcome_evidence"]) == 1
    assert requested_coverage(result)[0].status == expected
    result["messages"].append(AIMessage("Completed.", id="final"))
    finalized = await react_nodes.react_finalize_node(result, {})
    final = finalized["react_agent_result"]
    assert isinstance(final, dict)
    assert final["final_message"] == ("" if expected == "missing" else "Completed.")
    assert should_recover(result) is (expected == "missing")


async def test_actual_partial_read_and_exception_are_factual_gaps(
    contracts: list[ToolManifest],
) -> None:
    async def response(query: str = "Ada") -> UnifiedToolOutput:
        if query == "error":
            raise RuntimeError("provider failed")
        result = _contacts(query)
        result.metadata["partial"] = True
        return result

    read = _register(response)
    contracts.append(read)
    goal = GoalRequirement(
        domain="contact",
        label="complete contacts",
        source_quote="trouve tous les contacts",
        collection_key="contacts",
        requires_complete=True,
    )
    for query, expected in (("Ada", "partial"), ("error", "failed")):
        result = _requested_state(_call(read, "c1", query), goal)
        result = state_result(await execution_graph().ainvoke(result, context=_context()))
        assert requested_coverage(result)[0].status == expected
        assert observed_gaps(result)


async def test_cached_read_reuses_compact_goal_proof_without_duplicate_observation(
    contracts: list[ToolManifest],
) -> None:
    monitor = Calls()
    read = _register(monitor.read)
    contracts.append(read)
    goal = GoalRequirement(
        domain="contact",
        label="Ada contact",
        source_quote="trouve 1 contact Ada",
        collection_key="contacts",
        min_count=1,
    )
    state = _requested_state(_call(read, "c1"), goal)
    state["messages"] = [
        AIMessage("", id="model", tool_calls=[_call(read, "c1"), _call(read, "c2")])
    ]
    state = state_result(await execution_graph().ainvoke(state, context=_context()))
    assert monitor.seen == ["Ada"]
    assert requested_coverage(state)[0].status == "satisfied"
    assert len(state["requested_outcome_evidence"]) == 1
    evidence = state["requested_outcome_evidence"][0]
    assert evidence["arguments"] == {}
    assert evidence["data"] == {}
    assert len(state["registry"]) == 1, "canonical payload remains available"


async def test_actual_pending_draft_does_not_trigger_recovery_or_repeat_action(
    contracts: list[ToolManifest],
) -> None:
    attempted: list[str] = []

    async def stage(query: str = "Ada") -> UnifiedToolOutput:
        attempted.append(query)
        return UnifiedToolOutput.action_success(
            message="Contact draft prepared",
            structured_data={"draft_id": "draft-fixture"},
            metadata={
                "requires_confirmation": True,
                "draft_id": "draft-fixture",
                "draft_type": "contact",
            },
        )

    write = _register(stage, mutation=True, safe=False, ttl=None)
    contracts.append(write)
    goal = GoalRequirement(
        domain="contact",
        label="update Ada",
        source_quote="modifie le contact Ada",
        kind="action",
        operation="update",
    )
    state = _requested_state(_call(write, "w1"), goal)
    state = state_result(await execution_graph().ainvoke(state, context=_context()))
    assert attempted == ["Ada"]
    assert requested_coverage(state)[0].status == "pending_confirmation"
    assert not observed_gaps(state)
    assert not should_recover(state)
    assert state["pending_draft_critique"] is not None


async def test_recovery_reads_only_and_preserves_completed_results(
    contracts: list[ToolManifest],
) -> None:
    monitor, actions = Calls(), Calls()
    read = _register(monitor.read)
    write = _register(actions.read, mutation=True, safe=False, ttl=None)
    contracts.extend([read, write])
    graph = execution_graph()
    saved = _state(_call(read, "r1"))
    saved = state_result(await graph.ainvoke(saved, context=_context()))
    saved["messages"].append(
        AIMessage("", id="recovery", tool_calls=[_call(write, "w1"), _call(read, "r2", "Grace")])
    )
    saved["react_recovery_passes"] = [
        {"anchor_id": "r1", "draft": "Ada found", "unresolved": ["another contact"]}
    ]
    result = await graph.ainvoke(saved, context=_context())
    assert actions.seen == []
    assert monitor.seen == ["Ada", "Grace"]
    assert len(result["registry"]) == 2
    answers = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    blocked = next(message for message in answers if message.tool_call_id == "w1")
    assert blocked.artifact is not None
    assert "not executed" in str(blocked.content)
    assert result["semantic_source_valid_after"] is None


async def test_delegated_budget_stops_between_segments_and_closes_pending_calls(
    contracts: list[ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monitor = Calls()
    read = _register(monitor.read)
    contracts.append(read)
    monkeypatch.setattr("src.core.config.settings.react_tool_budget_seconds", 0.001)
    result = _state(*(_call(read, f"c{i}", f"Person{i}") for i in range(5)))
    result = state_result(await execution_graph().ainvoke(result, context=_context()))
    assert len(monitor.seen) == 4
    assert pending_calls(result)[1][0]["id"] == "c4"
    finalized = await react_nodes.react_finalize_node(result, {})
    details = finalized["react_agent_result"]
    assert isinstance(details, dict)
    assert details["final_message"] == ""
    assert details["truncation"]["reason"] == "tool_budget"
    abandoned = finalized["messages"]
    assert isinstance(abandoned, list)
    assert [item.tool_call_id for item in abandoned] == ["c4"]
    assert all(item.status == "error" for item in abandoned)


async def test_sources_come_from_real_registry_leaves_and_survive_checkpoint(
    contracts: list[ToolManifest],
) -> None:
    monitor = Calls()
    read = _register(monitor.read)
    monitor.tool_name = read.name
    contracts.append(read)
    saver = InMemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
    )
    graph = execution_graph(saver)
    await graph.ainvoke(_state(_call(read, "c1")), _config("sources"), context=_context("sources"))
    checkpoint = await graph.aget_state(_config("sources"))
    sources = checkpoint.values["semantic_source_observations"]
    assert len(sources) == 1
    source = next(iter(sources.values()))
    assert source["account_id"] == str(USER)
    assert source["entity_type"] == "Contact"
    assert source["predicate"] == "address"
    assert source["value"] == "12 rue de la Paix, Nancy, France"
    assert source["status"] == "present"
    assert source["source_ref"].endswith(".addresses[0].formattedValue")


def test_earlier_tool_call_ids_do_not_answer_a_later_generation() -> None:
    state = _state()
    state["messages"] = [
        AIMessage(
            "",
            id="old",
            tool_calls=[{"name": "read", "id": "same", "args": {}, "type": "tool_call"}],
        ),
        ToolMessage("old answer", tool_call_id="same"),
        AIMessage(
            "",
            id="new",
            tool_calls=[{"name": "read", "id": "same", "args": {}, "type": "tool_call"}],
        ),
    ]
    request, calls = pending_calls(state)
    assert request is state["messages"][-1]
    assert [call["id"] for call in calls] == ["same"]


def _registry_payloads(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    payloads: dict[str, object] = {}
    for key, item in value.items():
        assert isinstance(key, str) and isinstance(item, RegistryItem)
        payloads[key] = item.payload
    return payloads


async def test_parallel_policy_comparison_keeps_calls_and_canonical_outputs_equal(
    contracts: list[ToolManifest],
) -> None:
    timings: dict[str, object] = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "fixture_delay_seconds": 0.05,
        "item_count": 8,
    }
    snapshots: list[dict[str, object]] = []
    for safe in (False, True):
        monitor = Calls(delay=0.05)
        read = _register(monitor.read, safe=safe)
        contracts.append(read)
        started = time.perf_counter()
        result = await execution_graph().ainvoke(
            _state(*(_call(read, f"c{i}", f"Person{i}") for i in range(8))), context=_context()
        )
        timings["parallel" if safe else "serial"] = {
            "seconds": round(time.perf_counter() - started, 4),
            "calls": len(monitor.seen),
            "maximum_concurrency": monitor.maximum,
        }
        assert monitor.seen == [f"Person{i}" for i in range(8)]
        assert monitor.maximum == (4 if safe else 1)
        snapshots.append(_registry_payloads(result["registry"]))
    assert snapshots[0] == snapshots[1]
    print("native_execution_comparison=" + json.dumps(timings))


async def test_python_receives_canonical_json_and_its_budget_survives_new_graph_worker(
    contracts: list[ToolManifest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    captured: list[dict[str, object]] = []

    async def enabled(_capability: PlatformCapability) -> bool:
        return True

    async def container(**kwargs: object) -> ScriptResult:
        stdin = kwargs["stdin_payload"]
        assert isinstance(stdin, str)
        captured.append(json.loads(stdin))
        return ScriptResult(success=True, output="3\n", execution_started=True)

    monkeypatch.setattr("src.domains.feature_switches.registry.is_capability_enabled", enabled)
    monkeypatch.setattr(SkillScriptExecutor, "_run_source_in_container", staticmethod(container))
    monkeypatch.setattr(settings, "skills_script_sandbox", "container")
    monkeypatch.setattr(settings, "python_sandbox_max_runs_per_turn", 2)
    contracts.append(run_python_catalogue_manifest)
    name = run_python_catalogue_manifest.name
    calls: list[ToolCall] = [
        {
            "name": name,
            "id": f"p{i}",
            "args": {"code": f"print({i})", "purpose": "compute actual collected contacts"},
            "type": "tool_call",
        }
        for i in range(3)
    ]
    state = _state(calls[0])
    state["current_turn_registry"] = _contacts("Ada").registry_updates
    state = state_result(await execution_graph().ainvoke(state, context=_context()))
    assert state["react_script_runs"] == 1
    state["messages"].append(AIMessage("", id="new-worker", tool_calls=calls[1:]))
    result = state_result(await execution_graph().ainvoke(state, context=_context()))
    _assert_python_data_and_budget(result, captured)


def _assert_python_data_and_budget(state: MessagesState, captured: list[dict[str, object]]) -> None:
    assert len(captured) == 2, "the third script never reaches the container seam"
    items = captured[0]["items"]
    assert isinstance(items, dict)
    record = next(iter(items.values()))
    assert isinstance(record, dict), "RegistryItem must not become a repr string on stdin"
    assert record["payload"]["names"][0]["displayName"] == "Ada"
    assert state["react_script_runs"] == 2
    assert len(state["react_scripts"]) == 2
    answers = [message for message in state["messages"] if isinstance(message, ToolMessage)]
    assert [answer.status for answer in answers] == ["success", "success", "error"]
