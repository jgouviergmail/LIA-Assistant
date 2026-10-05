"""The only application door to the native TypeSafe transport."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter, time
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import structlog
from pydantic import JsonValue

from src.core.context import current_tracker
from src.domains.llm.pricing_service import token_cost_usd
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import (
    DecisionConfiguration,
    JevSnapshot,
    load_jev_snapshot,
)
from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate
from src.infrastructure.llm.decision_types import DecisionAttempt, DecisionCharge
from src.infrastructure.llm.inference_params import capture_inference_params
from src.infrastructure.llm.jev_debug_models import JevAction
from src.infrastructure.llm.jev_debug_store import begin_trace, finish_trace
from src.infrastructure.llm.typesafe_client import (
    ChoiceBatchResult,
    ChoiceQuestion,
    DecisionUsage,
    InvalidResponseReason,
    TypeSafeCancelledError,
    TypeSafeClient,
    TypeSafeError,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.proactive.tracking import out_of_turn_spend

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def _decision_tracker(run_id: str, user_id: UUID) -> AsyncIterator[TrackingContext]:
    """Join this account's current act; only standalone native work owns a tracker."""
    tracker = current_tracker.get()
    if tracker is not None and tracker.run_id == run_id and tracker.user_id == user_id:
        yield tracker
    else:
        async with out_of_turn_spend(run_id, user_id, "jev_decision") as owned:
            yield owned


async def _complete_charge(record: Coroutine[object, object, None]) -> None:
    """A received bill survives cancellation; join recording before the owner closes."""
    pending = asyncio.create_task(record)
    cancelled = False
    while not pending.done():
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            cancelled = True
    pending.result()
    if cancelled:
        raise asyncio.CancelledError


def _received_interruption(
    error: TypeSafeError | TypeSafeCancelledError,
) -> asyncio.CancelledError | None:
    return error if isinstance(error, TypeSafeCancelledError) else None


def _propagate_interruption(interruption: asyncio.CancelledError | None) -> None:
    if interruption is not None:
        raise interruption


async def choose_with_jev(
    *,
    usage: JevUsage,
    user_id: UUID,
    run_id: str,
    state: JsonValue,
    question: ChoiceQuestion,
) -> DecisionAttempt:
    """Resolve one operation snapshot, gate spend, call once and account before returning."""
    return await choose_many_with_jev(
        usage=usage,
        user_id=user_id,
        run_id=run_id,
        state=state,
        questions={"selection": question},
    )


async def choose_many_with_jev(
    *,
    usage: JevUsage,
    user_id: UUID,
    run_id: str,
    state: JsonValue,
    questions: dict[str, ChoiceQuestion],
    snapshot: JevSnapshot | None = None,
) -> DecisionAttempt:
    """One quota gate and charge per batch, retaining an operation's routing.

    A bounded multi-batch consumer may pass its captured snapshot for this same
    usage. New operations omit it and read the current database switches.
    """
    if snapshot is None:
        snapshot = await load_jev_snapshot(usage)
    if not snapshot.requested:
        return DecisionAttempt(
            outcome="disabled" if snapshot.readiness == "ready" else snapshot.readiness
        )
    config = snapshot.configuration
    if config is None:
        return DecisionAttempt(outcome=snapshot.readiness)
    await enforce_usage_limit(user_id, layer="jev_decision")
    return await _execute_decision(
        config=config,
        usage=usage,
        user_id=user_id,
        run_id=run_id,
        state=state,
        questions=questions,
    )


async def _call_native(
    client: TypeSafeClient,
    config: DecisionConfiguration,
    state: JsonValue,
    questions: dict[str, ChoiceQuestion],
) -> ChoiceBatchResult:
    """Preserve the single-selection interface while sharing batch validation."""
    if set(questions) == {"selection"}:
        result = await client.choose(
            model=config.model,
            state=state,
            question=questions["selection"],
            timeout_seconds=config.timeout_seconds,
        )
        return ChoiceBatchResult(result.model, {"selection": result.answer}, result.usage)
    return await client.choose_many(
        model=config.model, state=state, questions=questions, timeout_seconds=config.timeout_seconds
    )


async def _record_charge(
    tracker: TrackingContext,
    charge: DecisionCharge,
    config: DecisionConfiguration,
    usage: JevUsage,
    started_at: float,
    started: float,
    rate: float,
    failure: str | None,
) -> None:
    """Record a known bill exactly once, preserving it through cancellation."""
    await _complete_charge(
        tracker.record_node_tokens(
            node_name=f"jev_{usage.value}",
            model_name=charge.model,
            prompt_tokens=charge.input_tokens,
            completion_tokens=charge.output_tokens,
            cached_tokens=0,
            cache_write_tokens=0,
            cost_usd=charge.cost_usd,
            cost_eur=charge.cost_eur,
            usd_to_eur_rate=Decimal(str(rate)),
            duration_ms=(perf_counter() - started) * 1000,
            call_type="decision",
            started_at=started_at,
            llm_type=JEV_USAGES[usage].llm_type,
            status="error" if failure else "success",
            failure_kind=failure,
            params=capture_inference_params({"model": config.model}, declared_provider="typesafe"),
            requested_model=config.model,
        )
    )


