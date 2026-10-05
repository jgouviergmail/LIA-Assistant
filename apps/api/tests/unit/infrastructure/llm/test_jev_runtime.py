"""Native calls respect OFF, quotas, usage isolation and paid failure accounting."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.infrastructure.llm import jev_runtime as module
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceBatchResult,
    ChoiceQuestion,
    ChoiceResult,
    DecisionUsage,
    TypeSafeError,
)

pytestmark = pytest.mark.unit
QUESTION = ChoiceQuestion(instructions="Select.", criteria={"a": "A", "none": "Unclear"})
PRICE = ModelPrice(
    "jev-1.13.0",
    Decimal(".042"),
    None,
    Decimal(0),
    "per_1m_tokens",
    datetime(2026, 9, 28, tzinfo=UTC),
)


@pytest.fixture(autouse=True)
def debug_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """These accounting tests use no debug DB; capture has its own integration tests."""
    monkeypatch.setattr(module, "begin_trace", AsyncMock(return_value=None))


async def test_off_makes_no_provider_or_quota_call() -> None:
    with (
        patch.object(
            module,
            "load_jev_snapshot",
            AsyncMock(return_value=JevSnapshot(False, "ready")),
            create=True,
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock(), create=True) as guard,
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose", AsyncMock()
        ) as provider,
    ):
        result = await module.choose_with_jev(
            usage=JevUsage.MEETING_TEMPLATE,
            user_id=uuid4(),
            run_id="meeting-test",
            state="x",
            question=QUESTION,
        )
    assert result.outcome == "disabled" and result.charge is None
    provider.assert_not_awaited()
    guard.assert_not_awaited()


@pytest.mark.parametrize("invalid", [False, True])
async def test_paid_result_is_recorded_once_with_its_own_model_and_tariff(invalid: bool) -> None:
    owner = uuid4()
    tracker = TrackingContext("meeting-native", owner, "meeting", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    usage = DecisionUsage(input_tokens=1000, output_tokens=20)
    result = ChoiceResult(
        config.model,
        ChoiceAnswer(
            type="choice", choice="a", confidence=0.99, probabilities={"a": 0.999, "none": 0.001}
        ),
        usage,
    )
    provider = (
        AsyncMock(
            side_effect=TypeSafeError(
                "invalid_response", usage=usage, model=config.model, reason="probability_sum"
            )
        )
        if invalid
        else AsyncMock(return_value=result)
    )
    with (
        patch.object(
            module,
            "load_jev_snapshot",
            AsyncMock(return_value=JevSnapshot(True, "ready", config)),
            create=True,
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock(), create=True) as guard,
        patch.object(module, "out_of_turn_spend", return_value=tracker, create=True),
        patch.object(module, "get_cached_usd_eur_rate", return_value=0.9, create=True),
        patch("src.infrastructure.llm.typesafe_client.TypeSafeClient.choose", provider),
        patch.object(module, "logger") as log,
    ):
        attempt = await module.choose_with_jev(
            usage=JevUsage.MEETING_TEMPLATE,
            user_id=owner,
            run_id="meeting-native",
            state="private-native-context",
            question=QUESTION,
        )
    guard.assert_awaited_once_with(owner, layer="jev_decision")
    assert attempt.charge is not None
    assert attempt.charge.cost_usd == pytest.approx(0.000042)
    assert attempt.charge.cost_eur == pytest.approx(0.0000378)
    calls = tracker.get_llm_calls_breakdown()
    assert len(calls) == 1
    assert calls[0]["model_name"] == "jev-1.13.0"
    assert calls[0]["call_type"] == "decision"
    assert calls[0]["status"] == ("error" if invalid else "success")
    assert (attempt.answer is None) is invalid
    log.info.assert_called_once()
    assert log.info.call_args.args == ("jev_decision_completed",)
    metadata = log.info.call_args.kwargs
    assert metadata["usage"] == JevUsage.MEETING_TEMPLATE.value
    assert metadata["outcome"] == ("invalid_response" if invalid else "success")
    assert metadata["invalid_response_reason"] == ("probability_sum" if invalid else None)
    assert metadata["input_tokens"] == 1000
    assert metadata["cost_eur"] == attempt.charge.cost_eur
    assert "private-native-context" not in str(metadata)
    assert "test-secret" not in str(metadata)
    assert "instructions" not in metadata and "probabilities" not in metadata


async def test_denied_quota_never_reaches_provider() -> None:
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    with (
        patch.object(
            module,
            "load_jev_snapshot",
            AsyncMock(return_value=JevSnapshot(True, "ready", config)),
            create=True,
        ),
        patch.object(
            module,
            "enforce_usage_limit",
            AsyncMock(side_effect=PermissionError("quota")),
            create=True,
        ),
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose", AsyncMock()
        ) as provider,
        pytest.raises(PermissionError, match="quota"),
    ):
        await module.choose_with_jev(
            usage=JevUsage.MEETING_TEMPLATE,
            user_id=uuid4(),
            run_id="meeting-native",
            state="x",
            question=QUESTION,
        )
    provider.assert_not_awaited()


async def test_native_call_joins_matching_chat_accounting_without_closing_it() -> None:
    owner = uuid4()
    parent = TrackingContext("chat-native", owner, "chat", None, auto_commit=False)
    isolated = TrackingContext("chat-native", owner, "native", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    reply = ChoiceResult(
        config.model,
        ChoiceAnswer(
            type="choice",
            choice="a",
            confidence=0.99,
            probabilities={"a": 0.999, "none": 0.001},
        ),
        DecisionUsage(input_tokens=1000, output_tokens=20),
    )
    with (
        patch.object(
            module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock()),
        patch.object(module, "out_of_turn_spend", return_value=isolated),
        patch.object(module, "get_cached_usd_eur_rate", return_value=0.9),
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose",
            AsyncMock(return_value=reply),
        ),
    ):
        async with parent:
            await module.choose_with_jev(
                usage=JevUsage.MEETING_TEMPLATE,
                user_id=owner,
                run_id="chat-native",
                state="x",
                question=QUESTION,
            )
            assert current_tracker.get() is parent
            assert len(parent.get_llm_calls_breakdown()) == 1
            assert parent.get_llm_calls_breakdown()[0]["cost_eur"] == pytest.approx(0.0000378)
    assert isolated.get_llm_calls_breakdown() == []


async def test_batch_cost_is_recorded_once_and_all_answers_reach_consumer() -> None:
    owner = uuid4()
    tracker = TrackingContext("batch", owner, "chat", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    answer = ChoiceAnswer(
        type="choice", choice="a", confidence=0.99, probabilities={"a": 0.999, "none": 0.001}
    )
    with (
        patch.object(
            module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock()),
        patch.object(module, "get_cached_usd_eur_rate", return_value=0.9),
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose_many",
            AsyncMock(
                return_value=ChoiceBatchResult(
                    config.model,
                    {"q0": answer, "q1": answer},
                    DecisionUsage(input_tokens=1000, output_tokens=40),
                )
            ),
        ),
    ):
        async with tracker:
            result = await module.choose_many_with_jev(
                usage=JevUsage.MEETING_TEMPLATE,
                user_id=owner,
                run_id="batch",
                state="x",
                questions={"q0": QUESTION, "q1": QUESTION},
            )
    assert set(result.answers) == {"q0", "q1"}
    calls = tracker.get_llm_calls_breakdown()
    assert len(calls) == 1
    assert calls[0]["cost_eur"] == pytest.approx(0.0000378)
    assert calls[0]["tokens_out"] == 40


async def test_cancellation_after_paid_response_does_not_drop_the_pending_charge() -> None:
    import asyncio

    owner = uuid4()
    tracker = TrackingContext("cancel-paid", owner, "chat", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    arrived = asyncio.Event()

    async def paid(**kwargs):
        arrived.set()
        return ChoiceResult(
            config.model,
            ChoiceAnswer(
                type="choice",
                choice="a",
                confidence=0.99,
                probabilities={"a": 0.999, "none": 0.001},
            ),
            DecisionUsage(input_tokens=100, output_tokens=2),
        )

    with (
        patch.object(
            module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock()),
        patch("src.infrastructure.llm.typesafe_client.TypeSafeClient.choose", side_effect=paid),
    ):
        async with tracker:
            await tracker._lock.acquire()
            task = asyncio.create_task(
                module.choose_with_jev(
                    usage=JevUsage.MEETING_TEMPLATE,
                    user_id=owner,
                    run_id="cancel-paid",
                    state="x",
                    question=QUESTION,
                )
            )
            try:
                await asyncio.wait_for(arrived.wait(), 0.5)
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
            finally:
                tracker._lock.release()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(tracker.get_llm_calls_breakdown()) == 1


@pytest.mark.parametrize("cancelled", [False, True])
async def test_client_close_cannot_erase_an_already_received_bill(cancelled: bool) -> None:
    import asyncio
    from contextlib import asynccontextmanager

    owner = uuid4()
    tracker = TrackingContext("close-paid", owner, "chat", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    error = asyncio.CancelledError if cancelled else OSError

    @asynccontextmanager
    async def closing_client():
        yield None  # The native inference is substituted below; only shutdown fails.
        raise error()

    reply = ChoiceResult(
        config.model,
        ChoiceAnswer(
            type="choice", choice="a", confidence=0.99, probabilities={"a": 0.999, "none": 0.001}
        ),
        DecisionUsage(input_tokens=100, output_tokens=2),
    )
    with (
        patch.object(
            module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock()),
        patch.object(module.httpx, "AsyncClient", closing_client),
        patch(
            "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose",
            AsyncMock(return_value=reply),
        ),
    ):
        async with tracker:
            with pytest.raises(error):
                await module.choose_with_jev(
                    usage=JevUsage.MEETING_TEMPLATE,
                    user_id=owner,
                    run_id="close-paid",
                    state="x",
                    question=QUESTION,
                )
            calls = tracker.get_llm_calls_breakdown()
            assert len(calls) == 1
            assert calls[0]["tokens_in"] == 100


@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize("invalid_answer", [False, True])
async def test_real_transport_stream_cleanup_accounts_received_usage_once(
    cancelled: bool, invalid_answer: bool
) -> None:
    import asyncio
    from contextlib import asynccontextmanager

    import httpx

    owner = uuid4()
    tracker = TrackingContext("stream-paid", owner, "chat", None, auto_commit=False)
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("test-secret"), PRICE)
    error = asyncio.CancelledError if cancelled else OSError
    http = httpx.AsyncClient()

    @asynccontextmanager
    async def closing_stream(*args, **kwargs):
        yield httpx.Response(
            200,
            json={
                "model": config.model,
                "answers": (
                    {}
                    if invalid_answer
                    else {
                        "selection": {
                            "type": "choice",
                            "choice": "a",
                            "confidence": 0.99,
                            "probabilities": {"a": 0.999, "none": 0.001},
                        }
                    }
                ),
                "usage": {"input_tokens": 321, "output_tokens": 18},
            },
        )
        raise error()

    with (
        patch.object(
            module, "load_jev_snapshot", AsyncMock(return_value=JevSnapshot(True, "ready", config))
        ),
        patch.object(module, "enforce_usage_limit", AsyncMock()),
        patch.object(module.httpx, "AsyncClient", return_value=http),
        patch.object(http, "stream", closing_stream),
    ):
        async with tracker:
            request = module.choose_with_jev(
                usage=JevUsage.MEETING_TEMPLATE,
                user_id=owner,
                run_id="stream-paid",
                state="Synthetic",
                question=QUESTION,
            )
            if cancelled:
                with pytest.raises(asyncio.CancelledError):
                    await request
            else:
                attempt = await request
                assert attempt.outcome == "transport_error" and attempt.answer is None
            calls = tracker.get_llm_calls_breakdown()
            assert len(calls) == 1
            assert calls[0]["tokens_in"] == 321
            assert calls[0]["tokens_out"] == 18
            assert calls[0]["status"] == "error"
            assert calls[0]["failure_kind"] == ("cancelled" if cancelled else "transport_error")
