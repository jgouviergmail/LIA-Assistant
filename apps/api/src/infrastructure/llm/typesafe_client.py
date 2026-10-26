"""Native TypeSafe transport (Choice and Noul); no chat emulation and no implicit retries.

The caller owns HTTP resources, policy, accounting and the fallback. A malformed
answer retains valid usage so paid attempts are still recorded before fallback.
Provider response bodies and credentials never appear in raised errors.

Instructions and criteria may be plain strings or structured JSON (a question and
its rules, a criterion's ``what``/``not_for``/``examples``), as the documented
request accepts. A Noul answers whether a condition holds with ONE probability and
no separate confidence; its answers travel apart from the Choice answers.
"""

import asyncio
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Literal, Self

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
)

from src.core.token_budget import count_external_tokens
from src.infrastructure.utils.bounded_read import BodyTooLargeError, read_bounded

# The documented context of Jev 1.13 and 1.14 (docs.typesafe.ai/models, read
# 2026-10-25): the state plus every question, and the state plus any ONE question.
# The vendor sets no limit on the number of questions; only these two count.
MAX_REQUEST_TOKENS = 64_000
MAX_QUESTION_TOKENS = 32_000
# An upper estimate from the local tokenizer — the vendor's is unpublished.
# Measured on 201 billed requests in six languages (2026-10-25): billed = 270 +
# 1.10 x local tokens + 49 per question, never above 87 % of this estimate. The
# vendor still refuses an over-long request itself (400 max_tokens_exceeded).
LOCAL_TOKEN_FACTOR = 1.25
REQUEST_OVERHEAD_TOKENS = 300
QUESTION_OVERHEAD_TOKENS = 60
MAX_RESPONSE_BYTES = 262_144
# A sanity bound on one batch's answer set, far above any consumer's own.
MAX_QUESTIONS = 256

# The HTTP schema promises an approximately unit sum. Observed Choice values are
# cent-quantized, sometimes with binary float residue; preserve that evidence.
CHOICE_PROBABILITY_CONTRACT = "cent-rounded-v1"
_CHOICE_QUANTUM = Decimal("0.01")
_CHOICE_FLOAT_EPSILON = Decimal("1e-12")
_CHOICE_PRECISE_SUM_TOLERANCE = Decimal("0.001")


# Plain unions: an ``Annotated`` inside a union loses its metadata
# (test_annotated_metadata_guard); emptiness is refused by ``_non_empty``.
Criterion = str | dict[str, JsonValue] | list[JsonValue]
Instructions = str | dict[str, JsonValue]


def _non_empty[T: Criterion](value: T) -> T:
    """An empty instruction or criterion tells the model nothing; refuse it."""
    if not value:
        raise ValueError("must not be empty")
    return value


def _fill(value: JsonValue, values: Mapping[str, str]) -> JsonValue:
    """Fill ``{name}`` placeholders in every string of an instructions tree."""
    if isinstance(value, str):
        return value.format(**values)
    if isinstance(value, list):
        return [_fill(item, values) for item in value]
    if isinstance(value, dict):
        return {key: _fill(item, values) for key, item in value.items()}
    return value


class ChoiceQuestion(BaseModel):
    """One bounded choice, with fully described candidate values."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["choice"] = Field(default="choice", description="Native primitive.")
    instructions: Instructions = Field(description="The judgment to make.")
    criteria: dict[str, Criterion] = Field(
        min_length=2,
        max_length=255,
        description="Allowed answers, in the order offered.",
    )

    @field_validator("instructions")
    @classmethod
    def _instructions_said(cls, value: Instructions) -> Instructions:
        return _non_empty(value)

    @field_validator("criteria")
    @classmethod
    def _criteria_said(cls, value: dict[str, Criterion]) -> dict[str, Criterion]:
        return {key: _non_empty(criterion) for key, criterion in value.items()}

    def filled(self, **values: str) -> Self:
        """A copy whose instructions name one state member (``items.{item_key}``)."""
        return self.model_copy(update={"instructions": _fill(self.instructions, values)})


class NoulCriteria(BaseModel):
    """What makes the condition true and what makes it false."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    true: Criterion = Field(description="When the condition holds.")
    false: Criterion = Field(description="When it does not.")

    @field_validator("true", "false")
    @classmethod
    def _outcome_said(cls, value: Criterion) -> Criterion:
        return _non_empty(value)


