"""The one door of what LIA does from the Tools (ADR-372).

A click asks a model on the instance's key, so whatever it is, it goes through here: both ceilings
asked before anything is read, the spend billed to the account whatever happens (ADR-272), each
source that was read filed on the same run (ADR-263), the outcome counted under closed labels and
told in the
workbench's stable words. Nothing here retries: a model that failed is said, and the person presses
again if they want to pay again (ADR-221).

An assist that served what was already held opened nothing and cost nothing: it files nothing, and
says so by carrying no usage.

No session is open here, and none is held across the model's answer (ADR-304): the account comes
as plain values, and a source's read goes through the Tools' own door.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import NoReturn, TypedDict
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
    TOOL_ASSIST_LLM_TYPE,
    TOOL_ASSIST_TASK_TYPE,
)
from src.core.exceptions import BaseAPIException
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.llm_usage import LLMUsage
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.tool_assists.catalogue import ASSISTS, AssistSpec, ToolAssist
from src.domains.workbench.errors import ASSIST_FAILED, ASSIST_PAUSED, ASSIST_QUOTA, refuse
from src.infrastructure.llm.token_capture import TokenCaptureHandler, captured_usage
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.observability.metrics_tool_assists import (
    tool_assist_duration_seconds,
    tool_assists_total,
)
from src.infrastructure.proactive.tracking import (
    bill_captured_usage,
    capture_spend_on_failure,
    generate_proactive_run_id,
)

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class AssistRun:
    """What one assist works with.

    Attributes:
        user_id: The account it runs for.
        language: The reader's language, canonical.
        config: What every model call hands the client: its callback bills the run.
        slot: The slot that answers it: what it is billed under, once a file has said
            how it must be read.
        sections: The sources the assist may open, as its spec declares them.
        read_sections: Those it did open: only these are filed.
        failed_sections: Those that did not answer.
        served: It answered on a ledger of its own (a voice): nothing was merely held.
    """

    user_id: UUID
    language: str
    config: RunnableConfig
    slot: str = TOOL_ASSIST_LLM_TYPE
    sections: tuple[str, ...] = ()
    read_sections: set[str] = field(default_factory=set)
    failed_sections: set[str] = field(default_factory=set)
    served: bool = False

    @property
    def opened(self) -> bool:
        """Whether a source of the person was read."""
        return bool(self.read_sections)

    @property
    def failed(self) -> bool:
        """Whether a read did not answer."""
        return bool(self.failed_sections)

    @asynccontextmanager
    async def reading(self, section: str | None = None) -> AsyncIterator[None]:
        """Say a source of the person is being read; a read that fails stays filed as failed.

        Args:
            section: The source, where the assist may open several; else its only one.

        Yields:
            Nothing; the caller reads its source inside the block.
        """
        read = (section,) if section else self.sections
        self.read_sections.update(read)
        try:
            yield
        except BaseException:
            self.failed_sections.update(read)
            raise


class _Bill(TypedDict):
    """What a capture is billed under, on success as on failure."""

    user_id: UUID
    task_type: str
    target_id: str
    model_name: str
    source: str
    run_id: str
    llm_type: str


@dataclass(frozen=True, slots=True)
class Assisted[T]:
    """An assist's answer and what it cost; no usage when nothing was spent on it now."""

    value: T
    usage: LLMUsage | None
    #: Nothing was read or spoken for it: it served what was already held.
    held: bool = False


def slot_model(slot: str) -> str:
    """The model a slot resolves to now: what a capture prices by default."""
    return str(get_llm_config_for_agent(settings, slot).model)


def count_assist(assist: str, outcome: str) -> None:
    """Count one outcome (closed labels: see ``metrics_tool_assists``)."""
    tool_assists_total.labels(assist=assist, outcome=outcome).inc()


