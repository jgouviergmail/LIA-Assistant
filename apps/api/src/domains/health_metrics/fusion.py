"""What a kind's samples count for — the one door every reader counts through.

Two devices measuring the same walk send intervals that overlap without being
identical. Measured 2026-11-14 on the production instance: an iPhone and an
Apple Watch both reaching the Shortcut, both labelled ``iphone``, 161
overlapping pairs in one day (137 of them nested: a long phone sample holding
short watch ones), a raw sum of 23 309 steps where Apple Health showed 14 402
and the overlap-free count was about 13 300. The ingestion merge only meets
IDENTICAL intervals within one batch (``MergeStrategy``); the overlap is a
property of the stored history, so it is resolved where the history is READ.

A kind's :class:`~src.domains.health_metrics.kinds.OverlapRule` says how:

- ``KEEP_ALL`` — every sample is an observation of its own; the door returns
  the samples as stored.
- ``MAX_RATE`` — a count spread evenly over its interval. The samples are
  grouped into CLUSTERS (chains of overlapping intervals, in start order), each
  cluster is cut at every sample boundary into SLICES, and every slice counts
  the highest rate among the samples covering it, times its length. One walk
  measured twice counts once; a sample that overlaps nothing comes out whole.

The door returns rows shaped like samples (``date_start``, ``date_end``,
``value``) so a reader groups them by bucket as it grouped samples. A row
belongs to the window of its START — the existing rule for samples, kept for
slices. To cut every slice the same way whichever window reads it, the door
reads the samples starting up to :data:`HEALTH_METRICS_FUSION_HORIZON_HOURS`
before and after the window; adjacent windows then add up exactly.

The raw rows are never rewritten: correcting the rule corrects the history.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Float, and_, case, cast, extract, func, select, union
from sqlalchemy.sql import Subquery

from src.core.constants import HEALTH_METRICS_FUSION_HORIZON_HOURS
from src.domains.health_metrics.kinds import OverlapRule, get_spec
from src.domains.health_metrics.models import HealthSample

__all__ = ["counted_samples"]

#: A sample whose end does not follow its start is read as one second long: a
#: count needs a duration to be spread over, and nothing forbids such a row.
_SHORTEST_SAMPLE = timedelta(seconds=1)


def counted_samples(user_id: UUID, kind: str, *, from_ts: datetime, to_ts: datetime) -> Subquery:
    """The samples of a kind as every reader counts them, over ``[from_ts, to_ts)``.

    Args:
        user_id: The owner.
        kind: A registered kind.
        from_ts: Inclusive window start; a row belongs to the window of its start.
        to_ts: Exclusive window end.

    Returns:
        A subquery with the columns ``date_start``, ``date_end`` and ``value``:
        the stored samples for a ``KEEP_ALL`` kind (integer values), the fused
        slices for a ``MAX_RATE`` kind (fractional values, summed then rounded
        by the reader).

    Raises:
        KeyError: The kind is not registered.
    """
    if get_spec(kind).overlap_rule is OverlapRule.KEEP_ALL:
        return (
            select(
                HealthSample.date_start.label("date_start"),
                HealthSample.date_end.label("date_end"),
                HealthSample.value.label("value"),
            )
            .where(
                HealthSample.user_id == user_id,
                HealthSample.kind == kind,
                HealthSample.date_start >= from_ts,
                HealthSample.date_start < to_ts,
            )
            .subquery("counted")
        )
    return _max_rate_slices(user_id, kind, from_ts=from_ts, to_ts=to_ts)


def _max_rate_slices(user_id: UUID, kind: str, *, from_ts: datetime, to_ts: datetime) -> Subquery:
    """Overlap-free slices of a ``MAX_RATE`` kind, the highest rate on each.

    Args:
        user_id: The owner.
        kind: A ``MAX_RATE`` kind.
        from_ts: Inclusive window start.
        to_ts: Exclusive window end.

    Returns:
        The slices starting in the window, as ``date_start``, ``date_end``,
        ``value``.
    """
    horizon = timedelta(hours=HEALTH_METRICS_FUSION_HORIZON_HOURS)
    end = func.greatest(HealthSample.date_end, HealthSample.date_start + _SHORTEST_SAMPLE)
    seconds = cast(extract("epoch", end - HealthSample.date_start), Float)
    candidates = (
        select(
            HealthSample.id.label("sample_id"),
            HealthSample.date_start.label("start"),
            end.label("end"),
            (cast(HealthSample.value, Float) / seconds).label("rate"),
        )
        .where(
            HealthSample.user_id == user_id,
            HealthSample.kind == kind,
            HealthSample.date_start >= from_ts - horizon,
            HealthSample.date_start < to_ts + horizon,
        )
        .cte("candidates")
    )
    order = (candidates.c.start, candidates.c.end, candidates.c.sample_id)
    # A sample opens a cluster when it starts once every earlier one has ended.
    reach = func.max(candidates.c.end).over(order_by=order, rows=(None, -1))
    opened = select(
        candidates.c.sample_id,
        candidates.c.start,
        candidates.c.end,
        candidates.c.rate,
        case((reach.is_(None), 1), (candidates.c.start >= reach, 1), else_=0).label("opens"),
    ).cte("opened")
    clustered = select(
        opened.c.start,
        opened.c.end,
        opened.c.rate,
        func.sum(opened.c.opens)
        .over(order_by=(opened.c.start, opened.c.end, opened.c.sample_id), rows=(None, 0))
        .label("cluster"),
    ).cte("clustered")
    # Every boundary of a cluster, once: the slices run from one to the next.
    bounds = union(
        select(clustered.c.cluster, clustered.c.start.label("at")),
        select(clustered.c.cluster, clustered.c.end.label("at")),
    ).cte("bounds")
    slices = select(
        bounds.c.cluster,
        bounds.c.at.label("slice_start"),
        func.lead(bounds.c.at)
        .over(partition_by=bounds.c.cluster, order_by=bounds.c.at)
        .label("slice_end"),
    ).cte("slices")
    slice_seconds = cast(extract("epoch", slices.c.slice_end - slices.c.slice_start), Float)
    return (
        select(
            slices.c.slice_start.label("date_start"),
            slices.c.slice_end.label("date_end"),
            (func.max(clustered.c.rate) * slice_seconds).label("value"),
        )
        .select_from(
            slices.join(
                clustered,
                and_(
                    clustered.c.cluster == slices.c.cluster,
                    clustered.c.start <= slices.c.slice_start,
                    clustered.c.end >= slices.c.slice_end,
                ),
            )
        )
        .where(
            slices.c.slice_end.is_not(None),
            slices.c.slice_start >= from_ts,
            slices.c.slice_start < to_ts,
        )
        .group_by(slices.c.cluster, slices.c.slice_start, slices.c.slice_end)
        .subquery("counted")
    )
