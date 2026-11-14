"""Compose native persistence cleanup without teaching the domain about agent internals."""

from uuid import UUID

from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE
from src.core.conversation_target import ConversationRef
from src.domains.agents.context.store import get_tool_context_store
from src.domains.conversations.checkpointer import get_checkpointer
from src.domains.skills.proposals import ProposalStore
from src.infrastructure.browser.pool import forget_browser_sessions
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.streaming.live_binding import prepare_live_retirement
from src.infrastructure.streaming.runtime_cleanup import purge_runtime_inventory


class NativeRuntimeCleanup:
    """One immutable retired runtime per call; no account-substring deletion."""

    async def prepare_owner(self, owner: UUID) -> None:
        """Establish Live's existing source before a reset or deletion resolves its target."""
        await prepare_live_retirement(owner)

    async def purge_checkpoint(self, target: ConversationRef) -> bool:
        """The native saver owns removal of checkpoints, blobs and pending writes."""
        saver = await get_checkpointer()
        await saver.adelete_thread(str(target.runtime_id))
        return (
            await saver.aget_tuple({"configurable": {"thread_id": str(target.runtime_id)}}) is None
        )

    async def purge_tool_context(self, target: ConversationRef) -> bool:
        """Page at zero while deleting, including every declared child namespace."""
        store = await get_tool_context_store()
        prefix = (str(target.owner_id), str(target.runtime_id), "context")
        while True:
            page = await store.asearch(prefix, limit=CONVERSATION_CLEANUP_PAGE_SIZE)
            if not page:
                return True
            for item in page:
                await store.adelete(item.namespace, item.key)

    async def purge_pending(self, target: ConversationRef) -> bool:
        """Pending proposals, scoped browser sessions and inventoried HITL share the target."""
        redis = await get_redis_cache()
        await ProposalStore(redis).retire_runtime(target.owner_id, target.runtime_id)
        await forget_browser_sessions(target.owner_id, target.runtime_id)
        return await purge_runtime_inventory(redis, target)
