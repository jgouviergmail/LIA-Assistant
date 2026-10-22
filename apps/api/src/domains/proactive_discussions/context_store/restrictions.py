"""Cached classifications may restrict a native fact, never relax its authority."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.context_store.admission import observation_key
from src.domains.proactive_discussions.context_store.models import ContextObservationRecord
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.shared.discussion_sources import DiscussionEvidence


async def restrict_cached_topics(
    db: AsyncSession,
    owner: UUID,
    items: tuple[DiscussionEvidence, ...],
    *,
    now: datetime,
    directives_revision: str | None,
) -> tuple[DiscussionEvidence, ...]:
    """Add to unchanged evidence the sensitive topics an earlier interpretation found.

    A cached classification only ever adds topics, never removes one, and applies
    only to the same version under the same directives.

    Args:
        db: The session to read with.
        owner: The account.
        items: The evidence read now.
        now: The current instant; expired classifications are ignored.
        directives_revision: The directives a classification must match, or None
            for any.

    Returns:
        The evidence, each with its cached topics added.
    """
    rows = (
        await db.scalars(
            select(ContextObservationRecord.data).where(
                ContextObservationRecord.user_id == owner,
                ContextObservationRecord.root.in_([observation_key(item) for item in items]),
                ContextObservationRecord.expires_at > now,
            )
        )
    ).all()
    cached = {
        proof.root: proof
        for value in rows
        if (proof := ContextEvidenceLink.model_validate(value))
        and (directives_revision is None or proof.directives_revision == directives_revision)
    }
    result = []
    for item in items:
        previous = cached.get(observation_key(item))
        if previous is not None and previous.version == item.version:
            item = item.model_copy(
                update={
                    "sensitive_topics": tuple(
                        sorted(set(item.sensitive_topics) | set(previous.sensitive_topics))
                    )
                }
            )
        result.append(item)
    return tuple(result)
