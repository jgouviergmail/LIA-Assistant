"""Native account cleanup composition; users imports no agents or attachments domain."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE
from src.domains.agents.context.store import get_tool_context_store
from src.domains.attachments.file_cleanup import cleanup_files
from src.domains.attachments.models import Attachment
from src.domains.conversations.cleanup_contracts import CleanupState
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.cleanup_port import runtime_cleanup
from src.domains.conversations.cleanup_runner import ConversationCleanupRunner


class NativeAccountCleanup:
    """Reuse the same durable claims and file remover as targeted retirement."""

    async def cleanup_page(self, sessions: async_sessionmaker[AsyncSession], owner: UUID) -> int:
        """Attempt a bounded page; scheduling, not this request, owns eventual retries."""
        async with sessions() as db:
            operation_ids = list(
                await db.scalars(
                    select(ConversationOperation.id)
                    .where(
                        ConversationOperation.user_id == owner,
                        ConversationOperation.state != CleanupState.SUCCEEDED,
                    )
                    .order_by(ConversationOperation.created_at, ConversationOperation.id)
                    .limit(settings.conversation_cleanup_batch_size)
                )
            )
            file_ids = list(
                await db.scalars(
                    select(Attachment.id)
                    .where(
                        Attachment.user_id == owner,
                    )
                    .order_by(Attachment.id)
                    .limit(settings.attachments_cleanup_batch_size)
                )
            )
            await db.commit()
        runner = ConversationCleanupRunner(sessions, runtime_cleanup())
        for operation_id in operation_ids:
            await runner.run_one(operation_id=operation_id)
        async with sessions() as db:
            removed = await cleanup_files(db, ids=file_ids)
        return removed["deleted"]

    async def purge_store(self, owner: UUID) -> int:
        """The native API covers the root, children and vector rows without SQL guessing."""
        store = await get_tool_context_store()
        count = 0
        while page := await store.asearch((str(owner),), limit=CONVERSATION_CLEANUP_PAGE_SIZE):
            for item in page:
                await store.adelete(item.namespace, item.key)
                count += 1
        return count