async def run_assist[T](
    assist: ToolAssist,
    user_id: UUID,
    language: str,
    work: Callable[[AssistRun], Awaitable[T]],
) -> Assisted[T]:
    """Run one assist under the door's whole contract.

    Args:
        assist: What was asked.
        user_id: The account that asked: it pays and it is filed.
        language: The reader's language, canonical.
        work: The assist itself, handed its run.

    Returns:
        Its answer and what it cost.

    Raises:
        BaseAPIException: A workbench refusal, in the page's stable words.
    """
    started = perf_counter()
    # A cancellation escapes every handler below: the person left.
    outcome = "abandoned"
    spec = ASSISTS[assist]
    try:
        if spec.asks_a_model:
            await enforce_usage_limit(user_id, layer=TOOL_ASSIST_TASK_TYPE)
        done = await _accounted(assist, spec, user_id, language, work, started)
        outcome = "held" if done.held else "ok"
        return done
    except UsageLimitExceededError as limit:
        outcome = "quota"
        _refuse_ceiling(limit)
    except BaseAPIException:
        outcome = "refused"
        raise
    except Exception as failure:
        outcome = "failed"
        # The type alone: what a provider or a model said may quote the person's words.
        logger.warning("tool_assist_failed", assist=assist.value, error_type=type(failure).__name__)
        refuse(ASSIST_FAILED)
    finally:
        count_assist(assist.value, outcome)
        elapsed = perf_counter() - started
        tool_assist_duration_seconds.labels(assist=assist.value).observe(elapsed)
        logger.info(
            "tool_assist_done",
            assist=assist.value,
            outcome=outcome,
            duration_ms=int(elapsed * 1000),
        )


async def _accounted[T](
    assist: ToolAssist,
    spec: AssistSpec,
    user_id: UUID,
    language: str,
    work: Callable[[AssistRun], Awaitable[T]],
    started: float,
) -> Assisted[T]:
    """Run the work with its spend captured and what it read collected on one run."""
    capture = TokenCaptureHandler(slot_model(spec.slot))
    run_id = generate_proactive_run_id(TOOL_ASSIST_TASK_TYPE, assist.value)
    run = AssistRun(
        user_id=user_id,
        language=language,
        config=RunnableConfig(callbacks=[capture]),
        slot=spec.slot,
        sections=spec.sections,
    )

    def bill() -> _Bill:
        return _Bill(
            user_id=user_id,
            task_type=TOOL_ASSIST_TASK_TYPE,
            target_id=assist.value,
            model_name=slot_model(run.slot),
            source="user",
            run_id=run_id,
            llm_type=run.slot,
        )

    async with consultation_collector(run_id):
        try:
            try:
                value = await work(run)
            except BaseException:
                # Entered only now: the slot that answered is not known before the work.
                async with capture_spend_on_failure(capture, **bill()):
                    raise
            await bill_captured_usage(capture, **bill())
        finally:
            _file_read(run, spec, run_id, started)
    spent = capture.tokens_in or capture.tokens_out or capture.tokens_cache
    usage = captured_usage(capture, slot_model(run.slot)) if spent else None
    return Assisted(value, usage, held=usage is None and not run.served)


def _file_read(run: AssistRun, spec: AssistSpec, run_id: str, started: float) -> None:
    """File the sources the assist opened, each for itself; nothing when it opened none."""
    if not run.opened:
        return
    record_surface_consultations(
        surface=TOOL_ASSIST_TASK_TYPE,
        user_id=run.user_id,
        opened=[section for section in spec.sections if section in run.read_sections],
        failed=[section for section in spec.sections if section in run.failed_sections],
        duration_ms=int((perf_counter() - started) * 1000),
        run_id=run_id,
    )


def _refuse_ceiling(limit: UsageLimitExceededError) -> NoReturn:
    """Tell the instance's pause from the account's own ceiling."""
    if limit.error_code == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE:
        wait = (limit.headers or {}).get("Retry-After")
        refuse(ASSIST_PAUSED, **({"retry_after": int(wait)} if wait else {}))
    refuse(ASSIST_QUOTA)


__all__ = ["AssistRun", "Assisted", "count_assist", "run_assist", "slot_model"]
