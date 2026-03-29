"""
Conversation service - business logic for conversation management.

Handles conversation lifecycle:
- Lazy creation on first message
- Message archival for UI
- Conversation reset with audit trail
- Statistics tracking
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    REDIS_KEY_GMAIL_MESSAGE_PREFIX,
    REDIS_KEY_GMAIL_SEARCH_PREFIX,
)
from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_CONVERSATION_ID,
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_RUN_ID,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
    FIELD_TOTAL_COST_EUR,
    FIELD_TOTAL_TOKENS_CACHE,
    FIELD_TOTAL_TOKENS_IN,
    FIELD_TOTAL_TOKENS_OUT,
)
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.domains.conversations.repository import ConversationRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ConversationService:
    """
    Service for managing user conversations and message archival.

    Implements lazy creation pattern: conversations created on first message only.
    Follows existing patterns from auth/users services.
    """

    @staticmethod
    def _should_filter_hitl_message(role: str, metadata: dict[str, Any] | None) -> bool:
        """
        Determine if a HITL message should be filtered (hidden from UI and excluded from count).

        DISABLED: All messages are now shown and counted (HITL or not).
        This simplifies the conversation history and ensures accurate message counting.

        Previous filtering rules (now disabled):
        - User HITL responses: APPROVE/REJECT were filtered
        - Assistant HITL questions: were filtered as ephemeral UI state

        Current behavior:
        - ALL messages are shown (HITL interrupt, responses, questions)
        - ALL messages are counted for accurate tracking

        Args:
            role: Message role ("user", "assistant", "system") - unused
            metadata: Message metadata dict - unused

        Returns:
            Always False - no filtering applied
        """
        # DISABLED: No longer filter any messages
        # All HITL messages (user responses, assistant questions, interrupted messages)
        # are now shown in conversation history for transparency and accurate counting
        _ = role, metadata  # Explicitly mark as unused
        return False

    @staticmethod
    def _filter_hitl_messages(
        messages: list[ConversationMessage],
    ) -> list[ConversationMessage]:
        """
        Filter out trivial HITL responses (APPROVE, REJECT) from ConversationMessage list.

        Keeps meaningful interactions (EDIT, AMBIGUOUS, non-HITL messages).
        Utility method to keep conversation history clean by hiding trivial responses
        that don't add context value.

        Args:
            messages: List of ConversationMessage objects

        Returns:
            Filtered list with trivial HITL responses removed
        """
        filtered_messages = []
        filtered_count = 0
        filtered_types = {"APPROVE": 0, "REJECT": 0}

        for msg in messages:
            if ConversationService._should_filter_hitl_message(msg.role, msg.message_metadata):
                filtered_count += 1
                decision_type = (
                    msg.message_metadata.get("decision_type") if msg.message_metadata else None
                )
                if decision_type in filtered_types:
                    filtered_types[decision_type] += 1

                logger.debug(
                    "hitl_message_filtered",
                    message_id=str(msg.id),
                    decision_type=decision_type,
                    content_preview=msg.content[:50] if msg.content else "",
                )
            else:
                filtered_messages.append(msg)

        if filtered_count > 0:
            logger.info(
                "hitl_messages_filtered_summary",
                total=len(messages),
                filtered=filtered_count,
                shown=len(filtered_messages),
                approve_filtered=filtered_types["APPROVE"],
                reject_filtered=filtered_types["REJECT"],
            )

        return filtered_messages

    @staticmethod
    def _filter_hitl_messages_dict(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Filter out trivial HITL responses (APPROVE, REJECT) from dict message list.

        Same logic as _filter_hitl_messages but works on dict representations
        (used by get_messages_with_tokens methods).

        Args:
            messages: List of message dicts with 'role' and 'message_metadata'

        Returns:
            Filtered list with trivial HITL responses removed
        """
        filtered_messages = []
        filtered_count = 0
        filtered_types = {"APPROVE": 0, "REJECT": 0}

        for msg in messages:
            if ConversationService._should_filter_hitl_message(
                msg.get("role", ""),
                msg.get("message_metadata"),
            ):
                filtered_count += 1
                metadata = msg.get("message_metadata", {})
                decision_type = metadata.get("decision_type") if metadata else None
                if decision_type in filtered_types:
                    filtered_types[decision_type] += 1

                logger.debug(
                    "hitl_message_dict_filtered",
                    message_id=msg.get("id"),
                    decision_type=decision_type,
                    content_preview=msg.get(FIELD_CONTENT, "")[:50],
                )
            else:
                filtered_messages.append(msg)

        if filtered_count > 0:
            logger.info(
                "hitl_messages_dict_filtered_summary",
                total=len(messages),
                filtered=filtered_count,
                shown=len(filtered_messages),
                approve_filtered=filtered_types["APPROVE"],
                reject_filtered=filtered_types["REJECT"],
            )

        return filtered_messages

    async def get_or_create_conversation(self, user_id: UUID, db: AsyncSession) -> Conversation:
        """
        Get user's active conversation, reactivate soft-deleted, or create new one.

        Priority order:
        1. Return active conversation if exists (deleted_at IS NULL)
        2. Reactivate soft-deleted conversation if exists (deleted_at IS NOT NULL)
        3. Create new conversation only if none exists

        This prevents unique constraint violations when a user has a soft-deleted
        conversation (since conversation.id = user_id in 1:1 mapping).

        Args:
            user_id: User UUID
            db: Database session

        Returns:
            Active conversation (deleted_at IS NULL)

        Example:
            >>> conversation = await service.get_or_create_conversation(user_id, db)
            >>> print(conversation.message_count)
            0
        """
        # Use repository for DB access
        repo = ConversationRepository(db)

        # 1. Try to get active conversation
        conversation = await repo.get_active_for_user(user_id)
        if conversation:
            logger.debug(
                "conversation_loaded",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                message_count=conversation.message_count,
            )
            return conversation

        # 2. Check for soft-deleted conversation to reactivate
        soft_deleted = await repo.get_soft_deleted_for_user(user_id)
        if soft_deleted:
            logger.info(
                "conversation_reactivating",
                user_id=str(user_id),
                conversation_id=str(soft_deleted.id),
                previous_message_count=soft_deleted.message_count,
            )
            conversation = await repo.reactivate_conversation(
                conversation=soft_deleted,
                new_title=self._generate_title(),
            )
            await db.commit()

            # Track metrics
            from src.infrastructure.observability.metrics_agents import (
                conversation_reactivated_total,
            )

            conversation_reactivated_total.inc()

            return conversation

        # 3. Create new conversation with audit log (atomic operation)
        conversation = await repo.create_with_audit(
            user_id=user_id,
            title=self._generate_title(),
            initial_message_count=0,
            initial_tokens=0,
        )

        await db.commit()

        # Track metrics
        from src.infrastructure.observability.metrics_agents import conversation_created_total

        conversation_created_total.inc()

        logger.info(
            "conversation_created",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            title=conversation.title,
        )

        return conversation

    async def get_active_conversation(self, user_id: UUID, db: AsyncSession) -> Conversation | None:
        """
        Get user's active conversation without creating one.

        Args:
            user_id: User UUID
            db: Database session

        Returns:
            Active conversation or None if no conversation exists
        """
        repo = ConversationRepository(db)
        return await repo.get_active_for_user(user_id)

    async def reset_conversation(
        self,
        user_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Reset conversation: reset stats + purge messages + audit log.

        IMPORTANT: Does NOT soft-delete the conversation itself to avoid duplicate key errors.
        Instead, resets counters to 0 and deletes all messages.

        This approach:
        - Preserves the conversation record (avoids id=user_id duplicate key)
        - Purges all conversation_messages (cascade)
        - Resets stats to 0
        - LangGraph checkpoints are automatically cleared on next message (new thread state)

        Args:
            user_id: User UUID
            db: Database session

        Note:
            - Conversation record persists (id stays valid)
            - All messages are deleted (cascade from conversation_messages)
            - Audit log created for compliance and debugging
            - LangGraph checkpoints handled automatically via thread_id
        """
        # Get active conversation
        conversation = await self.get_active_conversation(user_id, db)

        if not conversation:
            logger.warning("conversation_reset_no_active_conversation", user_id=str(user_id))
            return

        # Capture stats before reset
        message_count = conversation.message_count
        total_tokens = conversation.total_tokens

        # METRICS: Track conversation length distribution (before reset)
        if message_count > 0:
            from src.infrastructure.observability.metrics import conversation_length_messages
            from src.infrastructure.observability.metrics_business import (
                conversation_abandonment_at_message_count,
                conversation_abandonment_total,
                conversation_tokens_total,
            )

            conversation_length_messages.observe(message_count)

            # Infer agent_type from conversation metadata (or default to "generic")
            # Note: Define before conditional blocks to ensure availability for all metrics
            agent_type = getattr(conversation, "agent_type", "generic")

            # Track tokens consumed in this conversation
            if total_tokens > 0:
                conversation_tokens_total.labels(agent_type=agent_type).observe(total_tokens)

            # Track conversation abandonment (user reset = abandonment)
            abandonment_reason = "user_reset"
            conversation_abandonment_total.labels(
                abandonment_reason=abandonment_reason, agent_type=agent_type
            ).inc()

            conversation_abandonment_at_message_count.labels(
                abandonment_reason=abandonment_reason
            ).observe(message_count)

            logger.debug(
                "conversation_abandonment_tracked",
                message_count=message_count,
                total_tokens=total_tokens,
                abandonment_reason=abandonment_reason,
                conversation_id=str(conversation.id),
            )

        # Reset conversation stats (keep record alive, avoid duplicate key)
        conversation.message_count = 0
        conversation.total_tokens = 0
        conversation.title = self._generate_title()  # New title for fresh start

        # Delete all messages using repository
        repo = ConversationRepository(db)
        await repo.delete_messages_for_conversation(conversation.id)

        # Delete attachments for this user (evolution F4 — File Attachments)
        # Files are linked to user lifecycle, not individual conversations
        from src.core.config import get_settings as _get_settings

        _settings = _get_settings()
        if getattr(_settings, "attachments_enabled", False):
            try:
                from src.domains.attachments.service import AttachmentService

                attachment_service = AttachmentService(db)
                attachments_deleted = await attachment_service.delete_all_for_user(user_id)
                logger.info(
                    "attachments_purged",
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                    count=attachments_deleted,
                )
            except Exception as e:
                logger.warning(
                    "attachments_purge_failed",
                    user_id=str(user_id),
                    error=str(e),
                )

        # Delete token summaries for this conversation
        # CRITICAL: Without this, get_conversation_totals() would return stale token counts
        from src.domains.chat.repository import ChatRepository

        chat_repo = ChatRepository(db)
        token_summaries_deleted = await chat_repo.delete_token_summaries_for_conversation(
            conversation.id
        )
        logger.info(
            "token_summaries_purged",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=token_summaries_deleted,
        )

        # Purge LangGraph checkpoints for this thread using checkpointer.adelete_thread()
        # CRITICAL: Must use checkpointer's method instead of direct SQL to invalidate internal caches
        try:
            from src.domains.conversations.checkpointer import get_checkpointer

            checkpointer = await get_checkpointer()
            thread_id_str = str(conversation.id)

            # Use checkpointer's adelete_thread() - handles cache invalidation correctly
            # This deletes from: checkpoints, checkpoint_blobs, checkpoint_writes
            await checkpointer.adelete_thread(thread_id_str)

            logger.info(
                "checkpoints_purged",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                thread_id=thread_id_str,
            )
        except Exception as checkpoint_error:
            # Non-fatal: continue even if checkpoint purge fails
            logger.warning(
                "checkpoint_purge_failed",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                error=str(checkpoint_error),
            )

        # Purge tool contexts from AsyncPostgresStore (Multi-Keys Store Pattern)
        # CRITICAL: Clean ALL domains (contacts, emails, events) for this session
        try:
            from src.domains.agents.context.manager import ToolContextManager
            from src.domains.agents.context.store import get_tool_context_store

            context_manager = ToolContextManager()
            context_store = await get_tool_context_store()
            # BUGFIX: Store namespaces use conversation.id directly as thread_id (no prefix)
            # The RunnableConfig sets thread_id=str(conversation_id) without "session_" prefix
            session_id_str = str(conversation.id)

            # Delete all Store items: (user_id, "session_{conversation_id}", "context", *)
            cleanup_stats = await context_manager.cleanup_session_contexts(
                user_id=user_id,
                session_id=session_id_str,
                store=context_store,
            )

            logger.info(
                "tool_contexts_purged",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                session_id=session_id_str,
                domains_cleaned=cleanup_stats["domains_cleaned"],
                items_deleted=cleanup_stats["total_items_deleted"],
            )

            # ADDITIONAL CLEANUP: Remove user-scoped store entries
            # AsyncPostgresStore stores namespace tuples, but we also need to clean entries
            # that were created with user_id in the namespace.
            #
            # IMPORTANT: We do NOT clean orphaned entries (emails.item, emails.list) here
            # because they lack user_id and could belong to OTHER users in parallel sessions.
            # Cleaning them would cause data loss for other active users.
            #
            # TODO (Issue #38): Fix emails_tools.py and contacts_tools.py to use proper namespaces
            # Expected: (user_id, session_id, "context", domain)
            # Current: ("emails", "list") - missing user_id, not cleanable per-user
            try:
                from sqlalchemy import text

                # Execute raw SQL on the existing session transaction
                # NOTE: Do NOT use `async with db.begin()` here — the session already
                # has an active implicit transaction from earlier operations in this method.
                # Starting a nested begin() raises InvalidRequestError.
                user_id_str = str(user_id)

                # Delete ONLY user-specific entries (safety: only this user's data)
                # This handles properly formatted entries with user_id in namespace
                count_user_result = await db.execute(
                    text("SELECT COUNT(*) FROM store WHERE prefix LIKE :pattern"),
                    {"pattern": f"%{user_id_str}%"},
                )
                user_entries_count = count_user_result.scalar()

                if user_entries_count > 0:
                    await db.execute(
                        text("DELETE FROM store WHERE prefix LIKE :pattern"),
                        {"pattern": f"%{user_id_str}%"},
                    )
                    logger.info(
                        "user_store_entries_deleted",
                        user_id=str(user_id),
                        conversation_id=str(conversation.id),
                        count=user_entries_count,
                    )
                else:
                    logger.debug(
                        "no_user_store_entries_to_delete",
                        user_id=str(user_id),
                        conversation_id=str(conversation.id),
                    )

            except Exception as store_cleanup_error:
                # Non-fatal: log warning but continue
                logger.warning(
                    "user_store_cleanup_failed",
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                    error=str(store_cleanup_error),
                    error_type=type(store_cleanup_error).__name__,
                )

        except Exception as context_cleanup_error:
            # Non-fatal: continue even if Store cleanup fails
            logger.warning(
                "tool_context_cleanup_failed",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                error=str(context_cleanup_error),
            )

        # Purge ALL Redis data for this user/conversation - GENERIC CLEANUP
        # CRITICAL: Clean everything to prevent conversation bleed-through into new conversation
        #
        # Design: Generic user-scoped cleanup instead of hard-coded patterns.
        # This approach:
        # - Works for ANY agent (contacts, emails, calendar, docs, etc.)
        # - No code changes needed when adding new agents
        # - Comprehensive: cleans ALL user data, not just specific patterns
        # - Safe: Uses SCAN (not KEYS), respects production best practices
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            conversation_id_str = str(conversation.id)
            user_id_str = str(user_id)

            # Generic pattern-based cleanup: delete ALL keys containing user_id or conversation_id
            # Pattern coverage:
            # - *:{user_id}:*       → contacts_search:USER:query, gmail:message:USER:id
            # - *:{user_id}         → contacts_list:USER, any_cache:USER
            # - {user_id}:*         → USER:session_data:*, USER:preferences:*
            # - *:{conversation_id}:* → hitl_pending:CONV:data, context:CONV:state
            # - *:{conversation_id} → pending_hitl:CONV, any_conv_cache:CONV
            # - {conversation_id}:* → CONV:checkpoint:*, CONV:metadata:*
            #
            # This covers:
            # - HITL: pending_hitl, hitl_pending, hitl:request_ts, hitl_tool_call_mapping
            # - Contacts: contacts_list, contacts_search, contacts_details
            # - Emails: gmail:message, gmail:search (via invalidate_llm_cache below)
            # - LLM cache: llm_cache:* (via invalidate_llm_cache below)
            # - ANY future agent caches automatically
            patterns_to_scan = [
                f"*:{user_id_str}:*",
                f"*:{user_id_str}",
                f"{user_id_str}:*",
                f"*:{conversation_id_str}:*",
                f"*:{conversation_id_str}",
                f"{conversation_id_str}:*",
            ]

            deleted_count = 0
            deleted_by_pattern = {}

            for pattern in patterns_to_scan:
                cursor = 0
                pattern_deleted = 0

                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=100)

                    if keys:
                        # Filter out whitelisted global keys if needed (none for now)
                        # keys_to_delete = [k for k in keys if not _is_whitelisted_key(k)]
                        keys_to_delete = keys

                        if keys_to_delete:
                            result = await redis.delete(*keys_to_delete)
                            pattern_deleted += result
                            deleted_count += result
                            logger.debug(
                                "redis_pattern_batch_deleted",
                                pattern=pattern,
                                batch_size=len(keys_to_delete),
                                batch_deleted=result,
                            )

                    if cursor == 0:
                        break

                if pattern_deleted > 0:
                    deleted_by_pattern[pattern] = pattern_deleted
                    logger.debug(
                        "redis_pattern_deleted",
                        pattern=pattern,
                        count=pattern_deleted,
                    )

            logger.info(
                "redis_purged_for_reset",
                user_id=user_id_str,
                conversation_id=conversation_id_str,
                total_keys_deleted=deleted_count,
                patterns_scanned=len(patterns_to_scan),
                deleted_by_pattern=deleted_by_pattern,
            )
        except Exception as redis_error:
            # Non-fatal: continue even if Redis purge fails
            logger.warning(
                "redis_purge_failed",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                error=str(redis_error),
                error_type=type(redis_error).__name__,
            )

        # Invalidate ALL LLM cache (llm_cache:*, gmail:*) - COMPREHENSIVE CLEANUP
        # Critical: Clean ALL LLM caches (router, planner, response, orchestrator, etc.)
        # to prevent stale cache bleed-through into new conversations.
        #
        # Why flush ALL LLM cache?
        # - llm_cache:* keys are NOT user-scoped (global cache for deterministic calls)
        # - Stale cache can cause incorrect responses across conversations
        # - Small performance cost (cache rebuild) vs correctness (no stale responses)
        # - Cache TTL is 5 minutes anyway, so we're just accelerating natural expiry
        try:
            from src.infrastructure.cache.llm_cache import invalidate_llm_cache

            # ALL LLM response cache (router, planner, response, orchestrator, etc.)
            # Uses pattern "llm_cache:*" to match ALL function caches:
            # - llm_cache:_call_router_llm:*
            # - llm_cache:_call_planner_llm:*
            # - llm_cache:_call_response_llm:*
            # - llm_cache:_call_task_orchestrator_llm:*
            # - Any future LLM cache entries
            all_llm_cache_invalidated = await invalidate_llm_cache("llm_cache:*")

            # Gmail cache (search + messages) - user-scoped
            gmail_search_invalidated = await invalidate_llm_cache(
                f"{REDIS_KEY_GMAIL_SEARCH_PREFIX}{user_id}:*"
            )
            gmail_message_invalidated = await invalidate_llm_cache(
                f"{REDIS_KEY_GMAIL_MESSAGE_PREFIX}{user_id}:*"
            )

            total_llm_cache_deleted = (
                all_llm_cache_invalidated + gmail_search_invalidated + gmail_message_invalidated
            )

            logger.info(
                "llm_cache_invalidated",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                all_llm_cache_deleted=all_llm_cache_invalidated,
                gmail_search_keys_deleted=gmail_search_invalidated,
                gmail_message_keys_deleted=gmail_message_invalidated,
                total_llm_cache_deleted=total_llm_cache_deleted,
            )
        except Exception as cache_error:
            # Non-fatal: continue even if cache invalidation fails
            logger.warning(
                "llm_cache_invalidation_failed",
                user_id=str(user_id),
                conversation_id=str(conversation.id),
                error=str(cache_error),
                error_type=type(cache_error).__name__,
            )

        # NOTE: Contacts cache is already cleaned by generic Redis scan above
        # (patterns: contacts_list:{user_id}, contacts_search:{user_id}:*, contacts_details:{user_id}:*)
        # No need for separate ContactsCache.invalidate_user() call - removed for simplicity

        # Create audit log using repository
        await repo.create_audit_log(
            user_id=user_id,
            conversation_id=conversation.id,
            action="reset",
            message_count_at_action=message_count,
            metadata={
                "total_tokens": total_tokens,
                "reset_at": datetime.now(UTC).isoformat(),
                "reset_type": "stats_reset",  # Not soft_delete
            },
        )

        await db.commit()

        # Track metrics
        from src.infrastructure.observability.metrics_agents import conversation_resets_total

        # No per-user label to avoid high cardinality (10K+ users = 10K+ time series)
        conversation_resets_total.inc()

        logger.info(
            "conversation_reset",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            message_count=message_count,
            total_tokens=total_tokens,
        )

    async def archive_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: dict[str, Any] | None,
        db: AsyncSession,
    ) -> ConversationMessage:
        """
        Archive message for fast UI display.

        Stores messages separately from LangGraph checkpoints for:
        - Fast UI pagination without deserializing checkpoints
        - Simple REST API for message history
        - Independent retention policies

        Args:
            conversation_id: Conversation UUID
            role: Message role ('user', 'assistant', 'system')
            content: Message text content
            metadata: Optional metadata (run_id, intention, confidence, etc.)
            db: Database session

        Returns:
            Created ConversationMessage instance

        Example:
            >>> await service.archive_message(
            ...     conversation_id,
            ...     "user",
            ...     "Hello assistant",
            ...     {"run_id": "abc123"}
            ... )
        """
        repo = ConversationRepository(db)
        message = await repo.create_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
        )

        # Note: Caller is responsible for commit to allow batching

        return message

    async def update_last_user_message(
        self,
        conversation_id: UUID,
        new_content: str,
        metadata_updates: dict[str, Any] | None,
        db: AsyncSession,
    ) -> ConversationMessage | None:
        """
        Update the last user message content and metadata.

        Used for HITL EDIT decisions to replace the original user intent
        with the reformulated one, maintaining conversation coherence.

        Args:
            conversation_id: Conversation UUID
            new_content: New message content to replace original
            metadata_updates: Optional metadata to merge with existing
            db: Database session

        Returns:
            Updated ConversationMessage instance, or None if no user message found

        Example:
            >>> await service.update_last_user_message(
            ...     conversation_id,
            ...     "recherche jean",
            ...     {"hitl_edit": True, "original_content": "recherche jean"}
            ... )
        """
        repo = ConversationRepository(db)
        last_user_message = await repo.get_last_user_message(conversation_id)

        if last_user_message:
            # Store original content in metadata before update
            original_content = last_user_message.content
            updated_metadata = last_user_message.message_metadata or {}

            # Merge new metadata
            if metadata_updates:
                updated_metadata.update(metadata_updates)

            # Add original content to metadata for traceability
            if "hitl_original_content" not in updated_metadata:
                updated_metadata["hitl_original_content"] = original_content

            # Update content and metadata
            last_user_message.content = new_content
            last_user_message.message_metadata = updated_metadata

            logger.info(
                "last_user_message_updated",
                conversation_id=str(conversation_id),
                original_content_preview=(
                    original_content[:50] if len(original_content) > 50 else original_content
                ),
                new_content=new_content,
            )

            return last_user_message
        else:
            logger.warning(
                "no_user_message_to_update",
                conversation_id=str(conversation_id),
            )
            return None

    async def increment_conversation_stats(
        self, conversation_id: UUID, tokens: int, db: AsyncSession, message_increment: int = 1
    ) -> None:
        """
        Update conversation statistics: message count and total tokens.

        Args:
            conversation_id: Conversation UUID
            tokens: Number of tokens to add to total
            db: Database session
            message_increment: Number of messages to add (default: 1).
                               Use 2 for user+assistant pair, 0 for token-only updates.

        Note:
            Caller is responsible for commit to allow transaction batching.
        """
        repo = ConversationRepository(db)
        conversation = await repo.get_by_id(conversation_id)

        if conversation:
            conversation.message_count += message_increment
            conversation.total_tokens += tokens

            logger.debug(
                "conversation_stats_incremented",
                conversation_id=str(conversation_id),
                new_message_count=conversation.message_count,
                new_total_tokens=conversation.total_tokens,
                message_increment=message_increment,
            )
        else:
            logger.warning(
                "conversation_not_found_for_stats_update",
                conversation_id=str(conversation_id),
            )

    async def get_messages(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        hide_hitl_approvals: bool = False,
    ) -> list[ConversationMessage]:
        """
        Get conversation message history for UI display.

        Messages are returned in descending order (newest first) for pagination.
        By default, shows ALL messages including HITL APPROVE/REJECT responses
        for complete conversation history and accurate token/message counting.

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            hide_hitl_approvals: If True, exclude HITL APPROVE/REJECT responses from history.
                                 EDIT/AMBIGUOUS are always kept for context.
                                 Default: False (show all messages)

        Returns:
            List of ConversationMessage (newest first)

        Example:
            >>> # Default: Show ALL messages including HITL
            >>> messages = await service.get_messages(user_id, limit=50, db=db)
            >>>
            >>> # Hide HITL APPROVE/REJECT responses (legacy behavior)
            >>> filtered_messages = await service.get_messages(
            ...     user_id, limit=50, db=db, hide_hitl_approvals=True
            ... )

        Filter Logic (when hide_hitl_approvals=True):
            Excluded messages:
            - role="user" AND metadata.hitl_response=True AND metadata.decision_type="APPROVE"
            - role="user" AND metadata.hitl_response=True AND metadata.decision_type="REJECT"
            - role="assistant" AND metadata.hitl_question=True

            Kept messages:
            - All assistant messages (non-HITL)
            - All regular user messages (no HITL)
            - HITL EDIT responses
            - HITL AMBIGUOUS responses
        """
        # Get active conversation
        conversation = await self.get_active_conversation(user_id, db)

        if not conversation:
            return []

        # Query messages using repository
        repo = ConversationRepository(db)
        messages = await repo.get_messages_for_conversation(
            conversation_id=conversation.id,
            limit=limit,
        )

        # Filter trivial HITL responses (APPROVE, REJECT) if requested
        if hide_hitl_approvals:
            messages = self._filter_hitl_messages(messages)

        logger.debug(
            "messages_loaded",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=len(messages),
            limit=limit,
            hide_hitl_approvals=hide_hitl_approvals,
        )

        return list(messages)

    async def get_audit_logs(
        self, user_id: UUID, db: AsyncSession, limit: int = 100
    ) -> list[ConversationAuditLog]:
        """
        Get conversation audit logs for user.

        Useful for debugging, compliance, and support.

        Args:
            user_id: User UUID
            db: Database session
            limit: Maximum number of logs to return

        Returns:
            List of ConversationAuditLog (newest first)
        """
        repo = ConversationRepository(db)
        return list(await repo.get_audit_logs(user_id=user_id, limit=limit))

    async def get_messages_with_tokens(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        hide_hitl_approvals: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get conversation message history with token usage and recalculated cost.

        JOINs conversation_messages with message_token_summary via run_id in metadata,
        then recalculates cost using current llm_model_pricing table.

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            hide_hitl_approvals: If True, exclude HITL APPROVE/REJECT responses from history.
                                 Default: False (show all messages for complete token counting)

        Returns:
            List of dicts with message fields + tokens_in/out/cache/cost_eur

        Example:
            >>> messages = await service.get_messages_with_tokens(user_id, 50, db)
            >>> for msg in messages:
            ...     print(f"{msg['role']}: tokens_in={msg['tokens_in']}, cost={msg['cost_eur']} EUR")
        """
        # Get active conversation
        conversation = await self.get_active_conversation(user_id, db)

        if not conversation:
            return []

        # Query messages using repository
        conv_repo = ConversationRepository(db)
        messages = await conv_repo.get_messages_for_conversation(
            conversation_id=conversation.id,
            limit=limit,
        )

        # Extract run_ids from message metadata
        run_ids = [
            msg.message_metadata.get(FIELD_RUN_ID)
            for msg in messages
            if msg.message_metadata and msg.message_metadata.get(FIELD_RUN_ID)
        ]

        # Load token summaries using ChatRepository (batch query)
        from src.domains.chat.repository import ChatRepository

        chat_repo = ChatRepository(db)
        token_summaries = {}
        if run_ids:
            token_summaries = await chat_repo.get_token_summaries_by_run_ids(run_ids)

        # Build enriched message list
        enriched_messages = []
        for msg in messages:
            # Base message data (use message_metadata to match model attribute)
            msg_data = {
                "id": msg.id,
                "role": msg.role,
                FIELD_CONTENT: msg.content,
                "message_metadata": msg.message_metadata,  # Use actual model field name
                "created_at": msg.created_at,
                FIELD_TOKENS_IN: None,
                FIELD_TOKENS_OUT: None,
                FIELD_TOKENS_CACHE: None,
                FIELD_COST_EUR: None,
                FIELD_GOOGLE_API_REQUESTS: None,
            }

            # Add token data if available (from batch query, no extra queries needed)
            run_id = msg.message_metadata.get(FIELD_RUN_ID) if msg.message_metadata else None
            if run_id and run_id in token_summaries:
                summary = token_summaries[run_id]
                msg_data[FIELD_TOKENS_IN] = summary.total_prompt_tokens
                msg_data[FIELD_TOKENS_OUT] = summary.total_completion_tokens
                msg_data[FIELD_TOKENS_CACHE] = summary.total_cached_tokens
                # Use historical cost from message_token_summary (stored at execution time)
                # Include Google API costs for accurate total billing display
                llm_cost = float(summary.total_cost_eur) if summary.total_cost_eur else 0.0
                google_cost = (
                    float(summary.google_api_cost_eur) if summary.google_api_cost_eur else 0.0
                )
                msg_data[FIELD_COST_EUR] = (
                    llm_cost + google_cost if (llm_cost or google_cost) else None
                )
                # Google API tracking
                msg_data[FIELD_GOOGLE_API_REQUESTS] = summary.google_api_requests

            enriched_messages.append(msg_data)

        # Filter trivial HITL responses (APPROVE, REJECT) if requested
        if hide_hitl_approvals:
            enriched_messages = self._filter_hitl_messages_dict(enriched_messages)

        # Filter assistant messages with empty/whitespace-only content (ephemeral progress messages)
        # Also filter out None values that may have been introduced by upstream processing
        enriched_messages = [
            msg
            for msg in enriched_messages
            if msg is not None
            and not (msg.get("role") == "assistant" and not msg.get(FIELD_CONTENT, "").strip())
        ]

        # Show tokens only on the NEWEST assistant message per run_id
        # (in HITL flows, multiple assistant messages may share same run_id)
        # Note: Messages are in DESC order (newest first), so we want the FIRST occurrence
        run_id_to_newest_assistant_index: dict[str, int] = {}
        for i, msg in enumerate(enriched_messages):
            if msg.get("role") == "assistant" and (msg.get("message_metadata") or {}).get(
                FIELD_RUN_ID
            ):
                run_id = (msg.get("message_metadata") or {})[FIELD_RUN_ID]
                # Keep only the first occurrence (newest message since DESC order)
                if run_id not in run_id_to_newest_assistant_index:
                    run_id_to_newest_assistant_index[run_id] = i

        # Clear tokens from all assistant messages except the newest one per run_id
        for i, msg in enumerate(enriched_messages):
            if msg.get("role") == "assistant" and (msg.get("message_metadata") or {}).get(
                FIELD_RUN_ID
            ):
                run_id = (msg.get("message_metadata") or {})[FIELD_RUN_ID]
                if i != run_id_to_newest_assistant_index[run_id]:
                    # Not the newest message for this run_id → hide tokens
                    msg[FIELD_TOKENS_IN] = None
                    msg[FIELD_TOKENS_OUT] = None
                    msg[FIELD_TOKENS_CACHE] = None
                    msg[FIELD_COST_EUR] = None
                    msg[FIELD_GOOGLE_API_REQUESTS] = None

        logger.debug(
            "messages_with_tokens_loaded",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=len(enriched_messages),
            with_tokens=len([m for m in enriched_messages if m.get(FIELD_TOKENS_IN) is not None]),
            hide_hitl_approvals=hide_hitl_approvals,
        )

        return enriched_messages

    async def get_messages_with_tokens_v2(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        hide_hitl_approvals: bool = False,
    ) -> list[dict[str, Any]]:
        """
        OPTIMIZED version of get_messages_with_tokens using ConversationRepository.

        Uses LEFT JOIN to fetch messages and token summaries in a single query,
        eliminating N+1 query problem. Controlled by USE_CONVERSATION_REPOSITORY feature flag.

        Performance improvements:
        - OLD: 1 query for messages + 1 query for token summaries + N queries for logs
        - NEW: 1 query with LEFT JOIN for messages+tokens + batch query for logs
        - Reduction: ~50% fewer database roundtrips for typical conversation

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            hide_hitl_approvals: If True, exclude HITL APPROVE/REJECT responses from history.
                                 Default: False (show all messages for complete token counting)

        Returns:
            List of dicts with message fields + tokens_in/out/cache/cost_eur
            (same format as get_messages_with_tokens for drop-in replacement)

        Example:
            >>> # In router, check feature flag:
            >>> if settings.use_conversation_repository:
            >>>     messages = await service.get_messages_with_tokens_v2(user_id, 50, db)
            >>> else:
            >>>     messages = await service.get_messages_with_tokens(user_id, 50, db)
        """
        # Get active conversation
        conversation = await self.get_active_conversation(user_id, db)

        if not conversation:
            return []

        # Use optimized repository method (single LEFT JOIN query)
        # Returns messages with token summary including cost_eur (historical cost)
        repo = ConversationRepository(db)
        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=limit,
        )

        # Build enriched message list - O(n) with no additional DB queries
        enriched_messages = []
        for message, token_dict in results:
            msg_data = {
                "id": message.id,
                "role": message.role,
                FIELD_CONTENT: message.content,
                "message_metadata": message.message_metadata,
                "created_at": message.created_at,
                FIELD_TOKENS_IN: None,
                FIELD_TOKENS_OUT: None,
                FIELD_TOKENS_CACHE: None,
                FIELD_COST_EUR: None,
                FIELD_GOOGLE_API_REQUESTS: None,
            }

            # Add token data if available (from LEFT JOIN, no extra queries needed)
            if token_dict:
                msg_data[FIELD_TOKENS_IN] = token_dict["prompt_tokens"]
                msg_data[FIELD_TOKENS_OUT] = token_dict["completion_tokens"]
                msg_data[FIELD_TOKENS_CACHE] = token_dict["cached_tokens"]
                # Use historical cost from message_token_summary (stored at execution time)
                msg_data[FIELD_COST_EUR] = token_dict.get("cost_eur")
                # Google API tracking
                msg_data[FIELD_GOOGLE_API_REQUESTS] = token_dict.get(FIELD_GOOGLE_API_REQUESTS)

            enriched_messages.append(msg_data)

        # Filter trivial HITL responses (APPROVE, REJECT) if requested
        if hide_hitl_approvals:
            enriched_messages = self._filter_hitl_messages_dict(enriched_messages)

        # Filter assistant messages with empty/whitespace-only content (ephemeral progress messages)
        # Also filter out None values that may have been introduced by upstream processing
        enriched_messages = [
            msg
            for msg in enriched_messages
            if msg is not None
            and not (msg.get("role") == "assistant" and not msg.get(FIELD_CONTENT, "").strip())
        ]

        # Show tokens only on the NEWEST assistant message per run_id
        # (in HITL flows, multiple assistant messages may share same run_id)
        # Note: Messages are in DESC order (newest first), so we want the FIRST occurrence
        run_id_to_newest_assistant_index: dict[str, int] = {}
        for i, msg in enumerate(enriched_messages):
            if msg.get("role") == "assistant" and (msg.get("message_metadata") or {}).get(
                FIELD_RUN_ID
            ):
                run_id = (msg.get("message_metadata") or {})[FIELD_RUN_ID]
                # Keep only the first occurrence (newest message since DESC order)
                if run_id not in run_id_to_newest_assistant_index:
                    run_id_to_newest_assistant_index[run_id] = i

        # Clear tokens from all assistant messages except the newest one per run_id
        for i, msg in enumerate(enriched_messages):
            if msg.get("role") == "assistant" and (msg.get("message_metadata") or {}).get(
                FIELD_RUN_ID
            ):
                run_id = (msg.get("message_metadata") or {})[FIELD_RUN_ID]
                if i != run_id_to_newest_assistant_index[run_id]:
                    # Not the newest message for this run_id → hide tokens
                    msg[FIELD_TOKENS_IN] = None
                    msg[FIELD_TOKENS_OUT] = None
                    msg[FIELD_TOKENS_CACHE] = None
                    msg[FIELD_COST_EUR] = None
                    msg[FIELD_GOOGLE_API_REQUESTS] = None

        logger.debug(
            "messages_with_tokens_loaded_v2_optimized",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=len(enriched_messages),
            with_tokens=len([m for m in enriched_messages if m.get(FIELD_TOKENS_IN) is not None]),
            optimization="left_join_repository",
            hide_hitl_approvals=hide_hitl_approvals,
        )

        return enriched_messages

    async def get_messages_with_tokens_auto(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        hide_hitl_approvals: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Automatic routing between old and new implementation based on feature flag.

        This method acts as a router that automatically selects the optimized
        implementation when USE_CONVERSATION_REPOSITORY=true in .env.

        Use this in production code for safe, progressive rollout:
        1. Deploy with flag=false (uses old implementation)
        2. Test in staging with flag=true
        3. Enable in production when validated
        4. Monitor metrics to compare performance

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            hide_hitl_approvals: If True, exclude HITL APPROVE/REJECT responses from history.
                                 Default: False (show all messages for complete token counting)

        Returns:
            List of dicts with message fields + tokens_in/out/cache/cost_eur
        """
        from src.infrastructure.observability.metrics_agents import (
            conversation_messages_query_duration_seconds,
        )

        # Always use optimized v2 implementation (N+1 query fix)
        with conversation_messages_query_duration_seconds.labels(version="v2").time():
            return await self.get_messages_with_tokens_v2(
                user_id, limit, db, hide_hitl_approvals=hide_hitl_approvals
            )

    async def get_conversation_totals(self, user_id: UUID, db: AsyncSession) -> dict[str, Any]:
        """
        Get conversation totals: aggregate tokens and historical cost.

        Returns aggregated token usage and cost from message_token_summary.
        Cost reflects historical prices at time of execution (not recalculated).

        Performance: Single SQL query with SUM aggregations - O(1) regardless
        of conversation length. Optimized for resource-constrained environments.

        Args:
            user_id: User UUID
            db: Database session

        Returns:
            Dict with conversation_id, total_tokens_in/out/cache, total_cost_eur

        Example:
            >>> totals = await service.get_conversation_totals(user_id, db)
            >>> print(f"Total: {totals[FIELD_TOTAL_COST_EUR]} EUR")
        """
        # Get active conversation
        conversation = await self.get_active_conversation(user_id, db)

        if not conversation:
            return {
                FIELD_CONVERSATION_ID: None,
                FIELD_TOTAL_TOKENS_IN: 0,
                FIELD_TOTAL_TOKENS_OUT: 0,
                FIELD_TOTAL_TOKENS_CACHE: 0,
                FIELD_TOTAL_COST_EUR: 0.0,
            }

        # Get aggregated token totals and cost using repository (single query)
        # Repository returns standardized keys matching field_names constants
        conv_repo = ConversationRepository(db)
        token_totals = await conv_repo.get_token_totals(conversation.id)

        logger.debug(
            "conversation_totals_calculated",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            **token_totals,
        )

        return {
            FIELD_CONVERSATION_ID: conversation.id,
            **token_totals,  # Contains FIELD_TOTAL_TOKENS_IN/OUT/CACHE, FIELD_TOTAL_COST_EUR
        }

    def _generate_title(self) -> str:
        """
        Generate default conversation title.

        Format: "Conversation du DD/MM/YYYY" (French default)

        Returns:
            Generated title string
        """
        now = datetime.now(UTC)
        return f"Conversation du {now.strftime('%d/%m/%Y')}"
