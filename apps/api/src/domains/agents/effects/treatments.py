"""Collecting what a turn CONSULTED, without making it pay for it (ADR-263).

The companion of the effect ledger, and deliberately its opposite in shape.

An ACTION is claimed before it happens, in its own committed transaction,
because an effect that is not recorded before it occurs can never be proven
afterwards. A CONSULTATION needs none of that: it is observed after the fact,
and observing must stay free — the measured property that makes the gate
acceptable on the hot path (0.64 µs and **zero database session** on a read) is
exactly what a row-per-call would destroy.

So the turn's parent publishes a **live list** and the gate only appends to it;
one batch is written at the end (:mod:`treatment_recorder`).

Why a live list and not ``ContextVar.set()`` inside the call: a ``set`` made in
a child task does not propagate to its parent, so a collector built that way
would work in ReAct (sequential awaits) and **silently lose the pipeline**
(``asyncio.gather``) — a register that lies by omission, on one execution mode
only. Appending to a list the parent published crosses both shapes, because the
LIST is what is shared, not the variable.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from src.domains.agents.effects.integrity import IntegrityKind, record_integrity_event

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Treatment:
    """One capability consulted by one turn.

    The field set IS the privacy contract: which capability, when, how long,
    with which outcome — never what was asked. « Searched Marie's emails »
    would reveal a search nobody asked to have recorded, where « sent an email
    to Marie » records an act the user requested.

    Attributes:
        user_id: Owner of the register the row belongs to.
        thread_id: Conversation the consultation happened in.
        run_id: Turn that consulted, so « this turn » is one indexed query.
        source: user | scheduled | subagent.
        execution_mode: pipeline | react | subagent.
        tool_name: The capability consulted.
        mutation_policy: Its declared policy, or None when it declares none.
        outcome: ``ok`` or ``failed`` — what was observed, nothing more.
        duration_ms: Wall-clock duration of the call.
        occurred_at: When the call returned (UTC).
    """

    user_id: str
    thread_id: str
    run_id: str
    source: str
    execution_mode: str
    tool_name: str
    mutation_policy: str | None
    outcome: str
    duration_ms: int
    occurred_at: datetime


@dataclass(slots=True)
class _Collector:
    """The live list a turn publishes, and the run it files rows under."""

    rows: list[Treatment]
    run_id: str | None


_COLLECTOR: ContextVar[_Collector | None] = ContextVar("effect_treatment_collector", default=None)

#: What a turn may record before we consider the register runaway rather than
#: informative. A ReAct turn does tens of calls; ten thousand is a loop that
#: escaped, and the rows past the cap teach nothing the first ten thousand do
#: not — while the batch insert would grow without bound.
MAX_TREATMENTS_PER_TURN = 10_000


@contextmanager
def treatment_collector(*, run_id: str | None = None) -> Iterator[list[Treatment]]:
    """Publish a live list for the duration of a turn.

    Args:
        run_id: The turn's run id. Rows fall back to the thread when it is
            absent, exactly as the effect ledger does — one convention, so a
            reader never has to know which register it is paging.

    Yields:
        The list the gate appends to, readable by the caller on exit.
    """
    collector = _Collector(rows=[], run_id=run_id)
    token = _COLLECTOR.set(collector)
    try:
        yield collector.rows
    finally:
        _COLLECTOR.reset(token)


def collected_treatments() -> Sequence[Treatment]:
    """What has been collected so far, or nothing outside a turn."""
    collector = _COLLECTOR.get()
    return () if collector is None else tuple(collector.rows)


def observe(treatment: Treatment) -> None:
    """Append one consultation to the turn's live list.

    Args:
        treatment: The row to keep.
    """
    collector = _COLLECTOR.get()
    if collector is None:
        return
    if len(collector.rows) >= MAX_TREATMENTS_PER_TURN:
        return
    collector.rows.append(treatment)


def record_treatment(
    tool_name: str,
    mutation_policy: str | None,
    *,
    succeeded: bool,
    duration_ms: int,
) -> None:
    """Observe one consultation — and never let observing break what it observes.

    The whole body is best-effort: this runs on the read path of every tool
    call, and a register that can take a working assistant down is worse than
    the gap it closes.

    Args:
        tool_name: The capability that was consulted.
        mutation_policy: Its declared policy, or None when it declares none.
        succeeded: Whether the capability answered.
        duration_ms: Wall-clock duration of the call.
    """
    if _COLLECTOR.get() is None:
        # Outside a turn (a script, a test, a boot probe) there is nothing to
        # record and no gap. INSIDE one, a missing collector means a register
        # is being lost — count it, or a second entry point drops consultations
        # with nothing to notice (ADR-148's failure mode).
        _count_lost_register()
        return
    try:
        row = _build(tool_name, mutation_policy, succeeded=succeeded, duration_ms=duration_ms)
        if row is not None:
            observe(row)
    except Exception:  # noqa: BLE001 - observing must never break the observed
        logger.debug("treatment_not_collected", tool_name=tool_name, exc_info=True)


def _count_lost_register() -> None:
    """Signal a turn whose consultations nobody is collecting.

    Read cheaply and only on the path that already returned early: under a
    published collector this is never reached, so a normal turn pays nothing.
    """
    from src.domains.agents.context.runtime_context import runtime_context_if_running

    try:
        context = runtime_context_if_running()
        if context is None:
            return
        from src.infrastructure.observability.metrics_effects import (
            treatments_uncollected_total,
        )

        mode = str(getattr(context, "execution_mode", "unknown"))
        treatments_uncollected_total.labels(execution_mode=mode).inc()
        logger.warning("treatment_register_not_open", execution_mode=mode)
        # The metric counts; the row says WHOSE turn (ADR-263 lot 8). Scheduled
        # as a task rather than awaited: this helper is called from the gate's
        # hot path and must not add a database round trip to a tool call.
        from src.infrastructure.async_utils import safe_fire_and_forget

        safe_fire_and_forget(
            record_integrity_event(
                IntegrityKind.TREATMENTS_UNCOLLECTED,
                user_id=getattr(context, "user_id", None),
                run_id=getattr(context, "run_id", None) or getattr(context, "thread_id", None),
                detail=mode,
            ),
            name="integrity_treatments_uncollected",
        )
    except Exception:  # noqa: BLE001 - observing must never break the observed
        logger.debug("treatment_gap_not_counted", exc_info=True)


def _build(
    tool_name: str,
    mutation_policy: str | None,
    *,
    succeeded: bool,
    duration_ms: int,
) -> Treatment | None:
    """Build the row from the authority in force, or None when there is none.

    Args:
        tool_name: The capability that was consulted.
        mutation_policy: Its declared policy.
        succeeded: Whether the capability answered.
        duration_ms: Wall-clock duration.

    Returns:
        The row, or None when no run context names a user — nothing can be
        written to a register whose every row belongs to someone.
    """
    from src.domains.agents.context.runtime_context import runtime_context_if_running
    from src.domains.agents.effects.scope import current_scope

    context = runtime_context_if_running()
    if context is None:
        return None

    collector = _COLLECTOR.get()
    scope = current_scope()
    run_id = (collector.run_id if collector else None) or (
        scope.run_id if scope else context.thread_id
    )
    source = scope.source if scope else ("scheduled" if context.is_automated_source else "user")
    return Treatment(
        user_id=str(context.user_id),
        thread_id=str(context.thread_id),
        run_id=str(run_id),
        source=source,
        execution_mode=str(context.execution_mode),
        tool_name=tool_name,
        mutation_policy=mutation_policy,
        outcome="ok" if succeeded else "failed",
        duration_ms=duration_ms,
        occurred_at=datetime.now(UTC),
    )
