"""Capture the revision before an immutable run starts any management action."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.context.runtime_context import LiaRuntimeContext, runtime_context_if_running
from src.domains.users.extraction_consent import snapshot_extraction_revision
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


async def with_current_extraction_revision(context: LiaRuntimeContext) -> LiaRuntimeContext:
    revision: int | None = None
    # Interests, open loops and recurrence also learn when all three optional
    # record preferences are off. Capture the account fence for every turn.
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


async def capture_run_extraction_revision(db: AsyncSession, owner_id: UUID) -> int | None:
    """Read the initial account/source fence, preserving a turn's captured consent."""
    context = runtime_context_if_running()
    if context is not None and (context.user_id != owner_id or context.extraction_revision is None):
        return None
    return await snapshot_extraction_revision(
        db,
        owner_id,
        expected_revision=context.extraction_revision if context is not None else None,
    )
