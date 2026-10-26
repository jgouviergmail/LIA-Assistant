"""Pack whole observations under the actual native envelope and operation budgets."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import JsonValue

from src.core.constants import (
    JEV_CLASSIFICATION_ESTIMATED_INPUT_TOKENS,
    JEV_CLASSIFICATION_MAX_BATCHES,
    JEV_CLASSIFICATION_MAX_ITEMS,
    JEV_CLASSIFICATION_TOTAL_REQUEST_BYTES,
    JEV_SHARED_STATE_BATCH_BYTES,
)
from src.domains.agents.prompts.prompt_loader import PromptName, load_prompt
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.domains.agents.utils.token_utils import count_tokens
from src.infrastructure.llm.typesafe_client import (
    ChoiceQuestion,
    TypeSafeError,
    encode_decision_request,
)


def _reference_time(now: datetime, timezone: str) -> str:
    """The clock in the zone the question names (2026-10-25).

    An explicit local deadline then compares without a conversion: the calibration
    corpora state their reference in the zone they name, and a UTC instant beside
    the person's zone disagrees with it on the day around midnight. An unknown
    zone keeps the UTC instant.
    """
    try:
        return now.astimezone(ZoneInfo(timezone)).isoformat()
    except ValueError, ZoneInfoNotFoundError:
        return now.isoformat()


@dataclass(frozen=True)
class ClassificationBatch:
    state: dict[str, JsonValue]
    questions: dict[str, ChoiceQuestion]
    members: tuple[ClassificationObservation, ...]
    request_bytes: int
    estimated_input_tokens: int


def _batch(
    values: list[ClassificationObservation], *, model: str, now: datetime, timezone: str
) -> ClassificationBatch:
    questions: dict[str, ChoiceQuestion] = {}
    items: dict[str, JsonValue] = {}
    for index, value in enumerate(values):
        key = f"i{index}"
        items[key] = {
            "evidence": value.evidence,
            "evidence_scope": value.evidence_scope,
        }
        prompt: PromptName = (
            "jev_email_category_question"
            if value.kind == "email"
            else "jev_event_category_question"
        )
        questions[f"{key}_category"] = ChoiceQuestion.model_validate_json(
            load_prompt(prompt, version="v1")
        ).filled(item_key=key)
        if value.kind == "email":
            questions[f"{key}_priority"] = ChoiceQuestion.model_validate_json(
                load_prompt("jev_email_priority_question", version="v1")
            ).filled(item_key=key)
    state: dict[str, JsonValue] = {
        "reference_time": _reference_time(now, timezone),
        "timezone": timezone,
        "items": items,
    }
    encoded = encode_decision_request(model, state, questions)
    # Several items share one state only within the measured batch shape; a single
    # item is bounded by the provider's documented context alone.
    if len(values) > 1 and len(encoded) > JEV_SHARED_STATE_BATCH_BYTES:
        raise TypeSafeError("request_too_large")
    return ClassificationBatch(
        state,
        questions,
        tuple(values),
        len(encoded),
        count_tokens(encoded.decode("utf-8")),
    )


def build_batches(
    values: list[ClassificationObservation], *, model: str, now: datetime, timezone: str
) -> list[ClassificationBatch]:
    if len({value.kind for value in values}) > 1 or len(
        {value.identity for value in values}
    ) != len(values):
        raise ValueError("Classification observations must have one kind and distinct identities")
    batches: list[ClassificationBatch] = []
    pending: list[ClassificationObservation] = []
    current: ClassificationBatch | None = None
    for value in values[:JEV_CLASSIFICATION_MAX_ITEMS]:
        try:
            candidate = _batch([*pending, value], model=model, now=now, timezone=timezone)
        except TypeSafeError:
            candidate = None
        if candidate is not None:
            current, pending = candidate, [*pending, value]
            continue
        if current is not None:
            batches.append(current)
            current, pending = None, []
        try:
            current = _batch([value], model=model, now=now, timezone=timezone)
            pending = [value]
        except TypeSafeError:
            continue  # Whole observation omitted; never classify an undisclosed cut.
    if current is not None:
        batches.append(current)
    return _within_operation_budget(batches)


def _within_operation_budget(
    batches: list[ClassificationBatch],
) -> list[ClassificationBatch]:
    accepted: list[ClassificationBatch] = []
    request_bytes = tokens = 0
    for batch in batches[:JEV_CLASSIFICATION_MAX_BATCHES]:
        request_bytes += batch.request_bytes
        tokens += batch.estimated_input_tokens
        if (
            request_bytes > JEV_CLASSIFICATION_TOTAL_REQUEST_BYTES
            or tokens > JEV_CLASSIFICATION_ESTIMATED_INPUT_TOKENS
        ):
            break
        accepted.append(batch)
    return accepted
