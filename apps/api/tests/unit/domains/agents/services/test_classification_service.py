"""One operation snapshot, bounded calls, no generative fallback or orphaned work."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from src.domains.agents.services.qualification import service
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer
from tests.unit.domains.agents.services.test_classification_batches import observed

pytestmark = pytest.mark.unit


def ready() -> JevSnapshot:
    return JevSnapshot(
        True,
        "ready",
        DecisionConfiguration(
            "jev-pinned",
            2,
            SecretStr("test-only"),
            ModelPrice(
                "jev-pinned",
                Decimal(".042"),
                None,
                Decimal(0),
                "per_1m_tokens",
                datetime.now(UTC),
            ),
        ),
    )


async def successful(**kwargs: object) -> DecisionAttempt:
    questions = kwargs["questions"]
    assert isinstance(questions, dict)
    answers: dict[str, ChoiceAnswer] = {}
    for key, question in questions.items():
        choice = "normal" if key.endswith("_priority") else "professional"
        answers[key] = ChoiceAnswer(
            type="choice",
            choice=choice,
            confidence=1.0,
            probabilities={option: float(option == choice) for option in question.criteria},
        )
    return DecisionAttempt(outcome="success", answers=answers)


async def invoke(**kwargs: object):
    return await service.qualify_observations(
        user_id=uuid4(),
        provider="google_gmail",
        source_scope="grant-1",
        observations=[observed(1)],
        run_id="test-run",
        timezone="UTC",
        **kwargs,
    )


@pytest.fixture(autouse=True)
def native_seams(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "load_jev_snapshot", AsyncMock(return_value=ready()))
    monkeypatch.setattr(service, "choose_many_with_jev", AsyncMock(side_effect=successful))
    monkeypatch.setattr(service, "record_action", AsyncMock())
    monkeypatch.setattr(
        service,
        "open_classification_cache",
        AsyncMock(return_value=service.ClassificationCache(None)),
    )


async def test_two_email_questions_share_one_operation_snapshot_and_one_native_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    choose = AsyncMock(side_effect=successful)
    load = AsyncMock(return_value=ready())
    monkeypatch.setattr(service, "choose_many_with_jev", choose)
    monkeypatch.setattr(service, "load_jev_snapshot", load)
    result = await invoke()
    assert result["private-1"].category == "professional"
    assert result["private-1"].priority == "normal"
    load.assert_awaited_once_with(JevUsage.EMAIL_CLASSIFICATION)
    assert len(choose.call_args.kwargs["questions"]) == 2
    assert choose.await_count == 1
    assert choose.call_args.kwargs["snapshot"] is load.return_value


@pytest.mark.parametrize(
    "readiness", ["disabled", "missing_key", "missing_price", "unavailable_model"]
)
async def test_unavailable_usage_does_not_read_cache_or_spend(
    monkeypatch: pytest.MonkeyPatch, readiness: str
) -> None:
    monkeypatch.setattr(
        service,
        "load_jev_snapshot",
        AsyncMock(
            return_value=JevSnapshot(
                readiness != "disabled",
                "ready" if readiness == "disabled" else readiness,
            )
        ),
    )
    choose, cache = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "choose_many_with_jev", choose)
    monkeypatch.setattr(service, "open_classification_cache", cache)
    assert await invoke() == {}
    choose.assert_not_awaited()
    cache.assert_not_awaited()


async def test_optional_native_failure_preserves_source_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = observed(1)
    before = value.model_dump_json()
    monkeypatch.setattr(service, "choose_many_with_jev", AsyncMock(side_effect=TimeoutError))
    result = await service.qualify_observations(
        user_id=uuid4(),
        provider="google_gmail",
        source_scope="grant-1",
        observations=[value],
        run_id="test-run",
        timezone="UTC",
    )
    assert result == {} and value.model_dump_json() == before


async def test_parent_cancellation_joins_native_work_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, closed = asyncio.Event(), asyncio.Event()

    async def native(**kwargs: object) -> DecisionAttempt:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()
        return DecisionAttempt()

    monkeypatch.setattr(service, "choose_many_with_jev", native)
    task = asyncio.create_task(invoke())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.parametrize("failure", [None, "answer_set", "unexpected_model"])
async def test_real_native_transport_and_accounting_close_one_bill_even_for_an_unusable_answer(
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None,
) -> None:
    requests: list[dict[str, object]] = []

    def response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        answers = {}
        for key, question in body["questions"].items():
            choice = "normal" if key.endswith("_priority") else "professional"
            answers[key] = {
                "type": "choice",
                "choice": choice,
                "confidence": 1.0,
                "probabilities": {
                    option: float(option == choice) for option in question["criteria"]
                },
            }
        if failure == "answer_set":
            answers.pop(next(iter(answers)))
        return httpx.Response(
            200,
            json={
                "model": ("other-model" if failure == "unexpected_model" else body["model"]),
                "answers": answers,
                "usage": {"input_tokens": 1234, "output_tokens": 42},
            },
        )

    original_http = httpx.AsyncClient
    monkeypatch.setattr(
        jev_runtime.httpx,
        "AsyncClient",
        lambda: original_http(transport=httpx.MockTransport(response)),
    )
    monkeypatch.setattr(jev_runtime, "enforce_usage_limit", AsyncMock())
    monkeypatch.setattr(jev_runtime, "begin_trace", AsyncMock(return_value=None))
    monkeypatch.setattr(jev_runtime, "get_cached_usd_eur_rate", lambda: 0.9)
    monkeypatch.setattr(service, "choose_many_with_jev", jev_runtime.choose_many_with_jev)
    owner = uuid4()
    tracker = TrackingContext("classification-native-test", owner, "chat", None, auto_commit=False)
    async with tracker:
        result = await service.qualify_observations(
            user_id=owner,
            provider="google_gmail",
            source_scope="grant-1",
            observations=[observed(1)],
            run_id=tracker.run_id,
            timezone="UTC",
        )
    assert bool(result) == (failure is None)
    assert len(requests) == 1 and len(requests[0]["questions"]) == 2
    calls = tracker.get_llm_calls_breakdown()
    assert len(calls) == 1 and calls[0]["call_type"] == "decision"
    assert calls[0]["tokens_in"] == 1234 and calls[0]["tokens_out"] == 42
    assert calls[0]["cost_eur"] == pytest.approx(1234 * 0.042 / 1_000_000 * 0.9)


async def test_evidence_is_owned_before_the_first_configuration_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def snapshot(usage: JevUsage) -> JevSnapshot:
        started.set()
        await release.wait()
        return ready()

    monkeypatch.setattr(service, "load_jev_snapshot", snapshot)
    choose = AsyncMock(side_effect=successful)
    monkeypatch.setattr(service, "choose_many_with_jev", choose)
    value = observed(1)
    task = asyncio.create_task(
        service.qualify_observations(
            user_id=uuid4(),
            provider="google_gmail",
            source_scope="grant-1",
            observations=[value],
            run_id="test-run",
            timezone="UTC",
        )
    )
    await started.wait()
    value.evidence["snippet"] = "Changed while configuration was loading"
    release.set()
    await task
    assert (
        choose.call_args.kwargs["state"]["items"]["i0"]["evidence"]["snippet"]
        == "Please review the project contract."
    )


async def test_operation_timeout_cancels_and_joins_native_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = asyncio.Event()

    async def native(**kwargs: object) -> DecisionAttempt:
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()
        return DecisionAttempt()

    monkeypatch.setattr(service, "JEV_CLASSIFICATION_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(service, "choose_many_with_jev", native)
    assert await invoke() == {}
    assert closed.is_set()


def test_threshold_change_invalidates_cached_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = service.policy_fingerprint()
    monkeypatch.setattr(service, "JEV_CLASSIFICATION_MIN_CONFIDENCE", 0.999)
    assert service.policy_fingerprint() != before


async def test_a_broken_cache_does_not_wait_for_a_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = MagicMock(spec=Redis)
    redis.mget = AsyncMock(side_effect=ConnectionError("cache unavailable"))
    cache = service.ClassificationCache(redis)
    claim = AsyncMock()
    monkeypatch.setattr(service, "open_classification_cache", AsyncMock(return_value=cache))
    monkeypatch.setattr(service, "acquire_claim", claim)
    result = await invoke()
    assert result["private-1"].category == "professional"
    assert cache.client is None
    claim.assert_not_awaited()


async def test_provider_failure_stops_queued_paid_batches_but_keeps_completed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = [observed(index) for index in range(4)]
    batches = [
        service.build_batches([value], model="jev-pinned", now=datetime.now(UTC), timezone="UTC")[0]
        for value in values
    ]
    monkeypatch.setattr(service, "build_batches", lambda *args, **kwargs: batches)
    calls = 0

    async def native(**kwargs: object) -> DecisionAttempt:
        nonlocal calls
        calls += 1
        number = calls
        await asyncio.sleep(0.01)
        return (
            DecisionAttempt(outcome="provider_error") if number == 1 else await successful(**kwargs)
        )

    monkeypatch.setattr(service, "choose_many_with_jev", native)
    result = await service.qualify_observations(
        user_id=uuid4(),
        provider="google_gmail",
        source_scope="grant-1",
        observations=values,
        run_id="test-run",
        timezone="UTC",
    )
    assert calls == 2
    assert set(result) == {"private-1"}
