"""Short owner/source locks shared by graph, file and deferred source publications."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationRef
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import Conversation
from src.domains.users.models import User


async def resolve_conversation_source(
    db: AsyncSession, owner_id: UUID, selection: ConversationSelection
) -> ConversationRef | None:
    """Offer account-bound source authority through the catalogue's sole resolver.

    Upload/copy domains depend on the account's authority, not the conversation
    lifecycle that already depends on their cleanup. Resolution creates no Main
    and no usage; a legacy omission snapshots Main only when it already exists.
    """
    return await ConversationCatalogueService(db).resolve_target(owner_id, selection)


async def hold_conversation_source(
    db: AsyncSession, owner_id: UUID, target: ConversationRef | None
) -> None:
    """Keep an active owner and an optional exact discussion current until commit.

    Args:
        db: The caller's short transaction; never held across a network or file wait.
        owner_id: Authenticated account, including legacy unbound uploads.
        target: The immutable source; None does not invent a Main usage.

    Raises:
        ExecutionRevoked: The account or source is unavailable or no longer current.
    """
    if target is not None and target.owner_id != owner_id:
        raise ExecutionRevoked()
    owner = await db.scalar(
        select(User.id)
        .where(User.id == owner_id, User.is_active.is_(True), User.deleted_at.is_(None))
        .with_for_update(read=True)
    )
    if owner is None:
        raise ExecutionRevoked()
    if not await conversation_source_is_current(db, owner_id, target, lock=True):
        raise ExecutionRevoked()


async def conversation_source_is_current(
    db: AsyncSession, owner_id: UUID, target: ConversationRef | None, *, lock: bool = False
) -> bool:
    """Check one exact source after its caller checked/locked the account first.

    A final writer uses lock=True on its own short transaction. Unbound work
    invents neither a Main identity nor a source revision.
    """
    if target is None:
        return True
    if target.owner_id != owner_id:
        return False
    query = select(Conversation.id).where(
        Conversation.user_id == owner_id,
        Conversation.id == target.id,
        Conversation.kind == target.kind,
        Conversation.revision == target.revision,
        Conversation.runtime_id == target.runtime_id,
        Conversation.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update(read=True)
    return await db.scalar(query) is not None
