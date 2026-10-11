"""Prepare outside locks, then fence the entire automatic interest write batch."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.interests import helpers
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services.action_applier import apply_interest_actions
from src.domains.users.extraction_consent import snapshot_extraction_revision
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.observability.logging import get_logger

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
logger = get_logger(__name__)


class ObsoleteInterestExtraction(Exception):
    """The actor, extraction revision or learning capability changed."""


async def capture_interest_revision(factory: SessionFactory, actor_id: UUID) -> int | None:
    run_context = runtime_context_if_running()
    if run_context is not None and (
        run_context.user_id != actor_id or run_context.extraction_revision is None
    ):
        return None
    async with factory() as db:
        return await snapshot_extraction_revision(
            db,
            actor_id,
            expected_revision=run_context.extraction_revision if run_context else None,
        )


async def require_interest_revision(
    db: AsyncSession, actor_id: UUID, revision: int, *, lock: bool = False
) -> None:
    if not await is_capability_enabled(PlatformCapability.INTERESTS):
        raise ObsoleteInterestExtraction
    if (
        await snapshot_extraction_revision(db, actor_id, expected_revision=revision, lock=lock)
        is None
    ):
        raise ObsoleteInterestExtraction


async def prepare_extraction_embeddings(
    factory: SessionFactory,
    user_id: UUID,
    revision: int,
    actions: list[ExtractedInterest],
    session_id: str,
    conversation_id: str | None,
    run_id: str | None,
) -> dict[str, list[float] | None]:
    topics = dict.fromkeys(
        action.topic for action in actions if action.action != "delete" and action.topic
    )
    prepared: dict[str, list[float] | None] = {}
    previous = get_embedding_context()
    set_embedding_context(str(user_id), session_id, conversation_id, run_id)
    try:
        for topic in topics:
            async with factory() as db:
                await require_interest_revision(db, user_id, revision)
            await enforce_usage_limit(user_id, layer="interest_extraction_embedding")
            prepared[topic] = await helpers.generate_interest_embedding(topic)
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
    return prepared


async def store_interest_extraction(
    factory: SessionFactory,
    actor_id: UUID,
    revision: int,
    actions: list[ExtractedInterest],
    *,
    session_id: str,
    conversation_id: str | None,
    run_id: str | None,
) -> int:
    prepared = await prepare_extraction_embeddings(
        factory, actor_id, revision, actions, session_id, conversation_id, run_id
    )

    async def resolve(topic: str) -> list[float] | None:
        # Missing preparation is an invariant failure, never paid work under a lock.
        return prepared[topic]

    async with factory() as db:
        await require_interest_revision(db, actor_id, revision, lock=True)
        repo = InterestRepository(db)
        candidates = await repo.get_for_dedup(actor_id, limit=settings.interest_dedup_scan_limit)
        stored = await apply_interest_actions(
            repo,
            user_id=str(actor_id),
            actions=actions,
            existing_interests=candidates,
            conversation_id=conversation_id,
            embedding_resolver=resolve,
        )
        await db.flush()
        await require_interest_revision(db, actor_id, revision)
        await db.commit()
        logger.info(
            "interest_extraction_completed",
            user_id=str(actor_id),
            session_id=session_id,
            extracted_count=len(actions),
            stored_count=stored,
        )
        return stored
