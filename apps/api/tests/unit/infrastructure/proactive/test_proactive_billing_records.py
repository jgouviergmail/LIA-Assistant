"""Per-attempt model, cache buckets and frozen costs survive proactive composition."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.llm_usage import LLMBillingRecord
from src.domains.heartbeat import prompts as heartbeat_prompts
from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
from src.domains.interests.proactive_task import InterestProactiveTask
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.llm import token_capture
from src.infrastructure.proactive.base import ProactiveTaskResult
from src.infrastructure.proactive.runner import ProactiveTaskRunner, RunnerStats
from src.infrastructure.proactive.tracking import TokenAccumulator
from src.infrastructure.scheduler import reminder_notification
from src.infrastructure.scheduler.reminder_notification import (
    ReminderMessageResult,
    _account_reminder_spend,
)

pytestmark = pytest.mark.unit


def record(model: str, started: float, cost: float, *, cached: int = 0) -> LLMBillingRecord:
    return LLMBillingRecord(
        model_name=model,
        started_at=started,
        tokens_in=0 if cached else 10,
        tokens_out=0 if cached else 2,
        tokens_cache=cached,
        cost_usd=cost,
        cost_eur=cost * 0.9,
        usd_to_eur_rate=0.9,
    )


def runner() -> ProactiveTaskRunner:
    return ProactiveTaskRunner(SimpleNamespace(task_type="heartbeat"))


def test_runner_display_sums_frozen_attempts_without_reading_current_prices() -> None:
    records = (record("decision-model", 100.0, 0.02), record("message-model", 200.0, 0.08))
    result = ProactiveTaskResult(success=True, model_name="later-config", billing_records=records)
    with patch(
        "src.infrastructure.proactive.runner.get_cached_cost_usd_eur",
        side_effect=AssertionError("repriced"),
    ):
        cost = runner()._stamp_cost_metadata(result, "r", user_id="u")
    assert cost == pytest.approx(0.09)
    assert result.metadata["cost_eur"] == pytest.approx(0.09)
    assert result.billing_records == records


async def test_failed_cached_only_attempt_reaches_runner_funnel() -> None:
    records = (record("actual-response-model", 100.0, 0.02, cached=50),)
    result = ProactiveTaskResult(success=False, tokens_cache=50, billing_records=records)
    with patch(
        "src.infrastructure.proactive.runner.track_proactive_tokens", AsyncMock()
    ) as tracked:
        await runner()._bill(
            SimpleNamespace(id=uuid4()),
            result,
            SimpleNamespace(id="t"),
            "run",
            conversation_id=None,
            failed=True,
        )
    assert tracked.await_args.kwargs["billing_records"] == records
    assert tracked.await_args.kwargs["failed"] is True
    assert tracked.await_args.kwargs["tokens_cache"] == 50


async def test_heartbeat_keeps_decision_enrichment_and_message_records_distinct() -> None:
    decision_record = record("decision-model", 100.0, 0.01)
    enrich_record = record("enrichment-model", 110.0, 0.02, cached=15)
    message_record = record("message-model", 120.0, 0.04)
    target = HeartbeatTarget(
        context=HeartbeatContext(),
        decision=HeartbeatDecision(
            action="notify", reason="useful", message_draft="draft", interest_topic="Topic"
        ),
        decision_tokens_in=10,
        decision_tokens_out=2,
        billing_records=(decision_record,),
    )
    task = HeartbeatProactiveTask()
    with (
        patch.object(task, "_get_user_personality", AsyncMock(return_value=None)),
        patch.object(
            task,
            "_fetch_interest_facts",
            AsyncMock(return_value=("facts", [], 0, 0, 15, 0, (enrich_record,))),
        ),
        patch(
            "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
            AsyncMock(return_value=("message", 10, 2, 0, 0, (message_record,))),
        ),
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            side_effect=AssertionError("read after call"),
        ),
    ):
        result = await task.generate_content(uuid4(), target, "fr")
    assert result.success
    assert result.billing_records == (decision_record, enrich_record, message_record)
    assert result.model_name == "message-model"
    assert (result.tokens_in, result.tokens_out, result.tokens_cache) == (20, 4, 15)


async def test_heartbeat_skip_bills_cached_only_decision() -> None:
    records = (record("decision-model", 100.0, 0.01, cached=20),)
    with patch(
        "src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()
    ) as tracked:
        await HeartbeatProactiveTask()._track_skip_tokens(uuid4(), 0, 0, 20, 0, records)
    assert tracked.await_count == 1
    assert tracked.await_args.kwargs["billing_records"] == records


async def test_interest_preserves_reflection_and_presentation_tariffs() -> None:
    first = record("reflection", 100.0, 0.02, cached=35)
    second = record("presentation", 200.0, 0.03)
    source = ContentResult(
        content="fresh facts", source="llm_reflection", tokens_cache=35, billing_records=(first,)
    )
    task = InterestProactiveTask()
    target = SimpleNamespace(id=uuid4(), topic="Topic", category="general")
    generator = SimpleNamespace(
        generate=AsyncMock(
            return_value=SimpleNamespace(
                success=True, content_result=source, sources_tried=["llm_reflection"]
            )
        )
    )
    with (
        patch.object(task, "_get_content_generator", return_value=generator),
        patch.object(task, "_get_user_personality", AsyncMock(return_value=None)),
        patch.object(task, "_get_recent_notification_embeddings", AsyncMock(return_value=[])),
        patch(
            "src.domains.interests.proactive_task._resolve_user_locality",
            AsyncMock(return_value=None),
        ),
        patch.object(
            task, "_present_content", AsyncMock(return_value=("presented", 10, 2, 0, 0, (second,)))
        ),
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            side_effect=AssertionError("model read after call"),
        ),
    ):
        result = await task.generate_content(uuid4(), target, "fr")
    assert result.success
    assert result.billing_records == (first, second)
    assert result.model_name == "presentation"
    assert (result.tokens_in, result.tokens_out, result.tokens_cache) == (10, 2, 35)


async def test_reminder_cached_only_cost_is_not_repriced_or_dropped() -> None:
    records = (record("response-model", 100.0, 0.02, cached=50),)
    result = ReminderMessageResult("message", tokens_cache=50, billing_records=records)
    with (
        patch(
            "src.infrastructure.scheduler.reminder_notification.get_cached_cost_usd_eur",
            side_effect=AssertionError("repriced"),
        ),
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()
        ) as tracked,
    ):
        cost = await _account_reminder_spend(
            SimpleNamespace(),
            reminder_id="reminder",
            user_id=uuid4(),
            run_id="r",
            conversation_id=uuid4(),
            result=result,
        )
    assert cost == pytest.approx(0.018)
    assert tracked.await_args.kwargs["billing_records"] == records


def test_accumulator_preserves_each_model_and_started_hour() -> None:
    records = (record("one", 100.0, 0.02), record("two", 200.0, 0.03, cached=40))
    accumulator = TokenAccumulator()
    for item in records:
        accumulator.add(
            item.tokens_in, item.tokens_out, item.tokens_cache, item.model_name, billing_record=item
        )
    assert accumulator.to_result_dict()["billing_records"] == records
    assert accumulator.total_tokens == 52
    assert accumulator.call_count == 2


@pytest.mark.parametrize("returned_model", [None, "returned-model"])
async def test_direct_call_freezes_request_price_and_model_before_await(
    returned_model: str | None,
) -> None:
    llm = SimpleNamespace(model="requested-model")
    response = SimpleNamespace(
        text="message",
        response_metadata={"model_name": returned_model},
        usage_metadata={"input_tokens": 8, "output_tokens": 2},
    )
    snapshot = object()
    expected_model = returned_model or "requested-model"
    expected = record(expected_model, 100.0, 0.03)

    async def invoked(**_kwargs):
        llm.model = "configuration-changed-during-call"
        return response

    with (
        patch("src.infrastructure.llm.get_llm", return_value=llm),
        patch(
            "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
            AsyncMock(side_effect=invoked),
        ),
        patch.object(heartbeat_prompts, "time", return_value=100.0),
        patch.object(heartbeat_prompts, "capture_pricing_snapshot", return_value=snapshot),
        patch.object(token_capture, "priced_call", return_value=expected) as priced,
    ):
        result = await heartbeat_prompts.generate_heartbeat_message(
            "draft", HeartbeatContext(), "fr"
        )
    assert result[-1] == (expected,)
    assert priced.call_args.args[1:] == (expected_model, 100.0)
    assert priced.call_args.kwargs["snapshot"] is snapshot


def test_message_failure_keeps_already_paid_decision_and_enrichment() -> None:
    first = record("decision", 100.0, 0.02)
    second = record("enrichment", 110.0, 0.04, cached=30)
    target = HeartbeatTarget(
        context=HeartbeatContext(),
        decision=HeartbeatDecision(action="notify", reason="useful", message_draft="draft"),
        decision_tokens_in=10,
        decision_tokens_out=2,
        billing_records=(first,),
    )
    result = HeartbeatProactiveTask._failed_after_spending(
        target, 0, 0, RuntimeError("provider failed"), 30, 0, (second,)
    )
    assert not result.success
    assert result.billing_records == (first, second)
    assert result.tokens_cache == 30


@pytest.mark.parametrize("error_type", [ValueError, asyncio.CancelledError])
async def test_heartbeat_failed_structured_attempt_is_billed_before_error_returns(
    error_type,
) -> None:
    owner = uuid4()
    failure = error_type("synthetic failure after paid attempt")

    async def failed_structured(**kwargs):
        capture = kwargs["config"]["callbacks"][0]
        request = uuid4()
        capture.on_chat_model_start({}, [], run_id=request)
        capture.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="invalid typed answer",
                                usage_metadata={
                                    "input_tokens": 28,
                                    "output_tokens": 2,
                                    "total_tokens": 30,
                                    "input_token_details": {"cache_read": 20},
                                },
                                response_metadata={"model_name": "actual-returned-model"},
                            )
                        )
                    ]
                ]
            ),
            run_id=request,
        )
        raise failure

    with (
        patch(
            "src.infrastructure.llm.get_llm", return_value=SimpleNamespace(model="requested-model")
        ),
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            return_value=SimpleNamespace(model="requested-model", provider="openai"),
        ),
        patch(
            "src.infrastructure.llm.structured_output.get_structured_output",
            AsyncMock(side_effect=failed_structured),
        ),
        patch("src.infrastructure.proactive.tracking.ambient_run_id", return_value="sweep-run"),
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()
        ) as tracked,
        pytest.raises(error_type) as caught,
    ):
        await heartbeat_prompts.get_heartbeat_decision(HeartbeatContext(), "fr", user_id=owner)
    assert caught.value is failure
    assert tracked.await_count == 1
    call = tracked.await_args.kwargs
    assert call["user_id"] == owner
    assert call["run_id"] == "sweep-run"
    assert call["failed"] is True
    assert (call["tokens_in"], call["tokens_out"], call["tokens_cache"]) == (8, 2, 20)
    assert len(call["billing_records"]) == 1
    assert call["billing_records"][0].model_name == "actual-returned-model"


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_runner_dispatch_failure_settles_known_result_once(error_type) -> None:
    owner = SimpleNamespace(id=uuid4(), language="fr")
    records = (record("message-model", 100.0, 0.02, cached=20),)
    result = ProactiveTaskResult(
        success=True, content="message", tokens_cache=20, billing_records=records
    )
    task = SimpleNamespace(
        task_type="heartbeat",
        select_target=AsyncMock(return_value=SimpleNamespace(id="target")),
        generate_content=AsyncMock(return_value=result),
    )
    service = ProactiveTaskRunner(task)
    failure = error_type("synthetic dispatch failure")
    service._dispatch_notification = AsyncMock(side_effect=failure)

    @asynccontextmanager
    async def effect(**_kwargs):
        yield SimpleNamespace(delivered=False)

    with (
        patch(
            "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect", effect
        ),
        patch("src.infrastructure.proactive.runner.track_proactive_tokens", AsyncMock()) as tracked,
        pytest.raises(error_type) as caught,
    ):
        await service._serve_user(owner, SimpleNamespace(), RunnerStats(), "sweep-run")
    assert caught.value is failure
    assert tracked.await_count == 1
    assert tracked.await_args.kwargs["billing_records"] == records
    assert tracked.await_args.kwargs["run_id"] == "sweep-run"
    assert tracked.await_args.kwargs["failed"] is True


@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_reminder_attempt_is_settled_before_delivery_failure(error_type) -> None:
    owner = uuid4()
    capture = token_capture.TokenCaptureHandler("message-model")
    response = AIMessage(
        content="message",
        usage_metadata={"input_tokens": 20, "output_tokens": 2, "total_tokens": 22},
    )
    capture.ensure_response_record(
        response, model_name="message-model", started_at=100.0, snapshot=None
    )
    result = ReminderMessageResult(
        "message",
        tokens_in=20,
        tokens_out=2,
        model_name="message-model",
        billing_records=capture.get_billing_records("message-model"),
        billing_capture=capture,
    )
    reminder = SimpleNamespace(
        id=uuid4(),
        user_id=owner,
        original_message="Synthetic reminder",
        content="Synthetic task",
        created_at=datetime.now(UTC),
        user_timezone="Europe/Paris",
        recurrence_spec=None,
    )
    failure = error_type("synthetic delivery failure")

    async def delivery(*_args, **_kwargs):
        assert tracked.await_count == 1
        raise failure

    with (
        patch(
            "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
            AsyncMock(return_value=False),
        ),
        patch.object(
            reminder_notification,
            "_load_owner",
            AsyncMock(return_value=(SimpleNamespace(language="fr", is_active=True), None)),
        ),
        patch.object(reminder_notification, "get_relevant_memories", AsyncMock(return_value=[])),
        patch.object(
            reminder_notification, "generate_reminder_message", AsyncMock(return_value=result)
        ),
        patch.object(reminder_notification, "_deliver", AsyncMock(side_effect=delivery)),
        patch.object(reminder_notification, "_archive", AsyncMock()) as archived,
        patch(
            "src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()
        ) as tracked,
        pytest.raises(error_type) as caught,
    ):
        await reminder_notification._notify(reminder)
    assert caught.value is failure
    assert tracked.await_count == 1
    assert tracked.await_args.kwargs["user_id"] == owner
    assert tracked.await_args.kwargs["billing_records"] == result.billing_records
    assert tracked.await_args.kwargs["db"] is None
    archived.assert_not_awaited()
    with patch(
        "src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()
    ) as tracked_again:
        cost = await _account_reminder_spend(
            None,
            reminder_id=str(reminder.id),
            user_id=owner,
            run_id="same-run",
            conversation_id=None,
            result=result,
        )
    tracked_again.assert_not_awaited()
    assert cost == sum(record.cost_eur for record in result.billing_records)
