"""The graph receives what a turn changed, never the whole restored state.

Measured 2026-10-12 on production: the loader restored the checkpoint's values,
shaped them for the turn and passed them WHOLE as the graph input, so every
channel took a new version on every turn — ``agent_results`` (600 KB) and
``registry`` (350 KB) rewritten unchanged, a ``__start__`` blob of about 1 MB
per turn, ~40 checkpoint saves of 1 MB and more per ReAct turn at p50 51 ms and
p90 187 ms, 1.9 GB of blobs. The diff is derived from a deep snapshot of the
restored values, so a writer that runs after the loader (the chat service sets
``plan_approved``) and an in-place mutation (the turn's attachments popped from
``metadata``) are both seen. What the model reads is untouched: the graph's state
stays complete, only what travels to the database between two nodes shrinks.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.services.orchestration.turn_input import (
    LOADED_SNAPSHOT_KEY,
    appended_messages,
    prepare_graph_input,
    snapshot_loaded_state,
    snapshot_restored_state,
    turn_input,
)

pytestmark = pytest.mark.unit


def _restored() -> dict[str, Any]:
    return {
        "messages": [HumanMessage("q1", id="h1"), AIMessage("a1", id="a1")],
        "current_turn_id": 1,
        "user_timezone": "UTC",
        "oauth_scopes": ["calendar"],
        "agent_results": {"step_1:x": {"big": "payload"}},
        "metadata": {"current_turn_attachments": ["f1"], "kept": True},
        "_schema_version": "1.4",
    }


class TestTheDiff:
    def test_without_a_snapshot_the_whole_state_travels(self) -> None:
        state = _restored()
        assert turn_input(state, None) is state

    def test_an_unchanged_key_does_not_travel(self) -> None:
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored["current_turn_id"] = 2
        shaped = turn_input(restored, snapshot)
        assert "agent_results" not in shaped
        assert "oauth_scopes" not in shaped
        assert shaped["current_turn_id"] == 2

    def test_only_the_appended_messages_travel(self) -> None:
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored["messages"].append(AIMessage("notification", id="n1"))
        restored["messages"].append(HumanMessage("q2"))
        shaped = turn_input(restored, snapshot)
        assert [m.content for m in shaped["messages"]] == ["notification", "q2"]

    def test_a_changed_prefix_sends_the_whole_list(self) -> None:
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored["messages"][0] = HumanMessage("edited", id="h1")
        restored["messages"].append(HumanMessage("q2"))
        assert len(turn_input(restored, snapshot)["messages"]) == 3

    def test_an_in_place_nested_mutation_is_seen(self) -> None:
        # The loader pops the previous turn's attachments from ``metadata``
        # without reassigning it: a shallow snapshot would miss it.
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored["metadata"].pop("current_turn_attachments")
        assert turn_input(restored, snapshot)["metadata"] == {"kept": True}

    def test_a_key_a_later_writer_sets_travels(self) -> None:
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored["plan_approved"] = True  # set by the chat service after the loader
        restored["_schema_version"] = "1.5"  # set by a schema migration
        shaped = turn_input(restored, snapshot)
        assert shaped["plan_approved"] is True
        assert shaped["_schema_version"] == "1.5"

    def test_the_snapshot_key_never_travels(self) -> None:
        restored = _restored()
        snapshot = snapshot_loaded_state(restored)
        restored[LOADED_SNAPSHOT_KEY] = snapshot
        restored["current_turn_id"] = 2
        assert LOADED_SNAPSHOT_KEY not in turn_input(restored, snapshot)

    def test_appended_messages_reads_the_tail_or_nothing(self) -> None:
        base = [HumanMessage("a", id="1")]
        assert appended_messages(base, base) == []
        assert appended_messages(base, [*base, AIMessage("b", id="2")]) == [AIMessage("b", id="2")]
        assert appended_messages(base, []) is None


# ---------------------------------------------------------------------------
# A real graph, an in-memory checkpointer: same final state, fewer rewrites
# ---------------------------------------------------------------------------


async def _noop(state: MessagesState) -> dict[str, Any]:
    return {}


def _graph():
    builder = StateGraph(MessagesState)
    builder.add_node("noop", _noop)
    builder.add_edge(START, "noop")
    builder.add_edge("noop", END)
    return builder.compile(checkpointer=InMemorySaver())


_USER = uuid.UUID(int=7)


def _initial() -> MessagesState:
    state = create_initial_state(
        _USER, "session", "run-1", user_timezone="UTC", oauth_scopes=["calendar"]
    )
    state["messages"] = [HumanMessage("q1", id="h1")]
    state["agent_results"] = {"step_1:x": {"big": "payload"}}
    return state


async def _second_turn(graph, thread: str, *, delta: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Turn 1 with the whole initial state; turn 2 shaped as the loader shapes it."""
    config = {"configurable": {"thread_id": thread}}
    await graph.ainvoke(_initial(), config)
    first = (await graph.aget_state(config)).values
    before = graph.checkpointer.get_tuple(config).checkpoint["channel_versions"]
    restored = dict(first)
    snapshot = snapshot_loaded_state(restored) if delta else None
    restored["messages"] = [*restored["messages"], HumanMessage("q2", id="h2")]
    restored["current_turn_id"] = restored.get("current_turn_id", 0) + 1
    restored["user_timezone"] = "UTC"
    await graph.ainvoke(turn_input(restored, snapshot), config)
    final = (await graph.aget_state(config)).values
    after = graph.checkpointer.get_tuple(config).checkpoint["channel_versions"]
    bumped = {key: after.get(key) != before.get(key) for key in before}
    return final, bumped


