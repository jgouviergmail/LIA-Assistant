"""Application of the interest actions an extraction proposed.

Extracted from ``extraction_service.extract_interests_background`` (file-size
ratchet — a logical file never grows; that function was also a CC-34 hotspot).
The behaviour is the same except for two deliberate changes, both of which fix
a defect measured in production on 2026-07-27:

1. **Deduplication sees every status, not only ``active``.** The dedup list used
   to come from ``get_active_for_user``, so an interest the user had BLOCKED was
   invisible to it. Production timeline, same day: an interest is created at
   12:51, the user blocks it at 19:14, and the extractor re-creates it at 19:39
   under a near-identical label (cosine similarity 0.9821 — far above the 0.89
   merge threshold, so it WOULD have merged had the row been visible). Blocking
   a subject must mean it never comes back; here it came back in 25 minutes.
   Dormant rows were invisible for the same reason, which made the
   reactivation branch of ``consolidate_on_mention`` unreachable from this path.

2. **A cap on deletions** (see ``agents/utils/extraction_guards``): one replayed
   production window made the model propose 19 deletions in a single turn.

Ownership: the caller owns the session and the transaction — nothing here
commits.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import settings
from src.domains.agents.utils.extraction_guards import enforce_delete_cap
from src.domains.interests.models import InterestStatus
from src.domains.shared.provenance_capture import record_origin
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_extractions import (
    extraction_action_rejected_total,
)

if TYPE_CHECKING:
    from src.domains.interests.models import UserInterest
    from src.domains.interests.repository import InterestRepository
    from src.domains.interests.schemas import ExtractedInterest

logger = get_logger(__name__)

KIND_INTERESTS = "interests"
REASON_BLOCKED = "blocked_interest"


async def find_similar_interest(
    topic: str,
    existing_interests: list[UserInterest],
) -> tuple[bool, UserInterest | None]:
    """Find whether a semantically equivalent interest already exists.

    Uses embedding cosine similarity when both sides carry an embedding, and
    falls back to substring matching when either does not — embedding
    generation is best-effort and may return ``None``, and that failure must
    not disable deduplication entirely (ADR-131: the "Anthropic"/"anthropic"
    production duplicate slipped through exactly there).

    Args:
        topic: Topic of the interest the model wants to create.
        existing_interests: Candidates to compare against — every status, so a
            blocked or dormant row is found rather than duplicated.

    Returns:
        ``(is_similar, matching_interest)``; the match is the best one above
        the configured threshold.
    """
    from src.domains.interests.helpers import generate_interest_embedding

    topic_embedding = await generate_interest_embedding(topic)

    best_match: UserInterest | None = None
    best_similarity: float = 0.0

    for interest in existing_interests:
        if topic_embedding and interest.embedding:
            from src.infrastructure.llm.local_embeddings import cosine_similarity

            similarity = cosine_similarity(topic_embedding, interest.embedding)
            if similarity >= settings.interest_dedup_similarity_threshold and (
                similarity > best_similarity
            ):
                best_similarity = similarity
                best_match = interest
        elif topic_embedding is None or not interest.embedding:
            if interest.topic.lower() in topic.lower() or topic.lower() in interest.topic.lower():
                logger.debug(
                    "interest_similarity_string_match",
                    new_topic=topic[:50],
                    existing_topic=interest.topic[:50],
                )
                return True, interest

    if best_match:
        # INFO-level for production monitoring of deduplication decisions.
        logger.info(
            "interest_dedup_match_found",
            new_topic=topic[:50],
            matched_topic=best_match.topic[:50],
            similarity=round(best_similarity, 4),
            threshold=settings.interest_dedup_similarity_threshold,
            matched_interest_id=str(best_match.id),
            matched_status=best_match.status,
        )
        return True, best_match

    return False, None


def _is_blocked(interest: UserInterest) -> bool:
    """Whether the user has explicitly rejected this interest."""
    return interest.status == InterestStatus.BLOCKED.value


def _record_blocked_skip(action: str, interest: UserInterest, user_id: str) -> None:
    """Count and log one action refused because the user blocked the subject.

    Args:
        action: The refused action, for the log line (``create``, ``update``,
            ``delete``, ``update_rename``).
        interest: The blocked interest the action would have touched.
        user_id: Owner, as a string.
    """
    logger.info(
        "interest_action_skipped_blocked",
        user_id=user_id,
        action=action,
        interest_id=str(interest.id),
        msg="The user blocked this subject; the extraction may not resurrect it.",
    )
    # Metrics emission is best-effort: an observability failure must never
    # break a fire-and-forget extraction (same contract as the rollback counter
    # in infrastructure/database/session.py).
    with suppress(Exception):
        extraction_action_rejected_total.labels(kind=KIND_INTERESTS, reason=REASON_BLOCKED).inc()


async def _resolve_target(
    repo: InterestRepository,
    extracted: ExtractedInterest,
    user_id: str,
    known_ids: set[str],
) -> UserInterest | None:
    """Return the interest an update/delete targets, or None if inadmissible.

    Rejects hallucinated identifiers, cross-tenant references, and any attempt
    to touch a blocked interest.

    Args:
        repo: Interest repository bound to the caller's session.
        extracted: The action emitted by the model.
        user_id: Owner of the extraction, as a string.
        known_ids: Identifiers the model was legitimately given.

    Returns:
        The target interest, or ``None`` when the action must be dropped.
    """
    if not extracted.interest_id or extracted.interest_id not in known_ids:
        logger.warning(
            "interest_extraction_unknown_id",
            user_id=user_id,
            action=extracted.action,
            interest_id=extracted.interest_id,
        )
        return None

    interest = await repo.get_by_id(UUID(extracted.interest_id))
    if not interest or str(interest.user_id) != user_id:
        return None
    if _is_blocked(interest):
        _record_blocked_skip(extracted.action, interest, user_id)
        return None
    return interest


async def _apply_delete(
    repo: InterestRepository,
    extracted: ExtractedInterest,
    user_id: str,
    known_ids: set[str],
) -> int:
    """Delete an interest the user is no longer interested in.

    Args:
        repo: Interest repository bound to the caller's session.
        extracted: The deletion the model proposed.
        user_id: Owner, as a string.
        known_ids: Identifiers the model was legitimately given.

    Returns:
        1 when the deletion was applied, 0 otherwise.
    """
    interest = await _resolve_target(repo, extracted, user_id, known_ids)
    if interest is None:
        return 0
    topic = interest.topic[:50]
    await repo.delete(interest)
    logger.info(
        "interest_deleted_by_extraction",
        user_id=user_id,
        interest_id=extracted.interest_id,
        topic=topic,
    )
    return 1


async def _apply_update(
    repo: InterestRepository,
    extracted: ExtractedInterest,
    user_id: str,
    known_ids: set[str],
) -> int:
    """Refine an existing interest and count the mention.

    Renaming onto an existing topic would create a duplicate, so the collision
    target is consolidated instead (ADR-131).

    Args:
        repo: Interest repository bound to the caller's session.
        extracted: The update the model proposed.
        user_id: Owner, as a string.
        known_ids: Identifiers the model was legitimately given.

    Returns:
        1 when something was applied, 0 otherwise.
    """
    interest = await _resolve_target(repo, extracted, user_id, known_ids)
    if interest is None:
        return 0

    if extracted.topic and extracted.topic != interest.topic:
        collision = await repo.get_by_user_and_topic_ci(interest.user_id, extracted.topic)
        if collision and collision.id != interest.id:
            if _is_blocked(collision):
                _record_blocked_skip("update_rename", collision, user_id)
                return 0
            await repo.consolidate_on_mention(collision)
            logger.info(
                "interest_rename_collision_consolidated",
                user_id=user_id,
                interest_id=str(collision.id),
                topic=collision.topic[:50],
            )
            return 1

        from src.domains.interests.helpers import generate_interest_embedding

        interest.topic = extracted.topic
        # Subject is derived from the topic: relabel on the next stale scan (ADR-131).
        interest.subject = None
        interest.embedding = await generate_interest_embedding(extracted.topic)

    if extracted.category:
        interest.category = extracted.category.value
    await repo.consolidate_on_mention(interest)
    logger.info(
        "interest_updated_by_extraction",
        user_id=user_id,
        interest_id=extracted.interest_id,
        topic=interest.topic[:50],
    )
    return 1


async def _apply_create(
    repo: InterestRepository,
    extracted: ExtractedInterest,
    user_id: str,
    existing_interests: list[UserInterest],
    conversation_id: str | None = None,
) -> int:
    """Create a new interest, or consolidate the one it duplicates.

    A match on a BLOCKED interest applies nothing: the user rejected that
    subject, and neither a new row nor a consolidation may bring it back.

    Args:
        repo: Interest repository bound to the caller's session.
        extracted: The creation the model proposed.
        user_id: Owner, as a string.
        existing_interests: Deduplication candidates. MUTATED on success — a
            creation joins the set so the rest of the batch dedups against it.

    Returns:
        1 when something was applied, 0 otherwise.
    """
    if not extracted.topic or not extracted.category:
        return 0

    is_similar, existing = await find_similar_interest(extracted.topic, existing_interests)

    if is_similar and existing:
        if _is_blocked(existing):
            _record_blocked_skip("create", existing, user_id)
            return 0
        # Consolidation also revives a dormant interest (repository contract).
        await repo.consolidate_on_mention(existing)
        logger.info(
            "interest_consolidated",
            user_id=user_id,
            interest_id=str(existing.id),
            topic=existing.topic[:50],
            positive_signals=existing.positive_signals,
            previous_status=existing.status,
        )
        return 1

    from src.domains.interests.helpers import generate_interest_embedding

    new_interest = await repo.create(
        user_id=UUID(user_id),
        topic=extracted.topic,
        category=extracted.category.value,
        embedding=await generate_interest_embedding(extracted.topic),
    )
    # Join the candidate set so a second creation in the SAME batch is
    # deduplicated against this one: the list was snapshotted before the loop,
    # so without this two near-identical topics both land.
    existing_interests.append(new_interest)
    # Where this interest came from, as a BOUNDED pointer. An interest IS a
    # belief LIA formed — "you seem to care about X" — and it stated that
    # belief, its weight and its status without ever saying what produced it.
    # Best-effort: the interest is already valid without its explanation.
    await record_origin(
        repo.db,
        user_id=UUID(user_id),
        source=conversation_id,
        interest_id=new_interest.id,
    )
    logger.info(
        "interest_created",
        user_id=user_id,
        interest_id=str(new_interest.id),
        topic=extracted.topic[:50],
        category=extracted.category.value,
        confidence=extracted.confidence,
    )
    return 1


async def apply_interest_actions(
    repo: InterestRepository,
    *,
    user_id: str,
    actions: list[ExtractedInterest],
    existing_interests: list[UserInterest],
    conversation_id: str | None = None,
) -> int:
    """Apply every action an extraction proposed, guarded.

    One failing action never takes the others down: each is applied under its
    own ``try``, exactly as the inline loop used to.

    Args:
        repo: Interest repository bound to the caller's session. The caller
            owns the transaction and commits.
        user_id: Owner of the interests, as a string.
        actions: Parsed actions, already filtered by the confidence floor.
        existing_interests: Deduplication candidates, ALL statuses included.
        conversation_id: The conversation the extraction ran on, recorded as
            the ORIGIN of anything it creates. Optional: an interest created
            outside a conversation simply carries no origin, rather than one
            that was invented.

    Returns:
        Number of actions actually applied.
    """
    guarded = enforce_delete_cap(
        actions,
        kind=KIND_INTERESTS,
        cap=settings.extraction_max_deletes_per_run,
    )
    known_ids = {str(interest.id) for interest in existing_interests}
    applied = 0

    for extracted in guarded:
        try:
            if extracted.action == "delete":
                applied += await _apply_delete(repo, extracted, user_id, known_ids)
            elif extracted.action == "update":
                applied += await _apply_update(repo, extracted, user_id, known_ids)
            else:
                applied += await _apply_create(
                    repo, extracted, user_id, existing_interests, conversation_id
                )
        except Exception as e:
            logger.warning(
                "interest_storage_failed",
                user_id=user_id,
                action=extracted.action,
                topic=extracted.topic[:50] if extracted.topic else "",
                error=str(e),
            )
            continue

    return applied
