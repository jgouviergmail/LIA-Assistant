"""A native batch has exact question identity and one independently billable usage."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from src.infrastructure.llm.typesafe_client import ChoiceQuestion, TypeSafeClient, TypeSafeError

pytestmark = pytest.mark.unit


def questions() -> dict[str, ChoiceQuestion]:
    return {
        "email": ChoiceQuestion(
            instructions="Read items.email.", criteria={"yes": "Yes", "no": "No"}
        ),
        "event": ChoiceQuestion(
            instructions="Read items.event.", criteria={"match": "Match", "unknown": "Insufficient"}
        ),
    }


def response() -> dict[str, JsonValue]:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "email": {
                "type": "choice",
                "choice": "yes",
                "confidence": 0.99,
                "probabilities": {"yes": 0.999, "no": 0.001},
            },
            "event": {
                "type": "choice",
                "choice": "unknown",
                "confidence": 0.99,
                "probabilities": {"match": 0.001, "unknown": 0.999},
            },
        },
        "usage": {"input_tokens": 703, "output_tokens": 38},
    }


async def test_two_independent_questions_share_one_request_and_one_usage() -> None:
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        result = await TypeSafeClient(http, "test-secret").choose_many(
            model="jev-1.13.0",
            state={"items": {"email": "Reply please", "event": "Meeting"}},
            questions=questions(),
            timeout_seconds=1,
        )
    assert len(requests) == 1
    assert set(json.loads(requests[0].content)["questions"]) == {"email", "event"}
    assert result.answers["email"].choice == "yes"
    assert result.answers["event"].choice == "unknown"
    assert result.usage.input_tokens == 703
    assert result.usage.output_tokens == 38


@pytest.mark.parametrize("malformation", ["missing", "foreign", "wrong-options"])
async def test_one_bad_answer_invalidates_batch_without_erasing_its_cost(malformation: str) -> None:
    body = response()
    original = body["answers"]
    assert isinstance(original, dict)
    answers = dict(original)
    if malformation == "missing":
        answers.pop("event")
    elif malformation == "foreign":
        answers["foreign"] = answers["event"]
    else:
        answers["event"] = answers["email"]
    body["answers"] = answers
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(TypeSafeError, match="invalid_response") as caught:
            await TypeSafeClient(http, "test-secret").choose_many(
                model="jev-1.13.0", state="items", questions=questions(), timeout_seconds=1
            )
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 703
    assert (
        caught.value.reason
        == {
            "missing": "answer_set",
            "foreign": "answer_set",
            "wrong-options": "option_set",
        }[malformation]
    )


async def test_tied_answer_does_not_erase_other_independent_answers_or_batch_usage() -> None:
    body = response()
    answers = body["answers"]
    assert isinstance(answers, dict)
    answers["event"] = {
        "type": "choice",
        "choice": "match",
        "confidence": 0.99,
        "probabilities": {"match": 0.5, "unknown": 0.5},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await TypeSafeClient(http, "secret").choose_many(
            model="jev-1.13.0", state="items", questions=questions(), timeout_seconds=1
        )
    assert result.answers["email"].choice == "yes"
    assert result.answers["email"].confidence == 0.99
    assert result.answers["event"].choice == "match"
    assert result.answers["event"].confidence == 0
    assert result.answers["event"].probabilities == {"match": 0.5, "unknown": 0.5}
    assert result.usage.input_tokens == 703 and result.usage.output_tokens == 38


@pytest.mark.parametrize(
    "item_tied,item_incoherent,scope_choice,scope_confidence,expected_keep",
    [
        (True, False, "clear", 0.8, None),
        (False, True, "clear", 0.8, None),
        (False, False, "clear", 0.8, [0]),
        (False, False, "uncertain", 0.99, None),
        (False, False, "clear", 0.799, None),
    ],
    ids=["tied-item", "incoherent-item", "clear-scope", "ambiguous-scope", "low-scope-confidence"],
)
async def test_http_scope_and_item_decisions_keep_one_charge_and_inspectable_hitl_outcome(
    item_tied: bool,
    item_incoherent: bool,
    scope_choice: str,
    scope_confidence: float,
    expected_keep: list[int] | None,
) -> None:
    from src.domains.agents.services.hitl.jev_item_filter import (
        _kept_indices,
        _record_result,
        exclusion_questions,
    )
    from src.domains.chat.service import TrackingContext
    from src.domains.llm.pricing_service import ModelPrice
    from src.domains.llm_config.jev_registry import JevUsage
    from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
    from src.infrastructure.llm import jev_runtime
    from src.infrastructure.llm.jev_debug_models import JevCallTrace, context_preview

    owner = uuid4()
    tracker = TrackingContext("tied-hitl", owner, "chat", None, auto_commit=False)
    price = ModelPrice(
        "jev-1.13.0", Decimal(".042"), None, Decimal(0), "per_1m_tokens", datetime.now(UTC)
    )
    config = DecisionConfiguration("jev-1.13.0", 2, SecretStr("secret"), price)
    requested = exclusion_questions(2)
    snapshot = [{"title": "A", "from": "Mira"}, {"title": "B", "from": "Robin"}]
    state = {
        "exclude_criteria": "Exclude the email from Robin.",
        "items": {f"item_{i}": item for i, item in enumerate(snapshot)},
    }
    body = {
        "model": "jev-1.13.0",
        "answers": {
            "item_0": {
                "type": "choice",
                "choice": "keep",
                "confidence": 0.99,
                "probabilities": {"keep": 0.999, "exclude": 0.001, "uncertain": 0.0},
            },
            "item_1": {
                "type": "choice",
                "choice": "exclude",
                "confidence": 0.99,
                "probabilities": (
                    {"keep": 0.5, "exclude": 0.5, "uncertain": 0.0}
                    if item_tied
                    else (
                        {"keep": 0.3, "exclude": 0.6, "uncertain": 0.1}
                        if item_incoherent
                        else {"keep": 0.001, "exclude": 0.999, "uncertain": 0.0}
                    )
                ),
            },
            "reference_scope": {
                "type": "choice",
                "choice": scope_choice,
                "confidence": scope_confidence,
                "probabilities": {
                    key: (
                        (1 + scope_confidence) / 2
                        if key == scope_choice
                        else (1 - scope_confidence) / 2
                    )
                    for key in ("clear", "uncertain")
                },
            },
        },
        "usage": {"input_tokens": 703, "output_tokens": 38},
    }
    trace = JevCallTrace(
        id=uuid4(),
        run_id="tied-hitl",
        caller="jev_hitl_exclusion",
        usage=JevUsage.HITL_EXCLUSION.value,
        started_at=datetime.now(UTC),
        requested_model=config.model,
        context=context_preview("synthetic list"),
    )
    real_client = httpx.AsyncClient
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=body)

    def mock_http() -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(serve))

    with (
        patch.object(
            jev_runtime,
            "load_jev_snapshot",
            AsyncMock(return_value=JevSnapshot(True, "ready", config)),
        ),
        patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()),
        patch.object(jev_runtime, "get_cached_usd_eur_rate", return_value=0.9),
        patch.object(jev_runtime, "begin_trace", AsyncMock(return_value=trace)),
        patch.object(jev_runtime.httpx, "AsyncClient", side_effect=mock_http),
        patch("src.infrastructure.llm.jev_debug_store.save_trace", AsyncMock()) as save,
    ):
        async with tracker:
            attempt = await jev_runtime.choose_many_with_jev(
                usage=JevUsage.HITL_EXCLUSION,
                user_id=owner,
                run_id="tied-hitl",
                state=state,
                questions=requested,
            )
        assert attempt.outcome == "success"
        keep = _kept_indices(attempt, 2)
        assert keep == expected_keep
        await _record_result(owner, attempt, snapshot, keep)
    assert len(requests) == 1
    submitted = json.loads(requests[0].content)
    assert submitted["state"] == state
    assert set(submitted["questions"]) == {"item_0", "item_1", "reference_scope"}
    calls = tracker.get_llm_calls_breakdown()
    assert len(calls) == 1 and calls[0]["status"] == "success"
    assert attempt.charge is not None and attempt.charge.input_tokens == 703
    assert attempt.charge.cost_usd == pytest.approx(703 * 0.042 / 1_000_000)
    assert calls[0]["cost_eur"] == attempt.charge.cost_eur
    saved = save.call_args.args[1]
    assert saved.action == ("fallback" if expected_keep is None else "selected")
    assert saved.outcome == ("uncertain" if expected_keep is None else "selected")
    assert saved.action_target == (
        "item_filter" if expected_keep is None else "human_reconfirmation"
    )
    assert saved.responses["item_0"].choice == "keep"
    assert saved.responses["item_1"].choice == "exclude"
    assert saved.responses["item_1"].confidence == pytest.approx(
        0.25 if item_tied else 0.4 if item_incoherent else 0.99
    )
    assert saved.responses["item_1"].probabilities[0].probability == (
        0.5 if item_tied else 0.6 if item_incoherent else 0.999
    )
    assert saved.responses["reference_scope"].choice == scope_choice
    assert saved.responses["reference_scope"].confidence == scope_confidence
    assert saved.decision_labels == {
        "item_0": "A",
        "item_1": "B",
        "reference_scope": "Exclusion reference scope",
    }
    assert saved.input_tokens == 703 and saved.output_tokens == 38
    assert saved.cost_eur == attempt.charge.cost_eur


@pytest.mark.parametrize("size", [0, 25])
async def test_batch_bounds_refuse_network_before_spending(size: int) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid batch reached provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        with pytest.raises(TypeSafeError, match="invalid_questions"):
            await TypeSafeClient(http, "test-secret").choose_many(
                model="jev-1.13.0",
                state="items",
                timeout_seconds=1,
                questions={str(i): questions()["email"] for i in range(size)},
            )


async def test_nonfinite_state_fails_as_a_safe_transport_outcome_before_network() -> None:
    def forbidden(request):
        pytest.fail("Invalid state reached provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
        with pytest.raises(TypeSafeError, match="invalid_request"):
            await TypeSafeClient(http, "test-secret").choose_many(
                model="jev-1.13.0",
                state={"score": float("nan")},
                questions=questions(),
                timeout_seconds=1,
            )