def _log_decision_completion(
    *,
    run_id: str,
    usage: JevUsage,
    requested_model: str,
    reported_model: str | None,
    failure: str | None,
    invalid_response_reason: InvalidResponseReason | None,
    status_code: int | None,
    started: float,
    counters: DecisionUsage | None,
    charge: DecisionCharge | None,
) -> None:
    """Publish bounded operational metadata without state or answer content."""
    logger.info(
        "jev_decision_completed",
        run_id=run_id,
        usage=usage.value,
        requested_model=requested_model,
        reported_model=reported_model,
        outcome=failure or "success",
        invalid_response_reason=invalid_response_reason,
        status_code=status_code,
        duration_ms=(perf_counter() - started) * 1000,
        input_tokens=counters.input_tokens if counters else None,
        output_tokens=counters.output_tokens if counters else None,
        cost_eur=charge.cost_eur if charge else None,
    )


async def _execute_decision(
    *,
    config: DecisionConfiguration,
    usage: JevUsage,
    user_id: UUID,
    run_id: str,
    state: JsonValue,
    questions: dict[str, ChoiceQuestion],
) -> DecisionAttempt:
    """Execute an authorized snapshot once, closing its accounting and diagnostic."""
    question = questions["selection"] if set(questions) == {"selection"} else questions
    diagnostic = await begin_trace(
        user_id=user_id,
        usage=usage,
        run_id=run_id,
        model=config.model,
        state=state,
        question=question,
    )
    started_at, started = time(), perf_counter()
    rate = get_cached_usd_eur_rate()
    answers, counters, model, failure = {}, None, config.model, None
    charge = None
    response_answer, status_code = None, None
    invalid_response_reason = None
    reported_model: str | None = None
    action: JevAction = "pending"
    interrupted: asyncio.CancelledError | None = None
    try:
        async with _decision_tracker(run_id, user_id) as tracker:
            async with httpx.AsyncClient() as http:
                try:
                    result = await _call_native(
                        TypeSafeClient(http, config.api_key.get_secret_value()),
                        config,
                        state,
                        questions,
                    )
                    answers, counters, model = result.answers, result.usage, result.model
                    response_answer = (
                        result.answers["selection"]
                        if isinstance(question, ChoiceQuestion)
                        else result.answers
                    )
                    reported_model = result.model
                    if model != config.model:
                        answers, failure = {}, "unexpected_model"
                except (TypeSafeError, TypeSafeCancelledError) as exc:
                    counters, model, failure = exc.usage, exc.model or config.model, exc.code
                    status_code = exc.status_code
                    reported_model = exc.model
                    invalid_response_reason = exc.reason
                    interrupted = _received_interruption(exc)
                # No awaited cleanup may intervene between receipt of a bill
                # and its protected recording: closing HTTP can be cancelled too.
                if counters is not None:
                    usd = token_cost_usd(
                        config.price,
                        counters.input_tokens,
                        counters.output_tokens,
                        0,
                        datetime.fromtimestamp(started_at, UTC),
                    )
                    charge = DecisionCharge(
                        model=model,
                        input_tokens=counters.input_tokens,
                        output_tokens=counters.output_tokens,
                        cost_usd=usd,
                        cost_eur=usd * rate,
                    )
                    await _record_charge(
                        tracker, charge, config, usage, started_at, started, rate, failure
                    )
                _propagate_interruption(interrupted)
    except asyncio.CancelledError:
        action, failure = "cancelled", "cancelled"
        raise
    except Exception:
        action, failure = "aborted", "processing_error"
        raise
    finally:
        _log_decision_completion(
            run_id=run_id,
            usage=usage,
            requested_model=config.model,
            reported_model=reported_model,
            failure=failure,
            invalid_response_reason=invalid_response_reason,
            status_code=status_code,
            started=started,
            counters=counters,
            charge=charge,
        )
        diagnostic = await finish_trace(
            user_id,
            diagnostic,
            answer=response_answer,
            question=question,
            reported_model=reported_model,
            duration_ms=(perf_counter() - started) * 1000,
            outcome=failure or "success",
            action=action,
            status_code=status_code,
            counters=counters,
            cost_eur=charge.cost_eur if charge else None,
            invalid_response_reason=invalid_response_reason,
        )
    return DecisionAttempt(
        answer=answers.get("selection"),
        answers=answers,
        charge=charge,
        outcome=failure or "success",
        diagnostic=diagnostic,
    )
