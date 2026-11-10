"""Pure merge/sort/pagination for the activity timeline (Lot 1-A1).

I/O-free by design (same doctrine as ``domains/memories/retention.py``):
the service fetches per-source event lists, this module merges them
deterministically. Exact per-kind totals come from complete source reads
(ADR-185: counts are exact or absent; rows only are paged).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from functools import partial
from typing import Literal

from src.domains.activity.schemas import ActivityEvent, MergedTimeline


def _event_key(
    event: ActivityEvent, *, sort: Literal["recent", "oldest"]
) -> tuple[float, str, str]:
    """One order for both the displayed page and every source frontier."""
    instant = event.occurred_at.timestamp()
    return (-instant if sort == "recent" else instant, event.kind, event.ref_id)


def merge_timeline(
    events_by_kind: Mapping[str, Sequence[ActivityEvent]],
    *,
    offset: int,
    limit: int,
    sort: Literal["recent", "oldest"] = "recent",
    truncated_kinds: Set[str] = frozenset(),
) -> MergedTimeline:
    """Merge per-source events into one deterministic page.

    Ordering follows the requested direction; equal timestamps fall back to (kind, ref_id)
    ascending so two calls over the same data always paginate identically.

    Args:
        events_by_kind: Events grouped by source kind.
        offset: Rows to skip (>= 0).
        limit: Page size (>= 1).
        sort: Recent or oldest first, applied before pagination.
        truncated_kinds: Sources whose unreturned tail bounds the known prefix.

    Returns:
        The requested page with ``has_more`` and the merged row count.

    Raises:
        ValueError: On negative offset or non-positive limit.
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

    key = partial(_event_key, sort=sort)

    merged = sorted(
        (event for events in events_by_kind.values() for event in events),
        key=key,
    )
    if truncated_kinds:
        # Past the earliest exhausted source, an unseen row could sort before
        # any other source's next row. Offer only the prefix proved complete.
        pools = [events_by_kind.get(kind, ()) for kind in truncated_kinds]
        if any(not pool for pool in pools):
            merged = []
        else:
            boundary = min(max(key(event) for event in pool) for pool in pools)
            merged = [event for event in merged if key(event) <= boundary]
    page = merged[offset : offset + limit]
    return MergedTimeline(
        events=list(page),
        has_more=offset + limit < len(merged),
        total_fetched=len(merged),
    )