class TestOnARealGraph:
    async def test_the_final_state_is_the_same_either_way(self) -> None:
        full, _ = await _second_turn(_graph(), "full", delta=False)
        delta, _ = await _second_turn(_graph(), "delta", delta=True)
        assert [m.content for m in delta["messages"]] == ["q1", "q2"]
        assert {k: v for k, v in delta.items() if k != "messages"} == {
            k: v for k, v in full.items() if k != "messages"
        }
        assert [m.content for m in full["messages"]] == [m.content for m in delta["messages"]]

    async def test_an_unchanged_channel_is_no_longer_rewritten(self) -> None:
        _, full = await _second_turn(_graph(), "full", delta=False)
        _, delta = await _second_turn(_graph(), "delta", delta=True)
        assert full["agent_results"] is True, "passed whole, the unchanged results took a version"
        assert delta["agent_results"] is False
        assert delta["oauth_scopes"] is False
        assert delta["messages"] is True and delta["current_turn_id"] is True


# ---------------------------------------------------------------------------
# The loader leaves the snapshot on the state it returns
# ---------------------------------------------------------------------------


class TestTheLoaderSnapshot:
    async def test_the_restored_values_are_copied_before_the_turn_shapes_them(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from src.domains.agents.models import CURRENT_SCHEMA_VERSION
        from src.domains.agents.services.orchestration.service import OrchestrationService

        restored = {
            **create_initial_state(_USER, "session", "run-0", user_timezone="UTC"),
            "messages": [HumanMessage("q1", id="h1"), AIMessage("a1", id="a1")],
            "current_turn_id": 1,
            "agent_results": {"step_1:x": {"big": "payload"}},
            "_schema_version": CURRENT_SCHEMA_VERSION,
        }
        restored["metadata"] = {**restored["metadata"], "current_turn_attachments": ["f1"]}
        graph = SimpleNamespace(
            aget_state=AsyncMock(
                return_value=SimpleNamespace(
                    values=restored, tasks=[], created_at="2026-10-12T10:00:00+00:00"
                )
            )
        )
        with patch.object(
            OrchestrationService, "_inject_proactive_messages", AsyncMock(return_value=0)
        ):
            state = await OrchestrationService().load_or_create_state(
                graph,
                uuid.uuid4(),
                "q2",
                _USER,
                "session",
                "run-1",
                "UTC",
                "fr",
                ["calendar", "gmail"],
            )

        snapshot = state[LOADED_SNAPSHOT_KEY]
        assert len(snapshot["messages"]) == 2 and len(state["messages"]) == 3
        assert snapshot["current_turn_id"] == 1 and state["current_turn_id"] == 2
        assert "current_turn_attachments" in snapshot["metadata"]
        assert "current_turn_attachments" not in state["metadata"]
        shaped = turn_input(state, snapshot)
        assert [m.content for m in shaped["messages"]] == ["q2"]
        assert shaped["current_turn_id"] == 2
        assert shaped["oauth_scopes"] == ["calendar", "gmail"]
        assert "agent_results" not in shaped and LOADED_SNAPSHOT_KEY not in shaped


# ---------------------------------------------------------------------------
# The two doors the services call
# ---------------------------------------------------------------------------


class TestTheServiceDoors:
    def test_the_snapshot_rides_on_the_state_and_its_cost_is_logged(self) -> None:
        from structlog.testing import capture_logs

        restored = _restored()
        with capture_logs() as logs:
            snapshot_restored_state(restored, "run-1")
        snapshot = restored[LOADED_SNAPSHOT_KEY]
        assert snapshot["current_turn_id"] == 1 and LOADED_SNAPSHOT_KEY not in snapshot
        taken = next(log for log in logs if log["event"] == "state_snapshot_taken")
        assert taken["key_count"] == 7 and taken["duration_ms"] >= 0

    def test_a_normal_turn_pops_the_snapshot_and_hands_the_diff(self) -> None:
        from structlog.testing import capture_logs

        restored = _restored()
        snapshot_restored_state(restored, "run-1")
        restored["current_turn_id"] = 2
        with capture_logs() as logs:
            shaped = prepare_graph_input(restored, "run-1", False)
        assert LOADED_SNAPSHOT_KEY not in restored
        assert shaped == {"current_turn_id": 2}
        prepared = next(log for log in logs if log["event"] == "graph_input_prepared")
        assert prepared["mode"] == "delta" and prepared["key_count"] == 1

    def test_a_resumption_only_drops_the_snapshot(self) -> None:
        from structlog.testing import capture_logs

        restored = _restored()
        snapshot_restored_state(restored, "run-1")
        with capture_logs() as logs:
            handed = prepare_graph_input(restored, "run-1", True)
        assert handed is restored and LOADED_SNAPSHOT_KEY not in restored
        assert not [log for log in logs if log["event"] == "graph_input_prepared"]

    def test_without_a_snapshot_the_whole_state_travels_and_says_so(self) -> None:
        from structlog.testing import capture_logs

        restored = _restored()
        with capture_logs() as logs:
            handed = prepare_graph_input(restored, "run-1", False)
        assert handed is restored
        prepared = next(log for log in logs if log["event"] == "graph_input_prepared")
        assert prepared["mode"] == "full"

    def test_a_value_the_copy_cannot_take_leaves_no_snapshot_and_never_fails(self) -> None:
        # An optimisation never breaks the turn: no snapshot, the whole state
        # travels as it always did, the failure logged by its type alone.
        from structlog.testing import capture_logs

        class _Uncopyable:
            def __deepcopy__(self, memo: dict[int, Any]) -> Any:
                raise RuntimeError("a handle")

        restored = {**_restored(), "handle": _Uncopyable()}
        with capture_logs() as logs:
            snapshot_restored_state(restored, "run-1")
        assert LOADED_SNAPSHOT_KEY not in restored
        failed = next(log for log in logs if log["event"] == "state_snapshot_failed")
        assert failed["error"] == "RuntimeError" and "a handle" not in str(failed)
        with capture_logs() as logs:
            assert prepare_graph_input(restored, "run-1", False) is restored
        assert next(log for log in logs if log["event"] == "graph_input_prepared")["mode"] == "full"


# ---------------------------------------------------------------------------
# A schema migration runs AFTER the snapshot: what it changed travels
# ---------------------------------------------------------------------------


class TestAMigratedTurn:
    def test_the_migration_keeps_the_snapshot_and_its_changes_travel(self) -> None:
        from src.domains.agents.models import (
            CURRENT_SCHEMA_VERSION,
            migrate_state_to_current,
            needs_migration,
        )

        restored = {**_restored(), "_schema_version": "1.0"}
        assert needs_migration(restored)
        snapshot_restored_state(restored, "run-1")
        migrated = migrate_state_to_current(restored)  # the loader rebinds ``state``
        assert LOADED_SNAPSHOT_KEY in migrated, "the migration dropped the loader's copy"
        shaped = prepare_graph_input(migrated, "run-1", False)
        assert shaped["_schema_version"] == CURRENT_SCHEMA_VERSION
        added = set(migrated) - set(_restored()) - {LOADED_SNAPSHOT_KEY}
        assert added and added <= set(shaped), "a key the migration added must be persisted"
        assert "agent_results" not in shaped and "messages" not in shaped
