"""Early, reversible collection judgments; source records and final synthesis stay intact."""

import json
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.filter_evidence import FilterEvidence, project_filter_evidence
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_models import AppliedVerdict
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import (
    MAX_QUESTIONS,
    MAX_REQUEST_BYTES,
    ChoiceAnswer,
    ChoiceQuestion,
)
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

MIN_CONFIDENCE = 0.95
PREVIEW_LIMIT = 100
COLLECTION_USAGES = {
    RegistryItemType.EMAIL: JevUsage.FILTER_EMAIL,
    RegistryItemType.EVENT: JevUsage.FILTER_EVENT,
    RegistryItemType.TASK: JevUsage.FILTER_TASK,
    RegistryItemType.FILE: JevUsage.FILTER_FILE,
    RegistryItemType.REMINDER: JevUsage.FILTER_REMINDER,
    RegistryItemType.TICKET: JevUsage.FILTER_TICKET,
    RegistryItemType.MCP_RESULT: JevUsage.FILTER_MCP,
    RegistryItemType.NOTE: JevUsage.FILTER_DOCUMENT,
}
if set(COLLECTION_USAGES.values()) != {
    usage for usage in JevUsage if usage.value.startswith("filter_")
}:
    raise RuntimeError("Every collection qualification must own a registered switch")


class QualifiedItem(BaseModel):
    id: str = Field(description="Exact registry identity, never a model-invented identifier.")
    title: str = Field(max_length=180, description="Source title for an inspectable preview.")
    excerpt: str = Field(max_length=600, description="Bounded source excerpt; rendered as text.")
    verdict: Literal["match", "non_match", "unknown"] = Field(
        description="Reversible qualification."
    )


class QualifiedCollection(BaseModel):
    kind: RegistryItemType = Field(description="Source collection type.")
    items: list[QualifiedItem] = Field(
        max_length=PREVIEW_LIMIT, description="Candidates, including unknowns and non-matches."
    )
    candidate_count: int = Field(
        ge=0, description="Size of the retrieved set, never a provider total."
    )
    evaluated_count: int = Field(ge=0, description="Candidates actually sent in the bounded batch.")
    omitted_count: int = Field(ge=0, description="Candidates beyond the display budget.")


def _title(item: RegistryItem) -> str:
    for key in ("subject", "summary", "title", "name"):
        value = item.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value[:180]
    return item.id[:180]


def _excerpt(item: RegistryItem, evidence: FilterEvidence) -> str:
    """Human-readable source prose; the classifier still receives the full evidence."""
    for key in ("body", "description", "content", "notes", "snippet"):
        value = item.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value[:600]
    return evidence.text[:600]


def compatible_collection_item(item: RegistryItem) -> bool:
    """Display already-authorized evidence, never infer permission to call its source.

    Generic MCP wrappers and unrelated notes are not collections. A structured
    MCP result remains untrusted text: this gate grants no tool permission and
    deliberately does not trust a server's readOnlyHint to authorize anything.
    """
    if item.type == RegistryItemType.MCP_RESULT:
        return item.meta.source.startswith("mcp_") and item.payload.get("_mcp_structured") is True
    if item.type == RegistryItemType.NOTE:
        return item.meta.source == "rag_user_excerpt"
    return item.type in COLLECTION_USAGES


def _eligible_kind(query: str, items: list[RegistryItem]) -> RegistryItemType | None:
    if not items or not query.strip() or len(query) > 4000:
        return None
    kind = items[0].type
    if kind not in COLLECTION_USAGES or any(
        item.type != kind
        or not item.id
        or len(item.id) > 512
        or not compatible_collection_item(item)
        for item in items
    ):
        return None
    return kind if len({item.id for item in items}) == len(items) else None


