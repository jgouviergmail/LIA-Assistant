"""Native TypeSafe Choice transport; no chat emulation and no implicit retries.

The caller owns HTTP resources, policy, accounting and the fallback. A malformed
answer retains valid usage so paid attempts are still recorded before fallback.
Provider response bodies and credentials never appear in raised errors.
"""

import asyncio
import json
import math
from dataclasses import dataclass
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from src.infrastructure.utils.bounded_read import BodyTooLargeError, read_bounded

# Conservative local limits; vendor token validation still applies independently.
MAX_REQUEST_BYTES = 32_000
MAX_RESPONSE_BYTES = 131_072
MAX_QUESTIONS = 24


class ChoiceQuestion(BaseModel):
    """One bounded choice, with fully described candidate values."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["choice"] = Field(default="choice", description="Native primitive.")
    instructions: str = Field(min_length=1, description="The judgment to make.")
    criteria: dict[str, str] = Field(min_length=2, max_length=255, description="Allowed answers.")


class DecisionUsage(BaseModel):
    """Actual provider counters, including free output tokens."""

    model_config = ConfigDict(strict=True, frozen=True)
    input_tokens: int = Field(ge=0, le=2_147_483_647, description="Billed input tokens.")
    output_tokens: int = Field(
        ge=0, le=2_147_483_647, description="Output tokens, priced separately."
    )


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ChoiceAnswer(BaseModel):
    """The typed answer; candidate membership is checked against the request."""

    model_config = ConfigDict(strict=True, frozen=True)
    type: Literal["choice"] = Field(description="Returned primitive.")
    choice: str = Field(description="Winning candidate key.")
    confidence: Probability = Field(description="Distribution concentration, not correctness.")
    probabilities: dict[str, Probability] = Field(description="Candidate distribution.")


class _UsageEnvelope(BaseModel):
    model_config = ConfigDict(strict=True)
    usage: DecisionUsage = Field(description="Actual token counters.")


class _Envelope(_UsageEnvelope):
    model: str = Field(min_length=1, max_length=100, description="Model that served the request.")
    answers: JsonValue = Field(default=None, description="Validate after capturing usage.")


@dataclass(frozen=True)
class ChoiceResult:
    """Successful decision and its independently billable usage."""

    model: str
    answer: ChoiceAnswer
    usage: DecisionUsage


@dataclass(frozen=True)
class ChoiceBatchResult:
    """Independent answers sharing one provider usage, never one charge per answer."""

    model: str
    answers: dict[str, ChoiceAnswer]
    usage: DecisionUsage


class TypeSafeError(Exception):
    """Safe error metadata, optionally retaining an already billed attempt."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        usage: DecisionUsage | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.usage = usage
        self.model = model


def _parse_envelope(raw: bytes) -> _Envelope:
    try:
        return _Envelope.model_validate_json(raw)
    except ValidationError:
        try:
            usage = _UsageEnvelope.model_validate_json(raw).usage
        except ValidationError:
            usage = None
        raise TypeSafeError("invalid_response", usage=usage) from None


def _parse_answer(value: JsonValue, question: ChoiceQuestion) -> ChoiceAnswer:
    answer = ChoiceAnswer.model_validate(value)
    probabilities = answer.probabilities
    if (
        set(probabilities) != set(question.criteria)
        or answer.choice not in probabilities
        or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.001)
        or probabilities[answer.choice] != max(probabilities.values())
        or list(probabilities.values()).count(probabilities[answer.choice]) != 1
    ):
        raise ValueError("inconsistent_answer")
    return answer


def _parse_batch(raw: bytes, questions: dict[str, ChoiceQuestion]) -> ChoiceBatchResult:
    envelope = _parse_envelope(raw)
    try:
        if not isinstance(envelope.answers, dict) or set(envelope.answers) != set(questions):
            raise ValueError("invalid_answers")
        answers = {
            key: _parse_answer(envelope.answers[key], question)
            for key, question in questions.items()
        }
    except ValidationError, ValueError:
        raise TypeSafeError(
            "invalid_response", usage=envelope.usage, model=envelope.model
        ) from None
    return ChoiceBatchResult(envelope.model, answers, envelope.usage)


class TypeSafeClient:
    """The caller owns and closes the supplied HTTP client."""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def choose(
        self, *, model: str, state: JsonValue, question: ChoiceQuestion, timeout_seconds: float
    ) -> ChoiceResult:
        """Evaluate once within a total deadline; the caller decides how to recover."""
        result = await self.choose_many(
            model=model,
            state=state,
            questions={"selection": question},
            timeout_seconds=timeout_seconds,
        )
        return ChoiceResult(result.model, result.answers["selection"], result.usage)

    async def choose_many(
        self,
        *,
        model: str,
        state: JsonValue,
        questions: dict[str, ChoiceQuestion],
        timeout_seconds: float,
    ) -> ChoiceBatchResult:
        """Evaluate independent questions once, atomically validating the answer set."""
        if not 1 <= len(questions) <= MAX_QUESTIONS or any(
            not key or len(key) > 100 for key in questions
        ):
            raise TypeSafeError("invalid_questions")
        body = _encode_request(model, state, questions)
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._http.stream(
                    "POST",
                    "https://api.typesafe.ai/v1/systemone",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    content=body,
                    timeout=timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        raise TypeSafeError("provider_error", status_code=response.status_code)
                    raw = await read_bounded(response, MAX_RESPONSE_BYTES)
        except BodyTooLargeError:
            raise TypeSafeError("response_too_large") from None
        except TimeoutError, httpx.TimeoutException:
            raise TypeSafeError("timeout") from None
        except httpx.RequestError:
            raise TypeSafeError("transport_error") from None
        return _parse_batch(raw, questions)


def _encode_request(model: str, state: JsonValue, questions: dict[str, ChoiceQuestion]) -> bytes:
    """Reject malformed state before HTTP; do not leak its values in exceptions."""
    try:
        body = json.dumps(
            {
                "model": model,
                "state": state,
                "questions": {key: question.model_dump() for key, question in questions.items()},
            },
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError:
        raise TypeSafeError("invalid_request") from None
    if len(body) > MAX_REQUEST_BYTES:
        raise TypeSafeError("request_too_large")
    return body
