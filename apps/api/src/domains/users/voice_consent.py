"""Current account consent for starting spoken replies, independent of a frozen turn."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.domains.users.models import User

logger = structlog.get_logger(__name__)


async def current_voice_consent(user_id: UUID) -> bool:
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            value = await db.scalar(
                select(User.voice_enabled).where(
                    User.id == user_id,
                    User.is_active,
                    User.deleted_at.is_(None),
                )
            )
            return value is True
    except SQLAlchemyError as exc:
        logger.warning("voice_consent_unavailable", exception_type=type(exc).__name__)
        return False