class NoulQuestion(BaseModel):
    """Whether one condition holds; answered by a single probability."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    type: Literal["noul"] = Field(default="noul", description="Native primitive.")
    instructions: Instructions = Field(description="The condition to judge.")
    criteria: NoulCriteria = Field(description="The two outcomes.")

    @field_validator("instructions")
    @classmethod
    def _instructions_said(cls, value: Instructions) -> Instructions:
        return _non_empty(value)

    def filled(self, **values: str) -> Self:
        """A copy whose instructions name one state member (``script.{line_key}``)."""
        return self.model_copy(update={"instructions": _fill(self.instructions, values)})


DecisionQuestion = ChoiceQuestion | NoulQuestion


class DecisionUsage(BaseModel):
    """Actual provider counters, including free output tokens."""

    model_config = ConfigDict(strict=True, frozen=True)
    input_tokens: int = Field(ge=0, le=2_147_483_647, description="Billed input tokens.")
    output_tokens: int = Field(
        ge=0, le=2_147_483_647, description="Output tokens, priced separately."
    )


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
InvalidResponseReason = Literal[
    "envelope_schema",
    "answer_set",
    "answer_schema",
    "option_set",
    "unknown_choice",
    "probability_sum",
    "winning_choice",
    "ambiguous_choice",  # Historical traces; tied maxima are valid uncertain answers.
]


class ChoiceAnswer(BaseModel):
    """The typed answer; candidate membership is checked against the request."""

    model_config = ConfigDict(strict=True, frozen=True)
    type: Literal["choice"] = Field(description="Returned primitive.")
    choice: str = Field(description="Winning candidate key.")
    confidence: Probability = Field(description="Distribution concentration, not correctness.")
    probabilities: dict[str, Probability] = Field(description="Candidate distribution.")


class NoulAnswer(BaseModel):
    """The probability that the condition holds; there is no separate confidence."""

    model_config = ConfigDict(strict=True, frozen=True)
    type: Literal["noul"] = Field(description="Returned primitive.")
    noul: Probability = Field(description="Probability that the condition holds.")


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
    """Independent answers sharing one provider usage, never one charge per answer.

    ``answers`` holds the Choice answers and ``nouls`` the Noul answers; together
    they cover exactly the questions sent.
    """

    model: str
    answers: dict[str, ChoiceAnswer]
    usage: DecisionUsage
    nouls: dict[str, NoulAnswer] = field(default_factory=dict)


class TypeSafeError(Exception):
    """Safe error metadata, optionally retaining an already billed attempt."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        usage: DecisionUsage | None = None,
        model: str | None = None,
        reason: InvalidResponseReason | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.usage = usage
        self.model = model
        self.reason = reason


class TypeSafeCancelledError(asyncio.CancelledError):
    """Cancellation still propagates, carrying only validated received spend."""

    def __init__(self, usage: DecisionUsage | None, model: str | None) -> None:
        super().__init__("cancelled")
        self.code = "cancelled"
        self.usage = usage
        self.model = model
        self.status_code = None
        self.reason = None


def _parse_envelope(raw: bytes) -> _Envelope:
    try:
        return _Envelope.model_validate_json(raw)
    except ValidationError:
        try:
            usage = _UsageEnvelope.model_validate_json(raw).usage
        except ValidationError:
            usage = None
        raise TypeSafeError("invalid_response", usage=usage, reason="envelope_schema") from None


def _received_metadata(raw: bytes | None) -> tuple[DecisionUsage | None, str | None]:
    """A complete body remains accounting evidence even if HTTP cleanup fails."""
    if raw is None:
        return None, None
    try:
        envelope = _parse_envelope(raw)
        return envelope.usage, envelope.model
    except TypeSafeError as exc:
        return exc.usage, exc.model


def _transport_failure(code: str, raw: bytes | None) -> TypeSafeError:
    usage, model = _received_metadata(raw)
    return TypeSafeError(code, usage=usage, model=model)


def _validate_questions(questions: Mapping[str, DecisionQuestion]) -> None:
    if not 1 <= len(questions) <= MAX_QUESTIONS or any(
        not key or len(key) > 100 for key in questions
    ):
        raise TypeSafeError("invalid_questions")


def _choice_probability_mass(probabilities: Mapping[str, float]) -> Decimal | None:
    values = [Decimal(str(value)) for value in probabilities.values()]
    total = sum(values, Decimal(0))
    if total <= 0:
        return None
    if abs(total - 1) <= _CHOICE_PRECISE_SUM_TOLERANCE:
        return total
    rounded = [value.quantize(_CHOICE_QUANTUM) for value in values]
    if any(
        abs(value - cent) > _CHOICE_FLOAT_EPSILON
        for value, cent in zip(values, rounded, strict=True)
    ):
        return None
    half = _CHOICE_QUANTUM / 2
    lower = sum(max(Decimal(0), value - half) for value in rounded)
    upper = sum(min(Decimal(1), value + half) for value in rounded)
    return total if lower <= 1 <= upper else None


