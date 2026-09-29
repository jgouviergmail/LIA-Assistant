"""A native batch has exact question identity and one independently billable usage."""

import json

import httpx
import pytest
from pydantic import JsonValue

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


@pytest.mark.parametrize("malformation", ["missing", "foreign", "wrong-options", "tie"])
async def test_one_bad_answer_invalidates_batch_without_erasing_its_cost(malformation: str) -> None:
    body = response()
    original = body["answers"]
    assert isinstance(original, dict)
    answers = dict(original)
    if malformation == "missing":
        answers.pop("event")
    elif malformation == "foreign":
        answers["foreign"] = answers["event"]
    elif malformation == "wrong-options":
        answers["event"] = answers["email"]
    else:
        answers["event"] = {
            "type": "choice",
            "choice": "match",
            "confidence": 0.99,
            "probabilities": {"match": 0.5, "unknown": 0.5},
        }
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
