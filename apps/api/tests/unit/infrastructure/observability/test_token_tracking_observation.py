"""The slot, the latency and the outcome reach the ledger."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.infrastructure.observability.error_taxonomy import LLM_FAILURE_KINDS, classify_llm_error


class _Tracker:
    """A tracker that records what it was told, nothing more."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_node_tokens(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _callback(tracker: _Tracker) -> Any:
    from src.infrastructure.observability.callbacks import TokenTrackingCallback

    return TokenTrackingCallback(tracker, "run-1")  # type: ignore[arg-type]


async def test_the_slot_travels_from_the_run_metadata() -> None:
    """``create_instrumented_config`` already puts ``llm_type`` there."""
    callback = _callback(_Tracker())
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [[]], run_id=run_id, metadata={"langgraph_node": "response", "llm_type": "response"}
    )
    assert callback._call_context[str(run_id)]["llm_type"] == "response"


async def test_a_missing_slot_is_none_not_a_guess() -> None:
    callback = _callback(_Tracker())
    run_id = uuid4()
    await callback.on_chat_model_start({}, [[]], run_id=run_id, metadata={})
    assert callback._call_context[str(run_id)]["llm_type"] is None


async def test_a_failed_call_records_status_and_kind() -> None:
    """A failure produces a zero-token row: the ledger must show it happened."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [[]], run_id=run_id, metadata={"langgraph_node": "response", "llm_type": "response"}
    )
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)

    assert len(tracker.calls) == 1
    recorded = tracker.calls[0]
    assert recorded["status"] == "error"
    assert recorded["failure_kind"] == "timeout"
    assert recorded["prompt_tokens"] == 0
    assert recorded["completion_tokens"] == 0
    assert recorded["llm_type"] == "response"
    assert recorded["node_name"] == "response"


async def test_an_error_is_recorded_once() -> None:
    """The same idempotency guard as ``on_llm_end`` — handlers can double-attach."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start({}, [[]], run_id=run_id, metadata={})
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)
    assert len(tracker.calls) == 1


async def test_an_error_after_a_success_does_not_double_record() -> None:
    """A run recorded on ``on_llm_end`` is never recorded again as a failure."""
    tracker = _Tracker()
    callback = _callback(tracker)
    run_id = uuid4()
    await callback.on_chat_model_start({}, [[]], run_id=run_id, metadata={})
    callback._recorded_llm_run_ids.add(str(run_id))
    await callback.on_llm_error(TimeoutError("timed out"), run_id=run_id)
    assert tracker.calls == []


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("x"), "timeout"),
        (ValueError("rate_limit exceeded"), "rate_limit"),
        (RuntimeError("something else"), "unknown"),
    ],
)
def test_the_taxonomy_is_the_one_the_metrics_already_use(
    error: BaseException, expected: str
) -> None:
    assert classify_llm_error(error) == expected
    assert expected in LLM_FAILURE_KINDS


def test_the_metrics_handler_delegates_to_the_shared_taxonomy() -> None:
    """One implementation: the label and the persisted column cannot diverge."""
    from src.infrastructure.observability.callbacks import MetricsCallbackHandler

    assert MetricsCallbackHandler._classify_llm_error(TimeoutError("x")) == classify_llm_error(
        TimeoutError("x")
    )


def test_every_kind_fits_the_column() -> None:
    """``failure_kind`` is ``String(32)``."""
    assert all(len(kind) <= 32 for kind in LLM_FAILURE_KINDS)


def test_the_classifier_can_only_return_a_declared_kind() -> None:
    """Read the function's own ``return`` statements, not a sample of inputs.

    The three parametrized cases above prove the classifier works; they cannot
    prove it never invents a kind. A branch returning ``"rate-limit"`` would
    ship a Prometheus label and a ``failure_kind`` value outside the closed
    set — invisible until a dashboard query silently matches nothing, and the
    same silent-fallback class ADR-085 exists to forbid.
    """
    import ast
    import inspect
    import textwrap

    from src.infrastructure.observability import error_taxonomy

    source = textwrap.dedent(inspect.getsource(error_taxonomy.classify_llm_error))
    returned = {
        node.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    assert returned, "no literal return found — the parser stopped guarding"
    assert returned <= LLM_FAILURE_KINDS, sorted(returned - LLM_FAILURE_KINDS)
