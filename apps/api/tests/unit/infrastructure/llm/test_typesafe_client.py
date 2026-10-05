"""Native decision transport: exact wire contract, bounded failures, no chat shim."""

import asyncio
import json
import math
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from src.infrastructure.llm.typesafe_client import ChoiceQuestion, TypeSafeClient, TypeSafeError

pytestmark = pytest.mark.unit


def _reply() -> dict[str, object]:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "selection": {
                "type": "choice",
                "choice": "a",
                "confidence": 0.99,
                "probabilities": {"a": 0.999, "none": 0.001},
            }
        },
        "usage": {"input_tokens": 321, "output_tokens": 18},
    }


@pytest.mark.parametrize("cancelled", [False, True])
async def test_received_usage_survives_response_stream_close_failure(cancelled: bool) -> None:
    error = asyncio.CancelledError if cancelled else OSError

    @asynccontextmanager
    async def closing_stream(*args, **kwargs):
        yield httpx.Response(200, json=_reply())
        raise error("private cleanup text")

    async with httpx.AsyncClient() as http:
        with patch.object(http, "stream", closing_stream):
            with pytest.raises(asyncio.CancelledError if cancelled else TypeSafeError) as caught:
                await TypeSafeClient(http, "test-secret").choose(
                    model="jev-1.13.0",
                    state={"text": "Synthetic"},
                    question=ChoiceQuestion(
                        instructions="Select", criteria={"a": "A", "none": "N"}
                    ),
                    timeout_seconds=1,
                )
    assert caught.value.usage.input_tokens == 321
    assert caught.value.usage.output_tokens == 18
    assert caught.value.model == "jev-1.13.0"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize(
    "raw", [b'{"usage":{"input_tokens":true,"output_tokens":18}}', b'{"usage":']
)
async def test_stream_close_failure_never_invents_unvalidated_usage(cancelled: bool, raw: bytes):
    error = asyncio.CancelledError if cancelled else OSError

    @asynccontextmanager
    async def closing_stream(*args, **kwargs):
        yield httpx.Response(200, content=raw)
        raise error()

    async with httpx.AsyncClient() as http:
        with patch.object(http, "stream", closing_stream):
            with pytest.raises(asyncio.CancelledError if cancelled else TypeSafeError) as caught:
                await TypeSafeClient(http, "test-secret").choose(
                    model="jev-1.13.0",
                    state="Synthetic",
                    question=ChoiceQuestion(
                        instructions="Select", criteria={"a": "A", "none": "N"}
                    ),
                    timeout_seconds=1,
                )
    assert caught.value.usage is None


async def test_native_contract_and_usage() -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert json.loads(request.content) == {
            "model": "jev-1.13.0",
            "state": {"text": "A workshop"},
            "questions": {
                "selection": {
                    "type": "choice",
                    "instructions": "Select the format.",
                    "criteria": {"a": "Workshop", "none": "Unclear"},
                }
            },
        }
        return httpx.Response(200, json=_reply())

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        result = await TypeSafeClient(http, "test-secret").choose(
            model="jev-1.13.0",
            state={"text": "A workshop"},
            question=ChoiceQuestion(
                instructions="Select the format.", criteria={"a": "Workshop", "none": "Unclear"}
            ),
            timeout_seconds=1,
        )
    assert result.answer.choice == "a"
    assert result.usage.input_tokens == 321
    assert result.usage.output_tokens == 18


