"""Persist analysis checkpoints without copying source bodies or reprocessing unchanged facts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.context_store.admission import observation_key, reference_key
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextObservationRecord,
)
from src.domains.proactive_discussions.context_store.preparation import proof_of
from src.domains.shared.discussion_sources import DiscussionEvidence


async def changed_observations(
    db: AsyncSession,
    owner: UUID,
    items: tuple[DiscussionEvidence, ...],
    *,
    now: datetime,
    signature: str | None = None,
    directives_revision: str | None = None,
    context_epoch: int = 0,
) -> tuple[DiscussionEvidence, ...]:
    """Return the evidence that changed since it was last interpreted.

    An item is unchanged when an unexpired observation holds the same version,
    interpreted under the same interpretation signature, directives and context
    epoch; only changed items are paid for again.

    Args:
        db: The session to read with.
        owner: The account.
        items: The evidence read now.
        now: The current instant.
        signature: The interpretation signature of this interpretation.
        directives_revision: The directives of this interpretation.
        context_epoch: The context epoch of this interpretation.

    Returns:
        The items to interpret.
    """
    rows = (
        (
            await db.execute(
                select(
                    ContextObservationRecord.root,
                    ContextObservationRecord.version,
                    ContextObservationRecord.data["interpretation_signature"].as_string(),
                    ContextObservationRecord.data["directives_revision"].as_string(),
                    ContextObservationRecord.data["interpreted_context_epoch"].as_integer(),
                ).where(
                    ContextObservationRecord.user_id == owner,
                    ContextObservationRecord.expires_at > now,
                    ContextObservationRecord.root.in_([observation_key(item) for item in items]),
                )
            )
        )
        .tuples()
        .all()
    )
    versions = {
        root: (version, interpreted, directives, epoch)
        for root, version, interpreted, directives, epoch in rows
    }
    return tuple(
        item
        for item in items
        if signature is None
        or versions.get(observation_key(item))
        != (item.version, signature, directives_revision, context_epoch)
    )


async def apply_observations(
    db: AsyncSession,
    owner: UUID,
    items: tuple[DiscussionEvidence, ...],
    *,
    now: datetime,
    policy_revision: int,
    directives_revision: str | None,
    context_epoch: int = 0,
    signature: str | None = None,
) -> bool:
    """Record the interpretation checkpoint of each evidence, without its body.

    An observation is upserted only when something it records changed; a shorter
    source retention also shortens every context item derived from it.

    Args:
        db: The session to write with.
        owner: The account.
        items: The interpreted evidence.
        now: The current instant.
        policy_revision: The policy revision of this interpretation (provenance).
        directives_revision: The directives of this interpretation.
        context_epoch: The context epoch of this interpretation.
        signature: The interpretation signature, which decides reuse.

    Returns:
        True when at least one observation changed.

    Raises:
        ValueError: Two items share one occurrence identity.
    """
    references = {item.reference: item for item in items}
    proofs = [
        proof_of(item, references, now=now).model_copy(
            update={
                "interpreted_policy_revision": policy_revision,
                "interpretation_signature": signature,
                "directives_revision": directives_revision,
                "interpreted_context_epoch": context_epoch,
            }
        )
        for item in items
    ]
    if len({proof.root for proof in proofs}) != len(proofs):
        raise ValueError("source objects do not have distinct occurrence identities")
    changed = False
    for proof in proofs:
        statement = insert(ContextObservationRecord).values(
            user_id=owner,
            root=proof.root,
            source=proof.source.value,
            version=proof.version,
            data=proof.model_dump(mode="json"),
            expires_at=proof.expires_at,
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[ContextObservationRecord.user_id, ContextObservationRecord.root],
            set_={
                "version": proof.version,
                "data": proof.model_dump(mode="json"),
                "expires_at": proof.expires_at,
            },
            where=(ContextObservationRecord.version != proof.version)
            | (ContextObservationRecord.expires_at > proof.expires_at)
            | (ContextObservationRecord.expires_at <= now)
            | ContextObservationRecord.data["sensitive_topics"].is_distinct_from(
                statement.excluded.data["sensitive_topics"]
            )
            | ContextObservationRecord.data["interpretation_signature"]
            .as_string()
            .is_distinct_from(signature)
            | ContextObservationRecord.data["directives_revision"]
            .as_string()
            .is_distinct_from(directives_revision)
            | ContextObservationRecord.data["interpreted_context_epoch"]
            .as_integer()
            .is_distinct_from(context_epoch),
        ).returning(ContextObservationRecord.root)
        if (await db.execute(upsert)).first() is not None:
            changed = True
        # A shorter source retention also bounds every already-derived item.
        await db.execute(
            update(ContextItemRecord)
            .where(
                ContextItemRecord.user_id == owner,
                ContextItemRecord.root_keys.overlap([proof.root, reference_key(proof.reference)]),
            )
            .values(expires_at=func.least(ContextItemRecord.expires_at, proof.expires_at))
        )
    return changed
