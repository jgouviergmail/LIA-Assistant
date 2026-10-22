"""Read a context call's proposals one by one: repair the mechanical, set the rest aside alone.

A context call's answer is one structured object, and one malformed proposal used to
refuse all of it: measured on 2026-10-21, four rebuilds in a row failed whole on one
configured model, each over one to four proposals among valid ones, and a model that
refuses a forced tool call has no second chance. Whatever model a slot runs, what a
repair cannot change the meaning of is repaired before validation: a reference listed
twice or left empty, an anchor missing from its proposal's own references, and an
observation resting on several facts, which by the store's own definition is an
episode (an observation rests on one source object, and the two kinds differ in
nothing else). What would need an intent nobody stated is set aside alone and counted,
never the answer (ADR-343's doctrine for the portrait's claims).
"""

from collections import Counter
from collections.abc import Sequence

from pydantic import ValidationError

from src.core.constants import DISCUSSION_CONTEXT_PROPOSALS_MAX
from src.domains.proactive_discussions.context_store.schemas import (
    ContextProposal,
    ProposalRefusal,
)


def read_proposals(
    raw: Sequence[object],
) -> tuple[tuple[ContextProposal, ...], Counter[ProposalRefusal]]:
    """Read a context call's proposals one by one.

    Args:
        raw: The proposals as the call returned them.

    Returns:
        The readable proposals, in their order, and why each other one was set aside:
        beyond the published cap, or any shape the contract refuses once repaired.
    """
    kept: list[ContextProposal] = []
    refused: Counter[ProposalRefusal] = Counter()
    for index, item in enumerate(raw):
        if index >= DISCUSSION_CONTEXT_PROPOSALS_MAX:
            refused["beyond_cap"] += 1
            continue
        try:
            kept.append(ContextProposal.model_validate(_repaired(item)))
        except ValidationError:
            refused["unreadable"] += 1
    return tuple(kept), refused


def _repaired(item: object) -> object:
    """The proposal with distinct non-empty references, its anchor first among them.

    An observation left with several references is an episode: the kind the store
    defines for an understanding that rests on several facts.
    """
    if not isinstance(item, dict):
        return item
    references = item.get("references")
    if not isinstance(references, list | tuple) or not all(
        isinstance(value, str) for value in references
    ):
        return item
    distinct = list(dict.fromkeys(value.strip() for value in references if value.strip()))
    anchor = item.get("anchor")
    if isinstance(anchor, str) and anchor.strip() and anchor.strip() not in distinct:
        distinct.insert(0, anchor.strip())
    kind = item.get("kind")
    if kind == "observation" and len(distinct) > 1:
        kind = "episode"
    return {**item, "kind": kind, "references": distinct}