@pytest.mark.parametrize("status", [401, 422, 429, 500, 529])
async def test_provider_failures_are_classified_without_leaking_body_or_retrying(
    status: int,
) -> None:
    calls = 0

    def serve(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status, text="private transcript test-secret", headers={"Retry-After": "60"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        with pytest.raises(TypeSafeError) as caught:
            await TypeSafeClient(http, "test-secret").choose(
                model="jev-1.13.0",
                state="text",
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
                timeout_seconds=1,
            )
    assert caught.value.status_code == status
    assert "private" not in str(caught.value) and "test-secret" not in str(caught.value)
    assert calls == 1


@pytest.mark.parametrize(
    "choice,confidence,probabilities,reason",
    [
        ("invented", 0.99, {"a": 0.99, "none": 0.01}, "unknown_choice"),
        ("a", float("nan"), {"a": 0.99, "none": 0.01}, "answer_schema"),
        ("a", 0.99, {"a": 0.2, "none": 0.8}, "winning_choice"),
        ("a", 0.99, {"a": 0.9}, "option_set"),
        ("a", 0.99, {"a": 0.8, "none": 0.8}, "probability_sum"),
    ],
)
async def test_invalid_answer_is_rejected_but_billable_usage_survives(
    choice: str, confidence: float, probabilities: dict[str, float], reason: str
) -> None:
    body = _reply()
    body["answers"] = {
        "selection": {
            "type": "choice",
            "choice": choice,
            "confidence": confidence,
            "probabilities": probabilities,
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(body)))
    ) as http:
        with pytest.raises(TypeSafeError) as caught:
            await TypeSafeClient(http, "test-secret").choose(
                model="jev-1.13.0",
                state="text",
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
                timeout_seconds=1,
            )
    assert caught.value.code == "invalid_response"
    assert caught.value.reason == reason
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 321


@pytest.mark.parametrize(
    "choice,confidence,probabilities,expected_confidence",
    [
        ("a", 0.99, {"a": 0.6, "none": 0.4}, 0.2),
        ("a", 0.99, {"a": 0.6, "none": 0.3, "other": 0.1}, 0.4),
        ("a", 0.1, {"a": 0.6, "none": 0.3, "other": 0.1}, 0.1),
        ("none", 0.99, {"a": 0.5, "none": 0.5}, 0.0),
        ("a", 0.99, {"a": 0.5, "none": 0.5, "other": 0.0}, 0.25),
        ("none", 0.1, {"a": 0.5, "none": 0.5, "other": 0.0}, 0.1),
        ("other", 0.99, {"a": 1 / 3, "none": 1 / 3, "other": 1 / 3}, 0.0),
    ],
)
async def test_maxima_preserve_decision_and_usage_but_cannot_inflate_confidence(
    choice: str,
    confidence: float,
    probabilities: dict[str, float],
    expected_confidence: float,
) -> None:
    body = _reply()
    body["answers"] = {
        "selection": {
            "type": "choice",
            "choice": choice,
            "confidence": confidence,
            "probabilities": probabilities,
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await TypeSafeClient(http, "secret").choose(
            model="jev-1.13.0",
            state="Two equally plausible formats.",
            question=ChoiceQuestion(
                instructions="Select the supported format.",
                criteria={key: key for key in probabilities},
            ),
            timeout_seconds=1,
        )
    assert result.answer.choice == choice
    assert result.answer.probabilities == probabilities
    assert result.answer.confidence == pytest.approx(expected_confidence)
    assert result.usage.input_tokens == 321 and result.usage.output_tokens == 18


@pytest.mark.parametrize("count", [2, 3, 5, 255])
@pytest.mark.parametrize("threshold", [0.80, 0.95, 0.97, 0.99])
@pytest.mark.parametrize("deficit", [0.0, 1e-12, None], ids=["exact", "below", "one-ulp-below"])
async def test_derived_confidence_keeps_exact_policy_boundary_without_promoting_a_deficit(
    count: int, threshold: float, deficit: float | None
) -> None:
    """Binary float arithmetic alone must not reject the exact accepted boundary."""
    target = Decimal(str(threshold)) - Decimal(str(deficit or 0))
    top = float((1 + (count - 1) * target) / count)
    if deficit is None:
        top = math.nextafter(top, 0.0)
    probabilities = {"a": top, **{f"other_{i}": (1 - top) / (count - 1) for i in range(count - 1)}}
    body = _reply()
    body["answers"] = {
        "selection": {
            "type": "choice",
            "choice": "a",
            "confidence": 1.0,
            "probabilities": probabilities,
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await TypeSafeClient(http, "secret").choose(
            model="jev-1.13.0",
            state="Boundary case.",
            question=ChoiceQuestion(
                instructions="Select.", criteria={key: key for key in probabilities}
            ),
            timeout_seconds=1,
        )
    assert (result.answer.confidence >= threshold) is (deficit == 0.0)
    assert result.answer.probabilities == probabilities


@pytest.mark.parametrize(
    "total,accepted", [(0.9995, True), (1.0005, True), (0.998, False), (1.002, False)]
)
async def test_probability_sum_rounding_tolerance_is_bounded(total: float, accepted: bool) -> None:
    body = _reply()
    body["answers"] = {
        "selection": {
            "type": "choice",
            "choice": "a",
            "confidence": 0.99,
            "probabilities": {"a": total * 0.9, "none": total * 0.1},
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        client = TypeSafeClient(http, "secret")
        decision = client.choose(
            model="jev-1.13.0",
            state="A format.",
            question=ChoiceQuestion(instructions="Select.", criteria={"a": "A", "none": "None"}),
            timeout_seconds=1,
        )
        if accepted:
            assert (await decision).answer.choice == "a"
        else:
            with pytest.raises(TypeSafeError) as caught:
                await decision
            assert caught.value.reason == "probability_sum"
            assert caught.value.usage is not None


@pytest.mark.parametrize("counter", [-1, True, "100", 2**63])
async def test_unsafe_counters_are_not_accepted_into_the_ledger(counter: object) -> None:
    body = _reply()
    body["usage"] = {"input_tokens": counter, "output_tokens": 1}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(TypeSafeError, match="invalid_response") as error:
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "None"}
                ),
            )
    assert error.value.usage is None
    assert error.value.reason == "envelope_schema"


async def test_total_deadline_interrupts_a_slow_provider() -> None:
    async def serve(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json=_reply())

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        with pytest.raises(TypeSafeError, match="timeout"):
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=0.01,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
            )


@pytest.mark.parametrize(
    "status,body,code",
    [
        (302, b"", "provider_error"),
        (200, b"x" * 131_073, "response_too_large"),
        (200, b"not json", "invalid_response"),
    ],
    ids=["redirect", "oversized-body", "malformed-json"],
)
async def test_bounded_body_and_no_redirect(status: int, body: bytes, code: str) -> None:
    calls = []

    def serve(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(status, content=body, headers={"Location": "https://other.invalid/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        with pytest.raises(TypeSafeError, match=code):
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
            )
    assert len(calls) == 1


async def test_large_request_is_refused_before_network() -> None:
    def serve(request: httpx.Request) -> httpx.Response:
        pytest.fail("An oversized request reached the provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        with pytest.raises(TypeSafeError, match="request_too_large"):
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="x" * 32_001,
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
            )


async def test_cancel_is_not_misrepresented_as_a_fallback() -> None:
    async def serve(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as http:
        with pytest.raises(asyncio.CancelledError):
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "Unclear"}
                ),
            )


@pytest.mark.parametrize("answers", [None, [], "invalid", {}])
async def test_unusable_answers_still_preserve_valid_usage(answers: object) -> None:
    body = _reply()
    body["answers"] = answers
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(TypeSafeError) as caught:
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "None"}
                ),
            )
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 321


@pytest.mark.parametrize("reported", [None, "", "x" * 101])
async def test_invalid_model_metadata_does_not_erase_provider_counters(reported: object) -> None:
    body = _reply()
    body["model"] = reported
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(TypeSafeError) as caught:
            await TypeSafeClient(http, "secret").choose(
                model="jev-1.13.0",
                state="text",
                timeout_seconds=1,
                question=ChoiceQuestion(
                    instructions="Select.", criteria={"a": "A", "none": "None"}
                ),
            )
    assert caught.value.usage is not None and caught.value.usage.input_tokens == 321
    assert caught.value.model is None
