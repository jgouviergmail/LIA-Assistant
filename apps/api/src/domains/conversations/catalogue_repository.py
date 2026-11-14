"""Owner-scoped discussion metadata and durable creation receipts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationKind
from src.core.repository import BaseRepository
from src.domains.conversations.models import Conversation, ConversationCreationReceipt


class ConversationCatalogueRepository(BaseRepository[Conversation]):
    """Read metadata without loading messages or LangGraph state."""

    def __init__(self, db: AsyncSession) -> None:
        """Use the caller's short database session."""
        super().__init__(db, Conversation)

    async def get_primary(
        self,
        owner_id: UUID,
        *,
        include_deleted: bool = False,
        lock: bool = False,
    ) -> Conversation | None:
        """Find the declared Main, independent of title and latest activity.

        Args:
            owner_id: Account whose Main is requested.
            include_deleted: Include the unique legacy row when reactivating it.
            lock: Hold a shared row lock for a short history read, never a stream.

        Returns:
            Main or None; reading never creates a row.
        """
        query = select(Conversation).where(
            Conversation.user_id == owner_id, Conversation.kind == ConversationKind.MAIN
        )
        if not include_deleted:
            query = query.where(Conversation.deleted_at.is_(None))
        if lock:
            query = query.with_for_update(read=True)
        return (
            await self.db.execute(query.execution_options(populate_existing=True))
        ).scalar_one_or_none()

    async def get_owned(
        self, owner_id: UUID, conversation_id: UUID, *, lock: bool = False
    ) -> Conversation | None:
        """Return an active owned discussion, hiding foreign and retired rows.

        Args:
            owner_id: Authenticated account.
            conversation_id: Stable business UUID.
            lock: Protect a short metadata/history snapshot from a concurrent reset.

        Returns:
            The owned active row or None.
        """
        query = (
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == owner_id,
                Conversation.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update(read=True)
        return (await self.db.execute(query)).scalar_one_or_none()

    async def last_creation_before(self, owner_id: UUID, before: datetime) -> datetime | None:
        """Read the historical return-metric instant without loading histories."""
        result = await self.db.scalars(
            select(Conversation.created_at)
            .where(Conversation.user_id == owner_id, Conversation.created_at < before)
            .order_by(Conversation.created_at.desc(), Conversation.id)
            .limit(1)
        )
        return result.first()

    async def get_receipt(
        self, owner_id: UUID, request_id: UUID
    ) -> ConversationCreationReceipt | None:
        """Read one account's durable creation attempt, including retired results."""
        return (
            await self.db.execute(
                select(ConversationCreationReceipt).where(
                    ConversationCreationReceipt.user_id == owner_id,
                    ConversationCreationReceipt.request_id == request_id,
                )
            )
        ).scalar_one_or_none()

    async def list_owned(
        self, owner_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        """Return a stable ordered page and exact total in ONE SQL snapshot.

        The outer join retains the aggregate even for an empty or out-of-range
        page. The CTE is the single ownership/visibility predicate for both.

        Args:
            owner_id: Authenticated account.
            limit: Validated maximum number of rows.
            offset: Validated page offset.

        Returns:
            Active metadata rows and the exact total, without an N+1 read.
        """
        owned = (
            select(Conversation.id, Conversation.kind, Conversation.created_at)
            .where(Conversation.user_id == owner_id, Conversation.deleted_at.is_(None))
            .cte("owned_conversations")
        )
        page = (
            select(owned.c.id)
            .order_by(
                (owned.c.kind == ConversationKind.MAIN).desc(),
                owned.c.created_at.desc(),
                owned.c.id,
            )
            .limit(limit)
            .offset(offset)
            .cte("conversation_page")
        )
        total = (
            select(func.count().label("total_count")).select_from(owned).cte("conversation_total")
        )
        query = (
            select(Conversation, total.c.total_count)
            .select_from(
                total.outerjoin(page, true()).outerjoin(Conversation, Conversation.id == page.c.id)
            )
            .order_by(
                (Conversation.kind == ConversationKind.MAIN).desc(),
                Conversation.created_at.desc(),
                Conversation.id,
            )
        )
        rows = (await self.db.execute(query)).all()
        return [row[0] for row in rows if row[0] is not None], int(rows[0][1])

    async def claim_waiting_title(self, conversation_id: UUID, title: str) -> UUID | None:
        """Give an annex still waiting for its title the one its first message suggests.

        One conditional statement, so the order two writers commit in cannot
        replace a title a person typed: a discussion its owner titled or
        renamed meanwhile, Main and a retired row all match nothing.

        Args:
            conversation_id: The discussion the message was written in.
            title: A title the catalogue's grammar accepts.

        Returns:
            The owner of the discussion that took the title, or None when it
            was not waiting for one.
        """
        owner_id: UUID | None = (
            await self.db.execute(
                update(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.kind == ConversationKind.SECONDARY,
                    Conversation.title_auto.is_(True),
                    Conversation.deleted_at.is_(None),
                )
                .values(title=title, title_auto=False)
                .returning(Conversation.user_id)
            )
        ).scalar_one_or_none()
        return owner_id
