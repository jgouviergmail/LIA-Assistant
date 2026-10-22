"""Body-free proof candidates; exclusion and policy checks precede native retrieval."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.proactive_discussions.context_store.models import ContextItemRecord
from src.domains.proactive_discussions.context_store.pages import present_items
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.shared.discussion_sources import SensitiveTopic, SourceKey


async def pending_proofs(
    db: AsyncSession,
    owner: UUID,
    *,
    sources: frozenset[SourceKey],
    topics: frozenset[SensitiveTopic],
    now: datetime,
) -> tuple[ContextEvidenceLink, ...]:
    """Return the proofs of the newest stored context items the run may still use.

    The ``DISCUSSION_REUSED_ITEMS_MAX`` most recently updated unexpired items are
    read; an item the person excluded, or with a proof from a source, dependency or
    topic no longer allowed, or expired, is skipped whole; proofs are kept while
    their union stays within ``DISCUSSION_REUSED_PROOFS_MAX`` references.

    Args:
        db: The session to read with.
        owner: The account.
        sources: The sources the run may read.
        topics: The sensitive topics the person allowed.
        now: The current instant.

    Returns:
        The proofs to read again before the context is reused, without any body.
    """
    rows = list(
        (
            await db.scalars(
                select(ContextItemRecord)
                .where(
                    ContextItemRecord.user_id == owner,
                    ContextItemRecord.expires_at > now,
                )
                .order_by(ContextItemRecord.updated_at.desc(), ContextItemRecord.id)
                .limit(settings.discussion_reused_items_max)
            )
        ).all()
    )
    candidates = await present_items(db, owner, rows)
    chosen: dict[str, ContextEvidenceLink] = {}
    for item in candidates:
        if item.excluded or not all(
            proof.source in sources
            and set(proof.required_sources) <= sources
            and set(proof.sensitive_topics) <= topics
            and proof.expires_at > now
            for proof in item.proofs
        ):
            continue
        additions = {proof.reference: proof for proof in item.proofs}
        if len(chosen.keys() | additions.keys()) <= settings.discussion_reused_proofs_max:
            chosen.update(additions)
    return tuple(chosen.values())
