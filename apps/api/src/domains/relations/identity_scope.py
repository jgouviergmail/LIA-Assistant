"""Who a relationship card is about, as each source stores them — ONE resolution.

The 360° card and the relationship timeline read the same records for the
same person; resolved twice, a merge or a spelling could put a call on the
card and leave it off the timeline (ADR-185). Both resolve here: the name is
folded through the person's merges (``IdentityResolver``), then matched
against the aggregates the overview counts, so SQL only ever sees the EXACT
spellings the records were stored under and never gets an opinion of its own
on who is the same person.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.relations.activity import _spellings_for, _total_for
from src.domains.relations.identity import IdentityResolver
from src.domains.shared.aggregates import NameActivity


@dataclass(frozen=True, slots=True)
class RelationScope:
    """A relationship, as its records are stored.

    Attributes:
        target_key: The canonical folded key of the person.
        identity_keys: Every folded key of the identity (the canonical one and
            those merged into it) — the relayed messages store each half under
            its own spelling.
        loop_names: The exact spellings of their open commitments.
        call_names: The exact spellings of their calls.
        loops_total: Their open commitments, exactly.
        calls_total: Their calls, exactly.
    """

    target_key: str
    identity_keys: frozenset[str]
    loop_names: list[str]
    call_names: list[str]
    loops_total: int
    calls_total: int


def relation_scope(
    resolver: IdentityResolver,
    name: str,
    loop_activity: list[NameActivity],
    call_activity: list[NameActivity],
) -> RelationScope:
    """Resolve ``name`` against the person's merges and the sources' aggregates.

    Args:
        resolver: Folding plus the merges the person declared.
        name: The name the card was opened with — a merged-away spelling lands
            on the same card as the canonical one.
        loop_activity: The open commitments, aggregated by counterparty.
        call_activity: The calls, aggregated by callee.

    Returns:
        The scope every read of this relationship uses.
    """
    target_key = resolver.key(name)
    return RelationScope(
        target_key=target_key,
        identity_keys=resolver.keys_of(target_key),
        loop_names=_spellings_for(loop_activity, target_key, resolver=resolver),
        call_names=_spellings_for(call_activity, target_key, resolver=resolver),
        loops_total=_total_for(loop_activity, target_key, resolver=resolver),
        calls_total=_total_for(call_activity, target_key, resolver=resolver),
    )


__all__ = ["RelationScope", "relation_scope"]
