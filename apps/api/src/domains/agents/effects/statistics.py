"""What the five records look like, as figures (ADR-263).

A register a person can only read row by row is a register nobody reads. These
aggregates are what turns eight months of rows into an answer to « what has this
assistant been doing, and at what cost ».

Four rules, and each of them is one of this programme's own doctrines applied
to a chart rather than to a file:

- **Every count is EXACT** — an aggregate over the whole filtered set, never
  the length of a page (ADR-185). A chart is a claim, and a claim is exact or
  it does not exist.
- **Every axis is BOUNDED.** Free-text fields are collapsed
  (``statistics_labels``) before they can become a label; the rest is a top-N
  with the remainder counted under one explicit « other », never dropped.
- **Nothing is computed in the browser.** The aggregation is SQL over indexed
  columns; a client that fetched rows to count them would download the very
  content these surfaces exist not to move around.
- **The scope is a parameter of the QUERY, never of the render.** One
  implementation serves a reader asking about themselves and an operator asking
  about one, several or every account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import (
    AgentDecision,
    AgentEffect,
    AgentIntegrityEvent,
    AgentTreatment,
)
from src.domains.agents.effects.statistics_labels import collapse_node_name, collapse_tool_name
from src.domains.agents.effects.treatment_labels import treatment_domain
from src.domains.chat.models import TokenUsageLog

#: How many bars a categorical chart shows before the rest is folded into one.
#: Beyond this a chart stops being read and starts being scrolled — and the
#: remainder is COUNTED, never dropped, so the total still adds up.
TOP_N: int = 12

#: What the folded remainder is called.
OTHER = "other"


class SeriesKind(str, Enum):
    """What the bars of a series draw, and therefore what a total may mean.

    A figure printed beside bars is a claim the reader can check by adding them
    up — so a series whose bars are not plain counts must SAY so, rather than
    wear the same badge and be wrong in a way only arithmetic reveals.

    ``COUNT``: one measure per bar; the total is their sum.
    ``STACKED``: two measures on one bar; the total is the sum of BOTH, which
        is what the bar's length draws.
    ``AVERAGE``: each bar is a mean; a sum of means is not a quantity, so the
        total is the mean over the whole set, WEIGHTED by observations.
    """

    COUNT = "count"
    STACKED = "stacked"
    AVERAGE = "average"


@dataclass(frozen=True)
class Slice:
    """One bar: a label and its exact count.

    Attributes:
        label: A bounded value — never free text.
        count: The exact number of rows.
        secondary: A second measure on the same bar (completion tokens beside
            prompt tokens, say), when the chart carries one.
    """

    label: str
    count: int
    secondary: int = 0


@dataclass(frozen=True)
class Series:
    """One chart's worth of bars, with what it left out stated.

    Attributes:
        slices: The bars, largest first.
        total: The EXACT figure for the whole filtered set — including whatever
            the top-N folded away. What it MEANS is :attr:`kind`: a sum for
            counts and stacks, a weighted mean for averages.
        kind: What the bars draw, so a reader is never left to assume.
    """

    slices: list[Slice] = field(default_factory=list)
    total: int = 0
    kind: SeriesKind = SeriesKind.COUNT


@dataclass(frozen=True)
class RegisterStatistics:
    """Every series the surfaces draw.

    Named after the question each answers rather than after its table: a reader
    asks « which models », not « which rows of token_usage_logs ».
    """

    calls_by_model: Series
    calls_by_node: Series
    tokens_by_model: Series
    consultations_by_domain: Series
    consultation_latency_by_tool: Series
    actions_by_status: Series
    turns_by_outcome: Series
    turns_by_mode: Series
    integrity_by_kind: Series
    activity_by_day: Series


def _scoped(statement: Select[Any], column: Any, user_ids: list[uuid.UUID] | None) -> Select[Any]:
    """Narrow a query to the accounts asked about.

    Args:
        statement: The query.
        column: Its account column.
        user_ids: The accounts, or None for every one of them.

    Returns:
        The narrowed query. ``None`` means the whole instance on purpose: an
        operator asking about the instance is asking about the instance.
    """
    return statement if user_ids is None else statement.where(column.in_(user_ids))


def _period(column: Any, since: datetime | None, until: datetime | None) -> list[Any]:
    """The half-open period clause, spelled once for five tables.

    Args:
        column: The table's own timestamp.
        since: Inclusive lower bound.
        until: Exclusive upper bound.

    Returns:
        The conditions.
    """
    clauses = []
    if since is not None:
        clauses.append(column >= since)
    if until is not None:
        clauses.append(column < until)
    return clauses


def _mean(total: int, observations: int) -> int:
    """A mean, rounded, and never a division by nothing."""
    return round(total / observations) if observations else 0


def _fold(
    rows: list[tuple[str, int, int]],
    *,
    top: int = TOP_N,
    kind: SeriesKind = SeriesKind.COUNT,
) -> Series:
    """Turn raw grouped rows into a bounded series.

    The two numbers of each row are read according to ``kind``: a count and a
    second measure for :attr:`SeriesKind.COUNT` and
    :attr:`SeriesKind.STACKED`, but a TOTAL and its OBSERVATIONS for
    :attr:`SeriesKind.AVERAGE` — because averaging is the one fold that cannot
    be done from already-averaged values.

    Args:
        rows: The grouped rows, in any order.
        top: How many bars to keep.
        kind: What the bars draw.

    Returns:
        The series, largest first, with the remainder folded under ``other`` —
        never dropped, so the badge still describes the whole set.
    """
    if kind is SeriesKind.AVERAGE:
        return _fold_averages(rows, top=top)

    ordered = sorted(rows, key=lambda row: row[1], reverse=True)
    kept = [
        Slice(label=label, count=count, secondary=extra) for label, count, extra in ordered[:top]
    ]
    rest = ordered[top:]
    if rest:
        kept.append(
            Slice(
                label=OTHER,
                count=sum(row[1] for row in rest),
                secondary=sum(row[2] for row in rest),
            )
        )
    total = sum(row[1] for row in ordered)
    if kind is SeriesKind.STACKED:
        # The bar's LENGTH is both measures; a total counting one of them sits
        # beside bars it is shorter than, and the reader's check fails.
        total += sum(row[2] for row in ordered)
    return Series(slices=kept, total=total, kind=kind)


def _fold_averages(rows: list[tuple[str, int, int]], *, top: int) -> Series:
    """Fold ``(label, total, observations)`` rows into a series of means.

    Args:
        rows: One row per group, carrying the SUM and the number of
            observations rather than a pre-computed mean.
        top: How many bars to keep — the slowest ones, which is the question
            this chart is opened to answer.

    Returns:
        The series. The folded bar is the mean of what it folded, and the badge
        is the mean over everything, both weighted by observations.
    """
    ordered = sorted(rows, key=lambda row: _mean(row[1], row[2]), reverse=True)
    kept = [
        Slice(label=label, count=_mean(total, observations))
        for label, total, observations in ordered[:top]
    ]
    rest = ordered[top:]
    if rest:
        kept.append(
            Slice(
                label=OTHER,
                count=_mean(sum(row[1] for row in rest), sum(row[2] for row in rest)),
            )
        )
    return Series(
        slices=kept,
        total=_mean(sum(row[1] for row in ordered), sum(row[2] for row in ordered)),
        kind=SeriesKind.AVERAGE,
    )


async def _grouped(
    db: AsyncSession,
    statement: Select[Any],
    *,
    relabel: Any = None,
    kind: SeriesKind = SeriesKind.COUNT,
) -> Series:
    """Run one grouped query and fold it.

    Args:
        db: The session.
        statement: A SELECT of ``(label, count)`` or ``(label, count, secondary)``.
        relabel: Applied to each label before folding — the seam where a free
            text field is collapsed to a bounded one, in Python because the
            collapsing rule must be the SAME one the exports use.
        kind: What the bars draw. The merge below adds the two raw numbers
            whatever the kind, which is what makes an average of a collapsed
            group correct: sums and observations add, means do not.

    Returns:
        The series.
    """
    result = await db.execute(statement)
    merged: dict[str, tuple[int, int]] = {}
    for row in result.all():
        label = str(relabel(row[0]) if relabel else (row[0] if row[0] is not None else "unknown"))
        count = int(row[1] or 0)
        extra = int(row[2] or 0) if len(row) > 2 else 0
        previous = merged.get(label, (0, 0))
        # Collapsing can map several stored values onto one label; adding them
        # here is what keeps the folded bar's count true.
        merged[label] = (previous[0] + count, previous[1] + extra)
    return _fold([(label, count, extra) for label, (count, extra) in merged.items()], kind=kind)


async def register_statistics(
    db: AsyncSession,
    *,
    user_ids: list[uuid.UUID] | None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> RegisterStatistics:
    """Every figure the surfaces draw, for one scope and one period.

    Args:
        db: The session.
        user_ids: The accounts, or None for the whole instance.
        since: Inclusive lower bound.
        until: Exclusive upper bound.

    Returns:
        The statistics. Ten queries, all grouped aggregates over indexed
        columns — never a row fetch.
    """
    inference = _period(TokenUsageLog.created_at, since, until)
    treatments = _period(AgentTreatment.occurred_at, since, until)
    effects = _period(AgentEffect.claimed_at, since, until)
    decisions = _period(AgentDecision.started_at, since, until)
    integrity = _period(AgentIntegrityEvent.occurred_at, since, until)

    return RegisterStatistics(
        calls_by_model=await _grouped(
            db,
            _scoped(
                select(TokenUsageLog.model_name, func.count()).where(*inference),
                TokenUsageLog.user_id,
                user_ids,
            ).group_by(TokenUsageLog.model_name),
        ),
        calls_by_node=await _grouped(
            db,
            _scoped(
                select(TokenUsageLog.node_name, func.count()).where(*inference),
                TokenUsageLog.user_id,
                user_ids,
            ).group_by(TokenUsageLog.node_name),
            relabel=collapse_node_name,
        ),
        tokens_by_model=await _grouped(
            db,
            _scoped(
                select(
                    TokenUsageLog.model_name,
                    func.coalesce(func.sum(TokenUsageLog.prompt_tokens), 0),
                    func.coalesce(func.sum(TokenUsageLog.completion_tokens), 0),
                ).where(*inference),
                TokenUsageLog.user_id,
                user_ids,
            ).group_by(TokenUsageLog.model_name),
            kind=SeriesKind.STACKED,
        ),
        consultations_by_domain=await _grouped(
            db,
            _scoped(
                select(AgentTreatment.tool_name, func.count()).where(*treatments),
                AgentTreatment.user_id,
                user_ids,
            ).group_by(AgentTreatment.tool_name),
            # The DOMAIN, not the tool: the consultation register's own
            # vocabulary is 31 nouns a reader understands, and a third-party
            # MCP tool collapses into one of them rather than widening the
            # axis. The tool name gets its own chart beside this one, where it
            # answers a technical question instead of a human one.
            relabel=treatment_domain,
        ),
        consultation_latency_by_tool=await _grouped(
            db,
            _scoped(
                select(
                    AgentTreatment.tool_name,
                    func.coalesce(func.sum(AgentTreatment.duration_ms), 0),
                    func.count(),
                ).where(*treatments),
                AgentTreatment.user_id,
                user_ids,
            ).group_by(AgentTreatment.tool_name),
            # A third-party server's own tool name is not ours to put on an
            # axis — least of all on the operator's cross-account screen, where
            # it would list the servers one account installed (ADR-255).
            relabel=collapse_tool_name,
            kind=SeriesKind.AVERAGE,
        ),
        actions_by_status=await _grouped(
            db,
            _scoped(
                select(AgentEffect.status, func.count()).where(*effects),
                AgentEffect.user_id,
                user_ids,
            ).group_by(AgentEffect.status),
            relabel=lambda value: str(getattr(value, "value", value)),
        ),
        turns_by_outcome=await _grouped(
            db,
            _scoped(
                select(AgentDecision.outcome, func.count()).where(*decisions),
                AgentDecision.user_id,
                user_ids,
            ).group_by(AgentDecision.outcome),
            relabel=lambda value: str(getattr(value, "value", value)),
        ),
        turns_by_mode=await _grouped(
            db,
            _scoped(
                select(AgentDecision.execution_mode, func.count()).where(*decisions),
                AgentDecision.user_id,
                user_ids,
            ).group_by(AgentDecision.execution_mode),
        ),
        integrity_by_kind=await _grouped(
            db,
            _scoped(
                select(AgentIntegrityEvent.kind, func.count()).where(*integrity),
                AgentIntegrityEvent.user_id,
                user_ids,
            ).group_by(AgentIntegrityEvent.kind),
        ),
        activity_by_day=await _daily(db, user_ids=user_ids, since=since, until=until),
    )


async def _daily(
    db: AsyncSession,
    *,
    user_ids: list[uuid.UUID] | None,
    since: datetime | None,
    until: datetime | None,
) -> Series:
    """Turns per day, as a chronology.

    The one series that is NOT largest-first: a timeline read by size is not a
    timeline. It is sorted here and the folding is skipped, because a day is a
    bounded label by construction and the period is what bounds the count.

    Args:
        db: The session.
        user_ids: The accounts, or None for the instance.
        since: Inclusive lower bound.
        until: Exclusive upper bound.

    Returns:
        One slice per day that had activity, oldest first.
    """
    day = func.date_trunc("day", AgentDecision.started_at)
    statement = _scoped(
        select(day, func.count())
        .where(*_period(AgentDecision.started_at, since, until))
        .group_by(day)
        .order_by(day),
        AgentDecision.user_id,
        user_ids,
    )
    rows = (await db.execute(statement)).all()
    slices = [
        Slice(label=row[0].date().isoformat(), count=int(row[1] or 0))
        for row in rows
        if row[0] is not None
    ]
    return Series(slices=slices, total=sum(one.count for one in slices))


__all__ = [
    "OTHER",
    "TOP_N",
    "RegisterStatistics",
    "Series",
    "SeriesKind",
    "Slice",
    "register_statistics",
]
