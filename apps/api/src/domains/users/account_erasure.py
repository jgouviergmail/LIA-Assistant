"""One SQL door for final account erasure, after the audited content purge."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.domains.users.account_cleanup import cleanup_pending, require_account_cleanup_complete
from src.domains.users.models import User
from src.domains.users.resource_release import build_capability_origin_scrub
from src.infrastructure.database.owner_lock import hold_owner_lock


async def erase_purged_account(db: AsyncSession, owner: UUID) -> bool:
    """Never let CASCADE erase unfinished file/runtime work; the caller commits.

    A previously deleted row is an idempotent success. Existing accounts must
    have completed AccountDeletionService first, including legacy admin paths.
    """
    await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner)
    user = await db.scalar(
        select(User)
        .where(User.id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        return False
    if user.is_active or user.deleted_at is None or user.is_superuser:
        raise cleanup_pending()
    await require_account_cleanup_complete(db, owner)
    await db.execute(build_capability_origin_scrub(owner))
    await db.execute(delete(User).where(User.id == owner))
    return True