def _batch(
    query: str, evidence: list[FilterEvidence], *, document_excerpt: bool = False
) -> tuple[dict[str, str], dict[str, ChoiceQuestion]]:
    """Keep whole evidence within the transport budget, including repeated instructions."""
    prompt = ChoiceQuestion.model_validate_json(
        load_prompt(
            "jev_document_question" if document_excerpt else "jev_collection_question",
            version="v1",
        )
    )
    selected: dict[str, str] = {}
    questions: dict[str, ChoiceQuestion] = {}
    for index, value in enumerate(evidence):
        if not value.complete or not value.text:
            continue
        key = f"q{index}"
        question = prompt.model_copy(
            update={"instructions": prompt.instructions.format(item_key=key)}
        )
        candidate = {**selected, key: value.text}
        candidate_questions = {**questions, key: question}
        # The catalogue bounds a model name at 100 characters. Reserve its full
        # UTF-8 size; the transport independently enforces the actual envelope.
        body = json.dumps(
            {
                "model": "界" * 100,
                "state": {"query": query, "items": candidate},
                "questions": {name: q.model_dump() for name, q in candidate_questions.items()},
            },
            ensure_ascii=False,
        )
        if len(body.encode("utf-8")) > MAX_REQUEST_BYTES:
            continue
        selected, questions = candidate, candidate_questions
        if len(questions) == MAX_QUESTIONS:
            break
    return selected, questions


def _verdict(answer: ChoiceAnswer | None) -> Literal["match", "non_match", "unknown"]:
    if answer is not None and answer.confidence >= MIN_CONFIDENCE:
        if answer.choice == "match":
            return "match"
        if answer.choice == "non_match":
            return "non_match"
    return "unknown"


def _judgments(
    attempt: DecisionAttempt, questions: dict[str, ChoiceQuestion]
) -> tuple[str, dict[str, AppliedVerdict] | None]:
    """One policy result feeds both the visible preview and its diagnostic."""
    if attempt.outcome != "success":
        return attempt.outcome, None
    if set(attempt.answers) != set(questions):
        return "invalid_response", None
    verdicts = {key: _verdict(value) for key, value in attempt.answers.items()}
    outcome = "qualified" if any(v != "unknown" for v in verdicts.values()) else "uncertain"
    return outcome, verdicts


async def qualify_collection(
    *,
    user_id: UUID,
    run_id: str,
    query: str,
    items: list[RegistryItem],
) -> QualifiedCollection | None:
    """Return a preview without ever narrowing the caller's registry or model context."""
    kind = _eligible_kind(query, items)
    if kind is None:
        return None
    usage = COLLECTION_USAGES[kind]
    evidence = [
        project_filter_evidence(item.payload, preserve_fields=kind == RegistryItemType.MCP_RESULT)
        for item in items[:PREVIEW_LIMIT]
    ]
    selected, questions = _batch(query, evidence, document_excerpt=kind == RegistryItemType.NOTE)
    if not questions:
        return None
    started = perf_counter()
    attempt = await choose_many_with_jev(
        usage=usage,
        user_id=user_id,
        run_id=run_id,
        state={"query": query, "items": dict(selected)},
        questions=questions,
    )
    outcome, verdicts = _judgments(attempt, questions)
    valid = verdicts is not None
    await record_action(
        user_id,
        attempt.diagnostic,
        action="preview" if valid else "fallback",
        outcome=outcome,
        target="result_preview" if valid else "response",
        applied_decisions=verdicts,
        decision_labels={
            f"q{i}": _title(item)
            for i, item in enumerate(items[:PREVIEW_LIMIT])
            if f"q{i}" in questions
        },
    )
    jev_decisions_total.labels(usage=usage, outcome=outcome).inc()
    jev_decision_duration_seconds.labels(usage=usage, outcome=outcome).observe(
        perf_counter() - started
    )
    if verdicts is None:
        return None
    entries = [
        QualifiedItem(
            id=item.id,
            title=_title(item),
            excerpt=_excerpt(item, evidence[index]),
            verdict=verdicts.get(f"q{index}", "unknown"),
        )
        for index, item in enumerate(items[:PREVIEW_LIMIT])
    ]
    return QualifiedCollection(
        kind=kind,
        items=entries,
        candidate_count=len(items),
        evaluated_count=len(selected),
        omitted_count=max(0, len(items) - PREVIEW_LIMIT),
    )