def choice_confidence(answer: ChoiceAnswer) -> float | None:
    """Shared mass validation and conservative confidence; raw weights stay intact."""
    count = len(answer.probabilities)
    if count < 2 or answer.choice not in answer.probabilities:
        return None
    mass = _choice_probability_mass(answer.probabilities)
    if mass is None:
        return None
    # Never fill missing mass by raising the winning probability. Excess mass
    # lowers its concentration; tiny serialization residue keeps existing boundaries.
    normalizer = mass if mass > 1 + _CHOICE_FLOAT_EPSILON else Decimal(1)
    best = Decimal(str(answer.probabilities[answer.choice])) / normalizer
    concentration = max(Decimal(0), (count * best - 1) / (count - 1))
    return min(answer.confidence, float(concentration))


def _parse_answer(value: JsonValue, question: ChoiceQuestion) -> ChoiceAnswer:
    try:
        answer = ChoiceAnswer.model_validate(value)
    except ValidationError:
        raise TypeSafeError("invalid_response", reason="answer_schema") from None
    probabilities = answer.probabilities
    if set(probabilities) != set(question.criteria):
        raise TypeSafeError("invalid_response", reason="option_set")
    if answer.choice not in probabilities:
        raise TypeSafeError("invalid_response", reason="unknown_choice")
    confidence = choice_confidence(answer)
    if confidence is None:
        raise TypeSafeError("invalid_response", reason="probability_sum")
    if probabilities[answer.choice] != max(probabilities.values()):
        raise TypeSafeError("invalid_response", reason="winning_choice")
    return answer.model_copy(update={"confidence": confidence})


def _parse_noul(value: JsonValue) -> NoulAnswer:
    try:
        return NoulAnswer.model_validate(value)
    except ValidationError:
        raise TypeSafeError("invalid_response", reason="answer_schema") from None


def _parse_batch(raw: bytes, questions: Mapping[str, DecisionQuestion]) -> ChoiceBatchResult:
    envelope = _parse_envelope(raw)
    try:
        if not isinstance(envelope.answers, dict) or set(envelope.answers) != set(questions):
            raise TypeSafeError("invalid_response", reason="answer_set")
        answers: dict[str, ChoiceAnswer] = {}
        nouls: dict[str, NoulAnswer] = {}
        for key, question in questions.items():
            if isinstance(question, NoulQuestion):
                nouls[key] = _parse_noul(envelope.answers[key])
            else:
                answers[key] = _parse_answer(envelope.answers[key], question)
    except TypeSafeError as exc:
        raise TypeSafeError(
            "invalid_response",
            usage=envelope.usage,
            model=envelope.model,
            reason=exc.reason,
        ) from None
    return ChoiceBatchResult(envelope.model, answers, envelope.usage, nouls)


class TypeSafeClient:
    """The caller owns and closes the supplied HTTP client."""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def choose(
        self,
        *,
        model: str,
        state: JsonValue,
        question: ChoiceQuestion,
        timeout_seconds: float,
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
        questions: Mapping[str, DecisionQuestion],
        timeout_seconds: float,
    ) -> ChoiceBatchResult:
        """Evaluate independent questions once, atomically validating the answer set."""
        _validate_questions(questions)
        body = encode_decision_request(model, state, questions)
        raw: bytes | None = None
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
        except asyncio.CancelledError:
            if raw is not None:
                raise TypeSafeCancelledError(*_received_metadata(raw)) from None
            raise
        except BodyTooLargeError:
            raise TypeSafeError("response_too_large") from None
        except TimeoutError, httpx.TimeoutException:
            raise _transport_failure("timeout", raw) from None
        except httpx.RequestError:
            raise _transport_failure("transport_error", raw) from None
        except Exception:
            if raw is None:
                raise
            raise _transport_failure("transport_error", raw) from None
        return _parse_batch(raw, questions)


def estimated_tokens(local_tokens: int, questions: int) -> int:
    """An upper estimate of the tokens the provider bills for this content and shape."""
    return (
        math.ceil(local_tokens * LOCAL_TOKEN_FACTOR)
        + REQUEST_OVERHEAD_TOKENS
        + QUESTION_OVERHEAD_TOKENS * questions
    )


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def encode_decision_request(
    model: str, state: JsonValue, questions: Mapping[str, DecisionQuestion]
) -> bytes:
    """Reject malformed or over-long requests before HTTP; never leak their values.

    Both documented contexts are checked: the whole request, and the state with
    its largest question — each question is evaluated against the whole state.
    """
    _validate_questions(questions)
    try:
        dumped = {key: question.model_dump() for key, question in questions.items()}
        state_tokens = count_external_tokens(_json_text(state))
        question_tokens = [count_external_tokens(_json_text(value)) for value in dumped.values()]
        body = _json_text({"model": model, "state": state, "questions": dumped}).encode("utf-8")
    except TypeError, ValueError:
        raise TypeSafeError("invalid_request") from None
    if (
        estimated_tokens(state_tokens + sum(question_tokens), len(dumped)) > MAX_REQUEST_TOKENS
        or estimated_tokens(state_tokens + max(question_tokens), 1) > MAX_QUESTION_TOKENS
    ):
        raise TypeSafeError("request_too_large")
    return body
