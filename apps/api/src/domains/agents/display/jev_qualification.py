"""Early, reversible collection judgments; source records and final synthesis stay intact."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, JsonValue

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.filter_evidence import FilterEvidence, is_utf8_text
from src.domains.agents.display.jev_collection_time import calendar_time_facts
from src.domains.agents.display.jev_snapshot import (
    snapshot_collection_items,
    snapshot_filter_evidence,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevSnapshot, load_jev_snapshot
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_models import AppliedVerdict, JevCollectionCoverage
from src.infrastructure.llm.jev_debug_store import begin_trace, finish_trace, record_action
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
logger = structlog.get_logger(__name__)
PREVIEW_LIMIT = 100
MAX_BATCHES = 8
MAX_CONCURRENT_BATCHES = 2
_LOCAL_OUTCOMES = frozenset(
    {
        "disabled",
        "missing_key",
        "unavailable_model",
        "missing_price",
        "unavailable",
        "invalid_request",
        "invalid_questions",
        "too_many_questions",
        "request_too_large",
    }
)
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
    evaluated_count: int = Field(ge=0, description="Candidates sent in the bounded batches.")
    omitted_count: int = Field(ge=0, description="Candidates beyond the display budget.")


def _title(item: RegistryItem) -> str:
    for key in ("subject", "summary", "title", "name"):
        value = item.payload.get(key)
        if isinstance(value, str) and value.strip() and is_utf8_text(value[:180]):
            return value[:180]
    return item.id[:180]


def _excerpt(item: RegistryItem, evidence: FilterEvidence) -> str:
    """Human-readable source prose; the classifier still receives the full evidence."""
    for key in ("body", "description", "content", "notes", "snippet"):
        value = item.payload.get(key)
        if isinstance(value, str) and value.strip() and is_utf8_text(value[:600]):
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
    query: str,
    evidence: list[FilterEvidence],
    *,
    document_excerpt: bool = False,
    excluded: set[str] | None = None,
    facts: dict[str, JsonValue] | None = None,
) -> tuple[dict[str, JsonValue], dict[str, ChoiceQuestion]]:
    """Keep whole evidence within the transport budget, including repeated instructions."""
    prompt = ChoiceQuestion.model_validate_json(
        load_prompt(
            "jev_document_question" if document_excerpt else "jev_collection_question",
            version="v1",
        )
    )
    selected: dict[str, JsonValue] = {}
    questions: dict[str, ChoiceQuestion] = {}
    for index, value in enumerate(evidence):
        if not value.complete or not value.text:
            continue
        key = f"q{index}"
        if excluded and key in excluded:
            continue
        question = prompt.model_copy(
            update={"instructions": prompt.instructions.format(item_key=key)}
        )
        candidate = {**selected, key: value.data if value.data is not None else value.text}
        candidate_questions = {**questions, key: question}
        # The catalogue bounds a model name at 100 characters. Reserve its full
        # UTF-8 size; the transport independently enforces the actual envelope.
        body = json.dumps(
            {
                "model": "界" * 100,
                "state": _request_state(query, candidate, facts or {}),
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


@dataclass(frozen=True)
class QualificationBatch:
    selected: dict[str, JsonValue]
    questions: dict[str, ChoiceQuestion]
    facts: dict[str, JsonValue]


@dataclass(frozen=True)
class BatchJudgment:
    batch: QualificationBatch
    attempt: DecisionAttempt
    outcome: str
    verdicts: dict[str, AppliedVerdict] | None
    submitted: bool = True


def _batches(
    query: str,
    evidence: list[FilterEvidence],
    *,
    document_excerpt: bool = False,
    facts: dict[str, JsonValue] | None = None,
) -> list[QualificationBatch]:
    """Cover whole records in bounded lots while retaining their original keys."""
    batches: list[QualificationBatch] = []
    excluded: set[str] = set()
    for _ in range(MAX_BATCHES):
        selected, questions = _batch(
            query, evidence, document_excerpt=document_excerpt, excluded=excluded, facts=facts
        )
        if not questions:
            break
        batches.append(QualificationBatch(selected, questions, facts or {}))
        excluded.update(questions)
    return batches


def _request_state(
    query: str, selected: dict[str, JsonValue], facts: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    state: dict[str, JsonValue] = {"query": query, "items": dict(selected)}
    if facts:
        state["application_facts"] = {key: value for key, value in facts.items() if key in selected}
    return state


async def _qualify_batch(
    batch: QualificationBatch,
    *,
    gate: asyncio.Semaphore,
    snapshot: JevSnapshot,
    usage: JevUsage,
    user_id: UUID,
    run_id: str,
    query: str,
) -> BatchJudgment:
    async with gate:
        started = perf_counter()
        submitted = True
        try:
            attempt = await choose_many_with_jev(
                usage=usage,
                user_id=user_id,
                run_id=run_id,
                state=_request_state(query, batch.selected, batch.facts),
                questions=batch.questions,
                snapshot=snapshot,
            )
            submitted = attempt.charge is not None or attempt.outcome not in _LOCAL_OUTCOMES
        except Exception as exc:
            # Native runtime already closes any received bill and diagnostic.
            logger.warning(
                "jev_collection_batch_unavailable", usage=usage.value, error_type=type(exc).__name__
            )
            attempt = DecisionAttempt(outcome="processing_error")
            submitted = False
        outcome, verdicts = _judgments(attempt, batch.questions)
        jev_decisions_total.labels(usage=usage, outcome=outcome).inc()
        jev_decision_duration_seconds.labels(usage=usage, outcome=outcome).observe(
            perf_counter() - started
        )
        return BatchJudgment(batch, attempt, outcome, verdicts, submitted)


async def _qualify_batches(
    batches: list[QualificationBatch],
    *,
    snapshot: JevSnapshot,
    usage: JevUsage,
    user_id: UUID,
    run_id: str,
    query: str,
) -> list[BatchJudgment]:
    gate = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(
                _qualify_batch(
                    batch,
                    gate=gate,
                    snapshot=snapshot,
                    usage=usage,
                    user_id=user_id,
                    run_id=run_id,
                    query=query,
                )
            )
            for batch in batches
        ]
    # TaskGroup cancels and joins active/queued work before the owner can close.
    return [task.result() for task in tasks]


async def _record_judgments(
    user_id: UUID, results: list[BatchJudgment], items: list[RegistryItem]
) -> None:
    evaluated = sum(len(result.batch.questions) for result in results if result.submitted)
    unknown = sum(
        (
            sum(value == "unknown" for value in result.verdicts.values())
            if result.verdicts is not None
            else len(result.batch.questions)
        )
        for result in results
        if result.submitted
    )
    for index, result in enumerate(results, 1):
        valid = result.verdicts is not None
        await record_action(
            user_id,
            result.attempt.diagnostic,
            action="preview" if valid else "fallback",
            outcome=result.outcome,
            target="result_preview" if valid else "response",
            applied_decisions=result.verdicts,
            decision_labels={
                f"q{i}": _title(item)
                for i, item in enumerate(items[:PREVIEW_LIMIT])
                if f"q{i}" in result.batch.questions
            },
            collection_coverage=JevCollectionCoverage(
                candidate_count=len(items),
                evaluated_count=evaluated,
                unevaluated_count=len(items) - evaluated,
                omitted_count=max(0, len(items) - PREVIEW_LIMIT),
                unknown_count=unknown,
                batch_index=index,
                batch_count=len(results),
            ),
        )


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


def _project_candidates(
    items: list[RegistryItem],
    kind: RegistryItemType,
    reference_datetime: datetime | None,
    timezone: str | None,
) -> tuple[list[FilterEvidence], dict[str, JsonValue]]:
    visible = items[:PREVIEW_LIMIT]
    evidence = [
        snapshot_filter_evidence(item, preserve_fields=kind == RegistryItemType.MCP_RESULT)
        for item in visible
    ]
    reference = reference_datetime if reference_datetime is not None else datetime.now(UTC)
    facts: dict[str, JsonValue] = {}
    if kind == RegistryItemType.EVENT:
        facts = {
            f"q{index}": calendar_time_facts(item.payload, reference, timezone)
            for index, item in enumerate(visible)
        }
    return evidence, facts


def _qualified_entries(
    items: list[RegistryItem], evidence: list[FilterEvidence], verdicts: dict[str, AppliedVerdict]
) -> list[QualifiedItem]:
    return [
        QualifiedItem(
            id=item.id,
            title=_title(item),
            excerpt=_excerpt(item, evidence[index]),
            verdict=verdicts.get(f"q{index}", "unknown"),
        )
        for index, item in enumerate(items[:PREVIEW_LIMIT])
    ]


async def _no_eligible_evidence(
    *,
    snapshot: JevSnapshot,
    usage: JevUsage,
    kind: RegistryItemType,
    user_id: UUID,
    run_id: str,
    items: list[RegistryItem],
    evidence: list[FilterEvidence],
) -> None:
    """An active preview with zero native questions still explains its omission."""
    config = snapshot.configuration
    if config is None:
        return
    coverage = JevCollectionCoverage(
        candidate_count=len(items),
        evaluated_count=0,
        unevaluated_count=len(items),
        omitted_count=max(0, len(items) - PREVIEW_LIMIT),
        unknown_count=0,
    )
    reasons: dict[str, JsonValue] = {
        "incomplete_evidence": sum(not value.complete for value in evidence),
        "empty_evidence": sum(value.complete and not value.text for value in evidence),
        "oversized_evidence": sum(value.complete and bool(value.text) for value in evidence),
    }
    trace = await begin_trace(
        user_id=user_id,
        usage=usage,
        run_id=run_id,
        model=config.model,
        state={"candidate_count": len(items), "omission_reasons": reasons},
        question={},
    )
    trace = await finish_trace(
        user_id,
        trace,
        answer=None,
        question={},
        reported_model=None,
        duration_ms=0,
        outcome="no_eligible_evidence",
        action="fallback",
        status_code=None,
        counters=None,
        cost_eur=None,
    )
    await record_action(
        user_id,
        trace,
        action="fallback",
        outcome="no_eligible_evidence",
        target="response",
        collection_coverage=coverage,
    )
    logger.info(
        "jev_collection_qualification_completed",
        usage=usage.value,
        kind=kind.value,
        run_id=run_id,
        outcome="no_eligible_evidence",
        candidate_count=len(items),
        evaluated_count=0,
        unevaluated_count=len(items),
        omitted_count=coverage.omitted_count,
        unknown_count=0,
        batch_count=0,
    )


async def qualify_collection(
    *,
    user_id: UUID,
    run_id: str,
    query: str,
    items: list[RegistryItem],
    reference_datetime: datetime | None = None,
    timezone: str | None = None,
) -> QualifiedCollection | None:
    """Return a preview without ever narrowing the caller's registry or model context."""
    kind = _eligible_kind(query, items)
    if kind is None:
        return None
    items = snapshot_collection_items(items)
    usage = COLLECTION_USAGES[kind]
    # A switch change between lots applies only to the next collection operation.
    snapshot = await load_jev_snapshot(usage)
    if not snapshot.requested or snapshot.configuration is None:
        return None
    evidence, facts = _project_candidates(items, kind, reference_datetime, timezone)
    batches = _batches(query, evidence, document_excerpt=kind == RegistryItemType.NOTE, facts=facts)
    if not batches:
        await _no_eligible_evidence(
            snapshot=snapshot,
            usage=usage,
            kind=kind,
            user_id=user_id,
            run_id=run_id,
            items=items,
            evidence=evidence,
        )
        return None
    results = await _qualify_batches(
        batches,
        snapshot=snapshot,
        usage=usage,
        user_id=user_id,
        run_id=run_id,
        query=query,
    )
    verdicts = {key: value for result in results for key, value in (result.verdicts or {}).items()}
    evaluated_count = sum(len(result.batch.questions) for result in results if result.submitted)
    await _record_judgments(user_id, results, items)
    logger.info(
        "jev_collection_qualification_completed",
        usage=usage.value,
        kind=kind.value,
        run_id=run_id,
        outcome=(
            "qualified" if any(value != "unknown" for value in verdicts.values()) else "uncertain"
        ),
        candidate_count=len(items),
        evaluated_count=evaluated_count,
        unevaluated_count=len(items) - evaluated_count,
        omitted_count=max(0, len(items) - PREVIEW_LIMIT),
        batch_count=len(results),
    )
    if not any(result.verdicts is not None for result in results):
        return None
    return QualifiedCollection(
        kind=kind,
        items=_qualified_entries(items, evidence, verdicts),
        candidate_count=len(items),
        evaluated_count=evaluated_count,
        omitted_count=max(0, len(items) - PREVIEW_LIMIT),
    )
