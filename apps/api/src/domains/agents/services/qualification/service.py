"""One snapshotted native usage, bounded work and cancellation joined before return."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from src.core.constants import (
    JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE,
    JEV_CLASSIFICATION_CLAIM_POLL_SECONDS,
    JEV_CLASSIFICATION_CLAIM_TTL_SECONDS,
    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
    JEV_CLASSIFICATION_MAX_CONCURRENT_BATCHES,
    JEV_CLASSIFICATION_MAX_ITEMS,
    JEV_CLASSIFICATION_MIN_CONFIDENCE,
    JEV_CLASSIFICATION_TIMEOUT_SECONDS,
    JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS,
)
from src.core.content_classification import (
    CLASSIFICATION_VERSION,
    ContentClassification,
    EmailClassification,
)
from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.prompts.prompt_loader import PromptName, load_prompt
from src.domains.agents.services.qualification.batches import (
    ClassificationBatch,
    build_batches,
)
from src.domains.agents.services.qualification.cache import (
    ClassificationCache,
    classification_cache_key,
    open_classification_cache,
)
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.domains.agents.services.qualification.policy import classify_answers
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevSnapshot, load_jev_snapshot
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_models import context_preview
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.locks.redis_claim import acquire_claim, held_claim
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX

logger = get_logger(__name__)
_PROMPTS: tuple[PromptName, ...] = (
    "jev_email_category_question",
    "jev_email_priority_question",
    "jev_event_category_question",
)


@dataclass(frozen=True)
class ClassificationOperation:
    user_id: UUID
    run_id: str
    usage: JevUsage
    snapshot: JevSnapshot
    now: datetime
    timezone: str


def policy_fingerprint() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "version": CLASSIFICATION_VERSION,
                "threshold": JEV_CLASSIFICATION_MIN_CONFIDENCE,
                "alert_threshold": JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE,
                "ttls": [
                    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
                    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
                    JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS,
                ],
                "prompts": [load_prompt(name, version="v1") for name in _PROMPTS],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def qualify_observations(
    *,
    user_id: UUID,
    provider: str,
    source_scope: str,
    observations: list[ClassificationObservation],
    run_id: str,
    timezone: str,
    now: datetime | None = None,
) -> dict[str, ContentClassification]:
    if not observations or not source_scope or not run_id:
        return {}
    # Own mutable JSON evidence before the first await; a later source edit
    # must not alter the observation bound to this operation.
    values = [
        ClassificationObservation.model_validate_json(value.model_dump_json())
        for value in observations[:JEV_CLASSIFICATION_MAX_ITEMS]
    ]
    usage = (
        JevUsage.EMAIL_CLASSIFICATION
        if observations[0].kind == "email"
        else JevUsage.EVENT_CLASSIFICATION
    )
    snapshot = await load_jev_snapshot(usage)
    if not snapshot.requested or snapshot.configuration is None:
        return {}
    instant = now or datetime.now(UTC)
    operation = ClassificationOperation(user_id, run_id, usage, snapshot, instant, timezone)
    try:
        policy = policy_fingerprint()
        keys = {
            value.identity: classification_cache_key(
                value,
                user_id=user_id,
                provider=provider,
                source_scope=source_scope,
                model=snapshot.configuration.model,
                policy=policy,
                now=instant,
                timezone=timezone,
            )
            for value in values
        }
        # One source lock also coalesces overlapping pages, not only identical batches.
        scope = hashlib.sha256(
            json.dumps(
                [provider, source_scope, snapshot.configuration.model, policy, timezone]
            ).encode()
        ).hexdigest()
        claim_key = f"{CLAIM_PREFIX}:content_classification:{user_id}:{scope}"
        cache = await open_classification_cache()
        async with asyncio.timeout(JEV_CLASSIFICATION_TIMEOUT_SECONDS):
            return await _coalesced(operation, cache, keys, values, claim_key)
    except Exception as exc:
        # Optional classification never turns a successful source read into failure.
        # Cancellation is BaseException and deliberately propagates.
        logger.info(
            "content_classification_unavailable",
            usage=usage.value,
            error_type=type(exc).__name__,
        )
        return {}


async def _coalesced(
    operation: ClassificationOperation,
    cache: ClassificationCache,
    keys: dict[str, str],
    values: list[ClassificationObservation],
    claim_key: str,
) -> dict[str, ContentClassification]:
    cached = await cache.read(keys, values, datetime.now(UTC))
    if len(cached) == len(keys):
        return cached
    if cache.client is None:
        return {**cached, **await _build(operation, cache, keys, values, cached)}
    try:
        token = await acquire_claim(
            cache.client,
            claim_key,
            ttl_seconds=JEV_CLASSIFICATION_CLAIM_TTL_SECONDS,
            wait_seconds=JEV_CLASSIFICATION_TIMEOUT_SECONDS,
            poll_seconds=JEV_CLASSIFICATION_CLAIM_POLL_SECONDS,
        )
    except Exception as exc:
        logger.debug("classification_claim_unavailable", error_type=type(exc).__name__)
        return {**cached, **await _build(operation, cache, keys, values, cached)}
    if token is None:
        return cached
    async with held_claim(
        cache.client,
        claim_key,
        token,
        ttl_seconds=JEV_CLASSIFICATION_CLAIM_TTL_SECONDS,
        max_hold_seconds=JEV_CLASSIFICATION_TIMEOUT_SECONDS + 1,
    ):
        cached = await cache.read(keys, values, datetime.now(UTC))
        return {**cached, **await _build(operation, cache, keys, values, cached)}


async def _build(
    operation: ClassificationOperation,
    cache: ClassificationCache,
    keys: dict[str, str],
    values: list[ClassificationObservation],
    cached: dict[str, ContentClassification],
) -> dict[str, ContentClassification]:
    config = operation.snapshot.configuration
    if config is None:
        return {}
    batches = build_batches(
        [value for value in values if value.identity not in cached],
        model=config.model,
        now=operation.now,
        timezone=operation.timezone,
    )
    gate = asyncio.Semaphore(JEV_CLASSIFICATION_MAX_CONCURRENT_BATCHES)
    stop = asyncio.Event()
    async with asyncio.TaskGroup() as group:
        tasks = [
            group.create_task(_evaluate(operation, cache, keys, batch, gate, stop))
            for batch in batches
        ]
    return {
        identity: annotation for task in tasks for identity, annotation in task.result().items()
    }


async def _evaluate(
    operation: ClassificationOperation,
    cache: ClassificationCache,
    keys: dict[str, str],
    batch: ClassificationBatch,
    gate: asyncio.Semaphore,
    stop: asyncio.Event,
) -> dict[str, ContentClassification]:
    async with gate:
        if stop.is_set():
            return {}
        started = perf_counter()
        attempt = await _call_native(operation, batch)
        if attempt.outcome != "success":
            stop.set()
        accepted = _accepted_annotations(operation, batch, attempt)
        outcome = _application_outcome(accepted, attempt.outcome)
        jev_decisions_total.labels(usage=operation.usage, outcome=outcome).inc()
        jev_decision_duration_seconds.labels(usage=operation.usage, outcome=outcome).observe(
            perf_counter() - started
        )
        await cache.write(keys, accepted, operation.now)
        await record_action(
            operation.user_id,
            attempt.diagnostic,
            action="preview" if accepted else "aborted",
            outcome=outcome,
            target=operation.usage.value,
            observed_result=context_preview(
                {key: value.model_dump(mode="json") for key, value in accepted.items()}
            ),
        )
        return accepted


def _application_outcome(values: dict[str, ContentClassification], native_outcome: str) -> str:
    if not values:
        return native_outcome
    known = any(
        value.category != "unknown"
        or (isinstance(value, EmailClassification) and value.priority != "unknown")
        for value in values.values()
    )
    return "classified" if known else "uncertain"


def _accepted_annotations(
    operation: ClassificationOperation,
    batch: ClassificationBatch,
    attempt: DecisionAttempt,
) -> dict[str, ContentClassification]:
    if attempt.outcome != "success" or set(attempt.answers) != set(batch.questions):
        return {}
    return {
        value.identity: classify_answers(
            value,
            category=attempt.answers.get(f"i{index}_category"),
            priority=attempt.answers.get(f"i{index}_priority"),
            now=operation.now,
        )
        for index, value in enumerate(batch.members)
    }


async def _call_native(
    operation: ClassificationOperation, batch: ClassificationBatch
) -> DecisionAttempt:
    try:
        return await choose_many_with_jev(
            usage=operation.usage,
            user_id=operation.user_id,
            run_id=operation.run_id,
            state=batch.state,
            questions=batch.questions,
            snapshot=operation.snapshot,
        )
    except UsageLimitExceededError:
        return DecisionAttempt(outcome="quota_exceeded")
    except Exception as exc:
        logger.info(
            "classification_native_unavailable",
            usage=operation.usage.value,
            error_type=type(exc).__name__,
        )
        return DecisionAttempt(outcome="processing_error")
