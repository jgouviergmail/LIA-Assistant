"""Parallel observation only: the original extractor always runs and owns all writes."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from uuid import UUID, uuid4

import structlog

from src.core.context import current_tracker
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_models import ContextPreview, context_preview
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.metrics_jev import jev_decisions_total

logger = structlog.get_logger(__name__)


@dataclass
class ExtractionObservation:
    """Bounded comparison with the existing model's proposal, before write validation."""

    result: ContextPreview | None = None
    usage: JevUsage | None = None
    owner: UUID | None = None
    run_id: str = ""
    task: asyncio.Task[DecisionAttempt] | None = None

    def start(self, prompt: str) -> None:
        if self.owner is not None and self.usage is not None and self.task is None:
            self.task = asyncio.create_task(_request(self.usage, self.owner, self.run_id, prompt))

    def set_output(self, output: str) -> None:
        try:
            value = json.loads(output)
            self.result = context_preview(value)
        except ValueError, TypeError, RecursionError:
            self.result = context_preview(output)


async def _request(usage: JevUsage, owner: UUID, run_id: str, prompt: str) -> DecisionAttempt:
    # Post-response tasks may outlive the turn's ambient tracker. The native
    # runtime owns and commits a separate ledger scope, attributed to this run.
    token = current_tracker.set(None)
    try:
        return await choose_with_jev(
            usage=usage,
            user_id=owner,
            run_id=run_id,
            state={"extraction_kind": usage.value, "extractor_prompt": prompt},
            question=ChoiceQuestion.model_validate_json(
                load_prompt("jev_extraction_question", version="v1")
            ),
        )
    except Exception as exc:
        # An observer cannot veto the baseline; that path retains its own quota guard.
        logger.warning("jev_observation_failed", usage=usage.value, error_type=type(exc).__name__)
        return DecisionAttempt(outcome="unavailable")
    finally:
        current_tracker.reset(token)


async def _record(
    owner: UUID, usage: JevUsage, attempt: DecisionAttempt, observed: ExtractionObservation
) -> None:
    try:
        await record_action(
            owner,
            attempt.diagnostic,
            action="observed",
            outcome=attempt.outcome,
            target="existing_extraction_unchanged",
            observed_result=observed.result,
        )
        jev_decisions_total.labels(
            usage=usage, outcome="observed" if attempt.answer is not None else attempt.outcome
        ).inc()
    except Exception as exc:
        logger.warning(
            "jev_observation_record_failed", usage=usage.value, error_type=type(exc).__name__
        )


@asynccontextmanager
async def observe_extraction(
    usage: JevUsage,
    user_id: str,
    run_id: str | None,
    prompt: str | None = None,
) -> AsyncIterator[ExtractionObservation]:
    """Join the observer before the extractor ends; preserve baseline cancellation/errors."""
    observed = ExtractionObservation()
    try:
        owner = UUID(user_id)
    except ValueError:
        yield observed
        return
    observed.owner = owner
    observed.usage = usage
    observed.run_id = run_id or f"jev_observe_{uuid4().hex}"
    if prompt is not None:
        observed.start(prompt)
    try:
        yield observed
    except BaseException:
        if observed.task is not None:
            observed.task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await observed.task
        raise
    else:
        if observed.task is not None:
            attempt = await observed.task
            await _record(owner, usage, attempt, observed)


_active_observation: ContextVar[ExtractionObservation | None] = ContextVar(
    "jev_extraction_observation", default=None
)


def start_extraction_observation(prompt: str) -> ExtractionObservation:
    """Capture the exact rendered prompt, without awaiting or delaying baseline work."""
    observation = _active_observation.get() or ExtractionObservation()
    observation.start(prompt)
    return observation


def observe_extractor[**P, R](
    usage: JevUsage,
    *,
    run_argument: str = "parent_run_id",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Own the observer for the COMPLETE extractor, including its ledger and writes."""

    def decorate(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        call_signature = signature(function)

        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            arguments = call_signature.bind(*args, **kwargs).arguments
            async with observe_extraction(
                usage, arguments["user_id"], arguments.get(run_argument)
            ) as observation:
                token = _active_observation.set(observation)
                try:
                    return await function(*args, **kwargs)
                finally:
                    _active_observation.reset(token)

        return wrapped

    return decorate
