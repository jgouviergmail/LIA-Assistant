"""The persisted execution trace mirrors what the live bubble showed (ADR-133 V2).

``TraceCapture`` accumulates the same ``execution_step`` chunks the frontend
turns into the live ⚙ trace, under the same rules (reset on ``router_decision``,
i18n-key-only labels, category whitelist, tail-keeping cap) so a reloaded trace
matches what the user saw during the run. The PII guard is structural: a step is
persisted ONLY as ``{emoji, i18n_key, category}`` — ``detail`` and reasoning
deltas never reach storage.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_EXECUTION_TRACE
from src.domains.agents.services.streaming.trace_capture import (
    ROUTER_SEED_STEP,
    TraceCapture,
    with_persisted_trace,
)


def _step_metadata(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "step_type": "node",
        "step_name": "planner",
        "emoji": "📋",
        "i18n_key": "planner_generation",
        "category": "system",
    }
    base.update(overrides)
    return base


class TestTraceCaptureAccumulation:
    def test_router_decision_resets_and_seeds_the_router_step(self) -> None:
        capture = TraceCapture(max_steps=100)
        capture.observe("execution_step", _step_metadata())

        capture.observe("router_decision", {"intention": "conversation"})

        assert capture.snapshot() == [ROUTER_SEED_STEP]

    def test_second_router_decision_discards_the_previous_turn(self) -> None:
        # HITL resumption re-enters through a fresh router_decision — the
        # persisted trace must cover the answering invocation only (ADR-133).
        capture = TraceCapture(max_steps=100)
        capture.observe("router_decision", None)
        capture.observe("execution_step", _step_metadata())

        capture.observe("router_decision", None)

        assert capture.snapshot() == [ROUTER_SEED_STEP]

    def test_appends_structured_step_with_i18n_key(self) -> None:
        capture = TraceCapture(max_steps=100)

        capture.observe("execution_step", _step_metadata())

        assert capture.snapshot() == [
            {"emoji": "📋", "i18n_key": "planner_generation", "category": "system"}
        ]

    def test_deduplicates_by_i18n_key_within_a_turn(self) -> None:
        # Mirrors the frontend ``emittedStepKeysRef`` early-return: a FOR_EACH
        # over N items shows ONE tool step live — the persisted trace must too.
        capture = TraceCapture(max_steps=100)

        capture.observe("execution_step", _step_metadata(i18n_key="get_contacts"))
        capture.observe("execution_step", _step_metadata(i18n_key="get_contacts"))
        capture.observe("execution_step", _step_metadata(i18n_key="planner_generation"))

        assert [step["i18n_key"] for step in capture.snapshot()] == [
            "get_contacts",
            "planner_generation",
        ]

    def test_router_node_step_never_duplicates_the_seed(self) -> None:
        # The router emits BOTH a router_decision chunk (seed) and an
        # updates-mode execution_step with i18n_key=router_decision — the
        # frontend pre-marks the key as seen at seed time; so do we.
        capture = TraceCapture(max_steps=100)
        capture.observe("router_decision", None)

        capture.observe("execution_step", _step_metadata(i18n_key="router_decision"))

        assert capture.snapshot() == [ROUTER_SEED_STEP]

    def test_router_decision_reset_clears_the_seen_keys(self) -> None:
        capture = TraceCapture(max_steps=100)
        capture.observe("router_decision", None)
        capture.observe("execution_step", _step_metadata(i18n_key="get_contacts"))

        capture.observe("router_decision", None)
        capture.observe("execution_step", _step_metadata(i18n_key="get_contacts"))

        assert [step["i18n_key"] for step in capture.snapshot()] == [
            "router_decision",
            "get_contacts",
        ]

    def test_emoji_defaults_and_category_whitelist(self) -> None:
        capture = TraceCapture(max_steps=100)

        capture.observe("execution_step", _step_metadata(emoji=None, category="nonsense"))
        capture.observe("execution_step", _step_metadata(i18n_key="get_contacts", category="tool"))

        assert capture.snapshot() == [
            {"emoji": "⚙️", "i18n_key": "planner_generation", "category": "system"},
            {"emoji": "📋", "i18n_key": "get_contacts", "category": "tool"},
        ]

    def test_skips_steps_without_i18n_key(self) -> None:
        # Compaction-style custom events carry step_type/step_label but no
        # i18n_key: unpersistable without shipping raw text (PII guard).
        capture = TraceCapture(max_steps=100)

        capture.observe("execution_step", {"step_type": "compaction", "step_label": "start"})

        assert capture.snapshot() == []

    def test_skips_reasoning_and_tool_error_sub_events(self) -> None:
        capture = TraceCapture(max_steps=100)

        capture.observe("execution_step", _step_metadata(step_type="reasoning", delta="thinking"))
        capture.observe(
            "execution_step",
            _step_metadata(step_type="tool_error", connector_type="google_gmail"),
        )

        assert capture.snapshot() == []

    def test_ignores_other_chunk_types_and_missing_metadata(self) -> None:
        capture = TraceCapture(max_steps=100)

        capture.observe("token", _step_metadata())
        capture.observe("done", None)
        capture.observe("execution_step", None)

        assert capture.snapshot() == []

    def test_cap_keeps_the_tail(self) -> None:
        # The tail is the most informative part of a long FOR_EACH run — same
        # choice as the frontend MAX_TRACE_STEPS cap.
        capture = TraceCapture(max_steps=3)
        capture.observe("router_decision", None)
        for index in range(5):
            capture.observe("execution_step", _step_metadata(i18n_key=f"step_{index}"))

        assert [step["i18n_key"] for step in capture.snapshot()] == [
            "step_2",
            "step_3",
            "step_4",
        ]

    def test_snapshot_is_a_defensive_copy(self) -> None:
        capture = TraceCapture(max_steps=100)
        capture.observe("execution_step", _step_metadata())

        snapshot = capture.snapshot()
        snapshot.clear()

        assert len(capture.snapshot()) == 1


class TestWithPersistedTrace:
    def test_empty_steps_return_the_same_object(self) -> None:
        metadata = {"run_id": "run-1"}

        result = with_persisted_trace(metadata, [], duration_ms=1200, run_id="run-1")

        assert result is metadata

    def test_attaches_steps_and_duration_as_a_new_dict(self) -> None:
        metadata = {"run_id": "run-1"}
        steps = [{"emoji": "📋", "i18n_key": "planner_generation", "category": "system"}]

        result = with_persisted_trace(metadata, steps, duration_ms=1200, run_id="run-1")

        assert result is not metadata
        assert metadata == {"run_id": "run-1"}  # input untouched (JSONB rule)
        assert result[FIELD_EXECUTION_TRACE] == {"steps": steps, "duration_ms": 1200}
        assert result["run_id"] == "run-1"

    def test_duration_is_optional(self) -> None:
        steps = [{"emoji": "⚙️", "i18n_key": "x", "category": "system"}]

        result = with_persisted_trace({}, steps, duration_ms=None, run_id="run-1")

        assert result[FIELD_EXECUTION_TRACE] == {"steps": steps, "duration_ms": None}
