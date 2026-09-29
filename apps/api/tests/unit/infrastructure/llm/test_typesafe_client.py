"""Native decision transport: exact wire contract, bounded failures, no chat shim."""

import asyncio
import json

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
    "choice,confidence,probabilities",
    [
        ("invented", 0.99, {"a": 0.99, "none": 0.01}),
        ("a", float("nan"), {"a": 0.99, "none": 0.01}),
        ("a", 0.99, {"a": 0.2, "none": 0.8}),
        ("a", 0.99, {"a": 0.9}),
        ("a", 0.99, {"a": 0.8, "none": 0.8}),
        ("a", 0.99, {"a": 0.5, "none": 0.5}),
    ],
)
async def test_invalid_answer_is_rejected_but_billable_usage_survives(
    choice: str, confidence: float, probabilities: dict[str, float]
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
    assert caught.value.usage is not None
    assert caught.value.usage.input_tokens == 321


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
