"""Known paid attempts survive failed/cancelled delivery without a second bill."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.proactive import tracking

pytestmark = pytest.mark.unit


def _paid(capture: TokenCaptureHandler) -> None:
    run_id = uuid4()
    response = AIMessage(
        content="reply",
        response_metadata={"model_name": "returned-model"},
        usage_metadata={
            "input_tokens": 20,
            "output_tokens": 5,
            "total_tokens": 25,
            "input_token_details": {"cache_read": 10},
        },
    )
    with patch("src.infrastructure.llm.token_capture.time", return_value=1000):
        capture.on_chat_model_start({}, [[]], run_id=run_id)
        capture.on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=response)]]), run_id=run_id
        )


@pytest.mark.parametrize("failure", [ValueError("invalid parse"), asyncio.CancelledError()])
async def test_paid_failure_is_once_and_original_exception_survives(failure: BaseException) -> None:
    capture = TokenCaptureHandler("requested-model")
    user_id = uuid4()
    bill = AsyncMock(return_value="logical-run")
    with patch.object(tracking, "track_proactive_tokens", bill):
        with pytest.raises(type(failure)) as raised:
            async with tracking.capture_spend_on_failure(
                capture,
                user_id=user_id,
                task_type="test",
                target_id="target",
                model_name="requested-model",
                source="user",
                run_id="logical-run",
            ):
                _paid(capture)
                # An unsuccessful second attempt reports no usage: no estimate.
                attempt = uuid4()
                capture.on_chat_model_start({}, [[]], run_id=attempt)
                capture.on_llm_error(RuntimeError("network"), run_id=attempt)
                raise failure
        assert raised.value is failure
        assert (
            await tracking.bill_captured_usage(
                capture,
                user_id=user_id,
                task_type="test",
                target_id="target",
                model_name="requested-model",
                source="user",
                run_id="logical-run",
            )
            is None
        )
    bill.assert_awaited_once()
    values = bill.await_args.kwargs
    assert values["run_id"] == "logical-run" and values["failed"] is True
    assert len(values["billing_records"]) == 1
    paid = values["billing_records"][0]
    assert paid.model_name == "returned-model" and paid.started_at == 1000
    assert (paid.tokens_in, paid.tokens_cache, paid.tokens_out) == (10, 10, 5)
    assert capture.accounting_handled


async def test_unknown_usage_does_not_create_a_bill() -> None:
    capture = TokenCaptureHandler("model")
    with patch.object(tracking, "track_proactive_tokens", new=AsyncMock()) as bill:
        with pytest.raises(RuntimeError):
            async with tracking.capture_spend_on_failure(
                capture,
                user_id=uuid4(),
                task_type="test",
                target_id="target",
                model_name="model",
                source="user",
            ):
                raise RuntimeError("failed before response")
    bill.assert_not_awaited()


async def test_repeated_cancel_waits_for_the_owned_bill_before_propagating() -> None:
    capture = TokenCaptureHandler("model")
    _paid(capture)
    started, release, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def persist(**kwargs):
        started.set()
        await release.wait()
        completed.set()
        return "logical-run"

    with patch.object(
        tracking, "track_proactive_tokens", new=AsyncMock(side_effect=persist)
    ) as bill:
        task = asyncio.create_task(
            tracking.bill_captured_usage(
                capture,
                user_id=uuid4(),
                task_type="test",
                target_id="target",
                model_name="model",
                source="user",
                run_id="logical-run",
            )
        )
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not completed.is_set() and not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert completed.is_set()
    bill.assert_awaited_once()
    assert capture.claim_billing_records("model") == ()


async def test_timeout_joins_the_cancelled_write(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = asyncio.Event()

    async def pending():
        try:
            await asyncio.Event().wait()
        finally:
            # The helper must join this cleanup before returning to its owner.
            await asyncio.sleep(0)
            closed.set()
        return "never"

    monkeypatch.setattr(tracking, "_BILLING_SETTLE_SECONDS", 0.01)
    assert await tracking.settle_known_billing(pending()) is None
    assert closed.is_set()


def test_direct_reply_seed_preserves_snapshot_and_never_adds_callback_usage() -> None:
    capture = TokenCaptureHandler("model")
    response = AIMessage(
        content="reply",
        response_metadata={"model_name": "returned"},
        usage_metadata={"input_tokens": 7, "output_tokens": 1, "total_tokens": 8},
    )
    capture.ensure_response_record(
        response,
        model_name="requested",
        started_at=1000,
        snapshot=capture_pricing_snapshot(),
    )
    capture.ensure_response_record(
        response,
        model_name="other",
        started_at=2000,
        snapshot=capture_pricing_snapshot(),
    )
    records = capture.get_billing_records("later-config")
    assert len(records) == 1 and records[0].tokens_in == 7
    assert records[0].model_name == "returned" and records[0].started_at == 1000
    callbacks = TokenCaptureHandler("requested")
    _paid(callbacks)
    callbacks.ensure_response_record(
        response,
        model_name="other",
        started_at=2000,
        snapshot=capture_pricing_snapshot(),
    )
    assert len(callbacks.get_billing_records("model")) == 1


async def test_funnel_itself_finishes_commit_before_cancellation() -> None:
    """Every direct-response caller inherits the same cancellation guarantee."""
    from src.domains.chat.service import TrackingContext

    started, release, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)

    async def commit():
        started.set()
        await release.wait()
        completed.set()

    tracker.commit = AsyncMock(side_effect=commit)
    with (
        patch("src.domains.chat.service.TrackingContext", return_value=tracker),
        patch.object(tracking, "_record_out_of_turn", new=AsyncMock()),
    ):
        task = asyncio.create_task(
            tracking.track_proactive_tokens(
                user_id=tracker.user_id,
                task_type="test",
                target_id="target",
                conversation_id=None,
                tokens_in=1,
                tokens_out=1,
                model_name="model",
                source="user",
                run_id=run_id,
                started_at=datetime(2026, 8, 17, tzinfo=UTC).timestamp(),
            )
        )
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    try:
        tracker.commit.assert_awaited_once()
        assert completed.is_set() and len(tracker._node_records) == 1
    finally:
        tracker.cleanup_run_records(run_id)


async def test_partial_stream_error_is_persisted_as_error_once() -> None:
    """The per-attempt error survives the shared background ledger bridge."""
    from src.domains.chat.service import TrackingContext

    capture = TokenCaptureHandler("requested-model")
    llm_run = uuid4()
    partial = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="partial",
                        response_metadata={"model_name": "returned-model"},
                        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )
                )
            ]
        ]
    )
    with patch("src.infrastructure.llm.token_capture.time", return_value=1000):
        capture.on_chat_model_start({}, [[]], run_id=llm_run)
        capture.on_llm_error(RuntimeError("stream failed"), run_id=llm_run, response=partial)
    run_id = str(uuid4())
    tracker = TrackingContext(run_id, uuid4(), "session", None, auto_commit=False)
    tracker.commit = AsyncMock()
    try:
        with (
            patch("src.domains.chat.service.TrackingContext", return_value=tracker),
            patch.object(tracking, "_record_out_of_turn", new=AsyncMock()) as decision,
        ):
            for _ in range(2):
                await tracking.bill_captured_usage(
                    capture,
                    user_id=tracker.user_id,
                    task_type="test",
                    target_id="target",
                    model_name="requested-model",
                    source="user",
                    run_id=run_id,
                    failed=True,
                )
        tracker.commit.assert_awaited_once()
        decision.assert_awaited_once()
        assert decision.await_args.kwargs["failed"] is True
        assert len(tracker._node_records) == 1
        row = tracker._node_records[0]
        assert row.status == "error" and row.failure_kind is not None
        assert (row.prompt_tokens, row.completion_tokens) == (10, 5)
        assert row.model_name == "returned-model"
        assert row.created_at == datetime.fromtimestamp(1000, UTC)
    finally:
        tracker.cleanup_run_records(run_id)
