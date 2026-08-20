"""Pure merge/sort/pagination for the activity timeline (Lot 1-A1).

I/O-free by design (same doctrine as ``domains/memories/retention.py``):
the service fetches per-source event lists, this module merges them
deterministically. Exact per-kind totals are computed separately by SQL
aggregates (ADR-185: counts are exact or absent; rows only are paged).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domains.activity.schemas import ActivityEvent, MergedTimeline


def merge_timeline(
    events_by_kind: Mapping[str, Sequence[ActivityEvent]],
    *,
    offset: int,
    limit: int,
) -> MergedTimeline:
    """Merge per-source events into one deterministic page.

    Ordering is newest first; equal timestamps fall back to (kind, ref_id)
    ascending so two calls over the same data always paginate identically.

    Args:
        events_by_kind: Events grouped by source kind.
        offset: Rows to skip (>= 0).
        limit: Page size (>= 1).

    Returns:
        The requested page with ``has_more`` and the merged row count.

    Raises:
        ValueError: On negative offset or non-positive limit.
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

    merged = sorted(
        (event for events in events_by_kind.values() for event in events),
        key=lambda e: (-e.occurred_at.timestamp(), e.kind, e.ref_id),
    )
    page = merged[offset : offset + limit]
    return MergedTimeline(
        events=list(page),
        has_more=offset + limit < len(merged),
        total_fetched=len(merged),
    )
