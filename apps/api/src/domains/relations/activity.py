"""Exact relationship activity across existing sources and their manual aliases."""

from dataclasses import dataclass, field
from datetime import datetime

from src.domains.relations.identity import NO_MERGES, IdentityResolver
from src.domains.shared.aggregates import NameActivity


@dataclass
class _Bucket:
    """Exact activity accumulated for one normalized relationship key."""

    raw_names: set[str] = field(default_factory=set)
    open_loops_count: int = 0
    calls_count: int = 0
    peer_messages_count: int = 0
    sms_count: int = 0
    last_interaction_at: datetime | None = None

    def note_interaction(self, when: datetime | None) -> None:
        if when is None:
            return
        if self.last_interaction_at is None or when > self.last_interaction_at:
            self.last_interaction_at = when


def _touch(
    buckets: dict[str, _Bucket], item: NameActivity, resolver: IdentityResolver
) -> _Bucket | None:
    """Locate (or open) the bucket one aggregate row belongs to.

    Folding happens HERE and nowhere else: sources hand over raw spellings,
    and two spellings of the same person land in the same bucket — which is
    also how the confidence learns they disagreed.

    The resolver adds the merges the USER declared on top of the fold, so a
    merged relationship yields ONE bucket carrying both spellings.

    Args:
        buckets: Accumulator, keyed by identity.
        item: One source aggregate row.
        resolver: Folding + the user's merges.

    Returns:
        The bucket, or None when the name folds to nothing (never a phantom).
    """
    key = resolver.key(item.raw_name)
    if not key:
        return None
    bucket = buckets.setdefault(key, _Bucket())
    bucket.raw_names.add(item.raw_name.strip())
    bucket.note_interaction(item.last_at)
    return bucket


def _bucketize(
    loops: list[NameActivity],
    calls: list[NameActivity],
    messages: list[NameActivity],
    *,
    resolver: IdentityResolver = NO_MERGES,
    sms: list[NameActivity] | None = None,
) -> dict[str, _Bucket]:
    """Fold every source's exact aggregates into per-identity buckets.

    Args:
        loops: Open-commitment aggregates.
        calls: Call aggregates.
        messages: Relayed-message aggregates.
        resolver: Folding + the user's merges (defaults to no merge).

    Returns:
        One bucket per identity, keyed by canonical key.
    """
    buckets: dict[str, _Bucket] = {}
    for item in loops:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.open_loops_count += item.count
    for item in calls:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.calls_count += item.count
    for item in messages:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.peer_messages_count += item.count
    for item in sms or []:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.sms_count += item.count
    return buckets


def _spellings_for(
    aggregates: list[NameActivity],
    target_key: str,
    *,
    resolver: IdentityResolver = NO_MERGES,
) -> list[str]:
    """The raw spellings of one identity, as the sources store them.

    This is what lets the 360° view query by EXACT string while keeping the
    resolver the only authority on who is the same person — SQL never gets a
    second opinion. After a merge, the merged-away side still stores its OWN
    spelling, so it must appear here or its rows are invisible on the card.

    Args:
        aggregates: Source aggregate rows.
        target_key: Canonical identity key.
        resolver: Folding + the user's merges.

    Returns:
        Every raw spelling belonging to that identity.
    """
    return [item.raw_name for item in aggregates if resolver.key(item.raw_name) == target_key]


def _total_for(
    aggregates: list[NameActivity],
    target_key: str,
    *,
    resolver: IdentityResolver = NO_MERGES,
) -> int:
    """Exact number of rows one identity holds across all its spellings.

    Args:
        aggregates: Source aggregate rows.
        target_key: Canonical identity key.
        resolver: Folding + the user's merges.

    Returns:
        The exact total, merged halves included.
    """
    return sum(item.count for item in aggregates if resolver.key(item.raw_name) == target_key)
