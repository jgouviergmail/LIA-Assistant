"""One SQL selection drives context rows and their exact filtered total."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import ColumnElement, any_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from src.domains.proactive_discussions.context_store.models import (
    ContextExclusionRecord,
    ContextItemRecord,
)
from src.domains.proactive_discussions.context_store.schemas import ContextKind
from src.domains.proactive_discussions.policy import effective_sources
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.shared.discussion_sources import DiscussionValue, SourceKey


# MODEL-FACING (discussion_context.read tool) and the context page's query parameters:
# a docstring or field description would become schema text the planner reads.
class ContextFilters(DiscussionValue):
    query: Annotated[str | None, Field(max_length=160)] = None
    source: SourceKey | None = None
    kind: ContextKind | None = None
    usable: bool | None = None
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        """Refuse a creation window whose end does not follow its start."""
        if self.created_from and self.created_to and self.created_to <= self.created_from:
            raise ValueError("context creation window must be increasing")
        return self


def context_conditions(
    owner: UUID, filters: ContextFilters, policy: DiscussionPolicy, *, now: datetime
) -> tuple[ColumnElement[bool], ...]:
    """Build the one selection behind a context page and its exact total (ADR-185).

    Args:
        owner: The account.
        filters: The person's filters.
        policy: The policy, for the usable filter.
        now: The current instant; expired items are never listed.

    Returns:
        The conditions, to be combined with AND.
    """
    conditions = [ContextItemRecord.user_id == owner, ContextItemRecord.expires_at > now]
    if filters.query:
        # The needle is folded as SQL folds the summary: ``casefold()`` would turn
        # « ß » into « ss », which ``lower()`` never does, and find nothing.
        conditions.append(
            func.strpos(func.lower(ContextItemRecord.data["summary"].astext), filters.query.lower())
            > 0
        )
    if filters.source:
        conditions.append(
            ContextItemRecord.data["proofs"].contains([{"source": filters.source.value}])
        )
    if filters.kind:
        conditions.append(ContextItemRecord.kind == filters.kind)
    if filters.created_from:
        conditions.append(ContextItemRecord.created_at >= filters.created_from)
    if filters.created_to:
        conditions.append(ContextItemRecord.created_at < filters.created_to)
    if filters.usable is not None:
        usable = usable_condition(owner, policy)
        conditions.append(usable if filters.usable else ~usable)
    return tuple(conditions)


def usable_condition(owner: UUID, policy: DiscussionPolicy) -> ColumnElement[bool]:
    """Express "usable" in SQL: not excluded, every proof readable and consented.

    Args:
        owner: The account.
        policy: The policy deciding which sources and topics are allowed.

    Returns:
        The condition; its negation selects the items that are not usable.
    """
    excluded = (
        select(ContextExclusionRecord.id)
        .where(
            ContextExclusionRecord.user_id == owner,
            or_(
                ContextExclusionRecord.item_id == ContextItemRecord.id,
                ContextExclusionRecord.root == any_(ContextItemRecord.root_keys),
            ),
        )
        .exists()
    )
    sources = [key.value for key in effective_sources(policy, frozenset(SourceKey))]
    proofs = (
        func.jsonb_array_elements(ContextItemRecord.data["proofs"])
        .table_valued("value")
        .alias("context_proof")
    )
    value = cast(proofs.c.value, JSONB)
    denied = (
        select(proofs.c.value)
        .where(
            or_(
                ~value["source"].astext.in_(sources),
                ~value["required_sources"].op("<@", is_comparison=True)(cast(sources, JSONB)),
                ~value["sensitive_topics"].op("<@", is_comparison=True)(
                    cast(list(policy.sensitive_topics), JSONB)
                ),
            )
        )
        .exists()
    )
    return ~excluded & ~denied
