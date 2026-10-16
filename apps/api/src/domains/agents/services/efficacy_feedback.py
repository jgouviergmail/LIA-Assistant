"""One final-message collector, also used by the transactional feedback port."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.analysis.efficacy_context import EfficacyTurnContext
from src.domains.agents.services.efficacy_provenance import eligible_message_context
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.response_feedback import (
    get_assistant_message_for_user,
    lock_feedback_owner,
)
from src.domains.psyche.efficacy_contracts import (
    EfficacyEpisodeInput,
    EfficacyFeedback,
    EfficacyObservation,
)
from src.domains.psyche.efficacy_repository import EfficacyRepository
from src.domains.psyche.efficacy_service import efficacy_enabled
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def episode_from_message(row: ConversationMessage, user_id: UUID) -> EfficacyEpisodeInput | None:
    canonical = eligible_message_context(row, user_id)
    if canonical is None:
        return None
    envelope, context = canonical
    fingerprint = envelope.get("config_fingerprint")
    if not isinstance(fingerprint, str):
        return None
    raw_observations = envelope.get("observations")
    if not isinstance(raw_observations, list):
        return None
    try:
        observations = tuple(EfficacyObservation.model_validate(item) for item in raw_observations)
        episode = EfficacyEpisodeInput(
            epoch=context.epoch,
            run_id=context.run_id,
            message_id=row.id,
            terminal_at=row.created_at,
            observations=observations,
            config_fingerprint=fingerprint,
        )
    except ValidationError, TypeError:
        return None
    return (
        episode if tuple(item.domain for item in observations) == context.analysis.domains else None
    )


def _active_feedback(metadata: dict[str, object], verdict: str | None) -> EfficacyFeedback | None:
    feedback_data = metadata.get("response_feedback")
    current = verdict or (feedback_data.get("verdict") if isinstance(feedback_data, dict) else None)
    if current == "thumbs_up":
        return EfficacyFeedback.HELPFUL
    if current == "thumbs_down":
        return EfficacyFeedback.UNHELPFUL
    return None


async def record_final_message(
    db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str | None = None
) -> bool:
    await lock_feedback_owner(db, user_id)
    if not await efficacy_enabled(db, user_id):
        return False
    row = await get_assistant_message_for_user(db, user_id, message_id)
    if row is None:
        return False
    episode = episode_from_message(row, user_id)
    if episode is None:
        return False
    feedback = _active_feedback(row.message_metadata or {}, verdict)
    return await EfficacyRepository(db).record_episode(
        user_id,
        episode,
        now=datetime.now(UTC),
        feedback=feedback,
        replace_feedback=feedback is not None,
    )


async def collect_final_message(
    user_id: UUID, message_id: UUID | None, *, context: EfficacyTurnContext | None
) -> None:
    if (
        message_id is None
        or not isinstance(context, EfficacyTurnContext)
        or not context.collection_enabled
    ):
        return
    if not settings.psyche_enabled or not settings.psyche_efficacy_collection_enabled:
        return
    try:
        async with asyncio.timeout(2.0), get_db_context() as db:
            from src.domains.agents.services.efficacy_provenance import finalize_provenance

            await lock_feedback_owner(db, user_id)
            if await efficacy_enabled(db, user_id) and await finalize_provenance(
                db, user_id, message_id
            ):
                await record_final_message(db, user_id, message_id)
            await db.commit()
    except Exception as exc:
        logger.warning("efficacy_collection_unavailable", error_type=type(exc).__name__)


class EfficacyResponseFeedbackHooks:
    async def apply(self, db: AsyncSession, user_id: UUID, message_id: UUID, verdict: str) -> None:
        await record_final_message(db, user_id, message_id, verdict)
