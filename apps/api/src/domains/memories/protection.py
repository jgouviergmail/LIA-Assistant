"""What may never be deleted automatically (owner arbitration, 2026-09-10).

Every category of :class:`~src.domains.memories.models.MemoryCategory` holds a
FACT LIA inferred about the person, and may therefore be re-inferred, corrected
or forgotten by the machinery that maintains them. ``procedural`` does not: it
holds the standing instructions the person DICTATED about how LIA should work
for them (ADR-236) — "always answer me in French", "never call after 8 pm". A
sweep that drops one of those silently changes how the assistant behaves, and
nobody can point at the moment it happened.

**A directive is corrected, never deleted.** The rule is not "this row is
frozen" — that would also block the corrections that keep a directive true, and
it is why pinning was considered and rejected (pinned means user-LOCKED, and
the extractor already refuses to touch a pinned row at all). The rule is that a
directive **never leaves the active set without a successor**:

| Path | A directive |
|---|---|
| Retention sweep | never purged, whatever its score or age |
| Consolidation (destroys the loser of a pair) | never paired |
| Extractor `delete` | skipped, and said so |
| `invalidate_memory` (retire with no successor) | refused |
| `supersede_with_update` (retire WITH a successor) | allowed — this is a correction |
| `update_memory` (edit in place) | allowed |
| The person deleting it themselves | allowed — it is their act |

The predicate takes the raw column value rather than an enum member: the column
is a ``String`` and every caller reads it from a row. An unrecognised category
answers False — a permissive fallback would freeze rows nobody decided about,
which is the opposite of ADR-085's doctrine applied here (the conservative side
is the one that does NOT accumulate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.memories.models import MemoryCategory

if TYPE_CHECKING:
    from src.domains.memories.models import Memory

__all__ = [
    "PROTECTED_CATEGORIES",
    "automated_edit_refusal",
    "is_protected_from_deletion",
]

#: Categories no automated path may remove from the active set without filing a
#: successor. Deliberately a frozenset of raw values: the column stores strings.
PROTECTED_CATEGORIES: frozenset[str] = frozenset({MemoryCategory.PROCEDURAL.value})


def is_protected_from_deletion(category: str | None) -> bool:
    """Whether an automated path must leave this memory in the active set.

    Args:
        category: The row's ``category`` column, as stored.

    Returns:
        True for a dictated directive; False for an inferred fact, an unknown
        category, or a missing one.
    """
    return category in PROTECTED_CATEGORIES


def automated_edit_refusal(memory: Memory) -> str | None:
    """Why an automated action must leave this memory alone, or None.

    ONE predicate for both branches of the extractor. They used to ask the same
    question in two copies of an if/log/continue block, which is exactly where a
    third rule goes missing — and a third rule arrived (ADR-278's sibling: a
    dictated directive is corrected, never deleted).

    Args:
        memory: The row the model proposed to change.

    Returns:
        A stable reason code, or None when the action may proceed.
    """
    if memory.pinned:
        return "pinned"
    if is_protected_from_deletion(memory.category):
        return "protected_category"
    return None
