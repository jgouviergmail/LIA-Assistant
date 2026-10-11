"""Capture the revision before an immutable run starts any management action."""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


async def with_current_extraction_revision(context: LiaRuntimeContext) -> LiaRuntimeContext:
    revision: int | None = None
    if context.memory_enabled or context.journals_enabled or context.psyche_enabled:
        try:
            async with get_db_context() as db:
                revision = await db.scalar(
                    select(User.extraction_revision).where(
                        User.id == context.user_id,
                        User.is_active,
                        User.deleted_at.is_(None),
                    )
                )
        except SQLAlchemyError:
            # The conversation can still answer; an unavailable authority permits no learning.
            revision = None
    return replace(context, extraction_revision=revision)
