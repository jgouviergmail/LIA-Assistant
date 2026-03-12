"""
Conversation repository for database operations.

Implements repository pattern for conversation domain, extending BaseRepository.
Provides data access layer with optimized queries.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.field_names import (
    FIELD_CREATED_AT,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_RUN_ID,
    FIELD_TOTAL_COST_EUR,
    FIELD_TOTAL_GOOGLE_API_REQUESTS,
    FIELD_TOTAL_TOKENS_CACHE,
    FIELD_TOTAL_TOKENS_IN,
    FIELD_TOTAL_TOKENS_OUT,
)
from src.core.repository import BaseRepository
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ConversationRepository(BaseRepository[Conversation]):
    """
    Repository for conversation database operations.

    Extends BaseRepository to provide domain-specific queries with proper
    error handling, logging, and optimization patterns.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize conversation repository.

        Args:
            db: SQLAlchemy async session
        """
        super().__init__(db, Conversation)

    async def get_active_for_user(self, user_id: UUID) -> Conversation | None:
        """
        Get active (non-deleted) conversation for user.

        Current implementation: 1:1 mapping between user and conversation.
        Future: May support multiple conversations per user.

        Args:
            user_id: User UUID

        Returns:
            Active conversation or None if not exists

        Example:
            >>> repo = ConversationRepository(db)
            >>> conversation = await repo.get_active_for_user(user_id)
            >>> if conversation:
            ...     print(f"Found conversation {conversation.id}")
        """
        try:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .where(Conversation.deleted_at.is_(None))
                .order_by(Conversation.created_at.desc())
                .limit(1)
            )

            result = await self.db.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                logger.debug(
                    "active_conversation_found",
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                )
            else:
                logger.debug(
                    "no_active_conversation",
                    user_id=str(user_id),
                )

            return conversation

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_active_conversation_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def get_soft_deleted_for_user(self, user_id: UUID) -> Conversation | None:
        """
        Get soft-deleted conversation for user (deleted_at IS NOT NULL).

        Used by get_or_create to check if a conversation needs reactivation
        instead of creating a new one (which would violate unique constraint).

        Args:
            user_id: User UUID

        Returns:
            Soft-deleted conversation or None if not exists
        """
        try:
            stmt = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .where(Conversation.deleted_at.isnot(None))
                .order_by(Conversation.deleted_at.desc())
                .limit(1)
            )

            result = await self.db.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                logger.debug(
                    "soft_deleted_conversation_found",
                    user_id=str(user_id),
                    conversation_id=str(conversation.id),
                    deleted_at=str(conversation.deleted_at),
                )

            return conversation

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_soft_deleted_conversation_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def reactivate_conversation(
        self,
        conversation: Conversation,
        new_title: str | None = None,
    ) -> Conversation:
        """
        Reactivate a soft-deleted conversation.

        Clears deleted_at and optionally resets title.
        Message count and tokens are preserved.

        Args:
            conversation: Soft-deleted conversation to reactivate
            new_title: Optional new title (if None, keeps existing)

        Returns:
            Reactivated conversation
        """
        from datetime import UTC, datetime

        try:
            conversation.deleted_at = None
            if new_title:
                conversation.title = new_title

            # Create audit log for reactivation
            audit = ConversationAuditLog(
                user_id=conversation.user_id,
                conversation_id=conversation.id,
                action="reactivated",
                message_count_at_action=conversation.message_count,
                audit_metadata={
                    "reactivated_at": datetime.now(UTC).isoformat(),
                    "previous_deleted_at": (
                        str(conversation.deleted_at) if conversation.deleted_at else None
                    ),
                },
            )
            self.db.add(audit)

            await self.db.flush()
            await self.db.refresh(conversation)

            logger.info(
                "conversation_reactivated",
                user_id=str(conversation.user_id),
                conversation_id=str(conversation.id),
            )

            return conversation

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "reactivate_conversation_failed",
                conversation_id=str(conversation.id),
                error=str(e),
            )
            raise

    async def get_messages_for_conversation(
        self,
        conversation_id: UUID,
        limit: int = 50,
        order_desc: bool = True,
    ) -> Sequence[ConversationMessage]:
        """
        Get messages for a conversation with optional limit and ordering.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum number of messages to return
            order_desc: If True, order by created_at DESC (newest first)

        Returns:
            List of conversation messages

        Example:
            >>> messages = await repo.get_messages_for_conversation(
            ...     conversation_id=conv_id,
            ...     limit=50,
            ...     order_desc=True
            ... )
        """
        try:
            stmt = select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id
            )

            if order_desc:
                stmt = stmt.order_by(ConversationMessage.created_at.desc())
            else:
                stmt = stmt.order_by(ConversationMessage.created_at.asc())

            if limit > 0:
                stmt = stmt.limit(limit)

            result = await self.db.execute(stmt)
            messages = result.scalars().all()

            logger.debug(
                "messages_retrieved",
                conversation_id=str(conversation_id),
                count=len(messages),
                limit=limit,
            )

            return messages

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_messages_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def get_messages_with_token_summaries(
        self,
        conversation_id: UUID,
        limit: int = 50,
    ) -> Sequence[tuple[ConversationMessage, dict]]:
        """
        Get messages with their token summaries in a single optimized query.

        OPTIMIZATION: Uses LEFT JOIN instead of N+1 queries.
        This is the optimized version that eliminates the N+1 problem.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum number of messages

        Returns:
            List of (message, token_summary_dict) tuples

        Performance:
            - Old: 1 query for messages + N queries for token summaries
            - New: 1 query with LEFT JOIN
            - Improvement: ~50% faster for typical conversation

        Example:
            >>> results = await repo.get_messages_with_token_summaries(conv_id)
            >>> for message, token_summary in results:
            ...     if token_summary:
            ...         print(f"Message used {token_summary['total_tokens']} tokens")
        """
        try:
            from src.domains.chat.models import MessageTokenSummary

            # LEFT JOIN to get messages and their token summaries in one query
            stmt = (
                select(ConversationMessage, MessageTokenSummary)
                .outerjoin(
                    MessageTokenSummary,
                    ConversationMessage.message_metadata[FIELD_RUN_ID].astext
                    == MessageTokenSummary.run_id,
                )
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            rows = result.all()

            # Convert to list of (message, token_summary_dict)
            results = []
            for message, token_summary in rows:
                token_dict = None
                if token_summary:
                    total_tokens = (
                        token_summary.total_prompt_tokens + token_summary.total_completion_tokens
                    )
                    token_dict = {
                        FIELD_RUN_ID: token_summary.run_id,
                        "total_tokens": total_tokens,
                        "prompt_tokens": token_summary.total_prompt_tokens,
                        "completion_tokens": token_summary.total_completion_tokens,
                        "cached_tokens": token_summary.total_cached_tokens,
                        "cost_eur": (
                            float(token_summary.total_cost_eur)
                            if token_summary.total_cost_eur
                            else None
                        ),
                        FIELD_GOOGLE_API_REQUESTS: token_summary.google_api_requests,
                    }
                results.append((message, token_dict))

            logger.debug(
                "messages_with_tokens_retrieved",
                conversation_id=str(conversation_id),
                count=len(results),
                optimization="left_join",
            )

            return results

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_messages_with_tokens_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def delete_messages_for_conversation(
        self,
        conversation_id: UUID,
    ) -> int:
        """
        Delete all messages for a conversation (for reset operation).

        Args:
            conversation_id: Conversation UUID

        Returns:
            Number of messages deleted

        Example:
            >>> count = await repo.delete_messages_for_conversation(conv_id)
            >>> print(f"Deleted {count} messages")
        """
        try:
            from sqlalchemy import delete

            stmt = delete(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id
            )

            result = await self.db.execute(stmt)
            count = result.rowcount

            logger.info(
                "messages_deleted",
                conversation_id=str(conversation_id),
                count=count,
            )

            return count

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "delete_messages_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def get_conversation_with_messages(
        self,
        conversation_id: UUID,
        message_limit: int = 50,
    ) -> Conversation | None:
        """
        Get conversation with its messages eagerly loaded.

        Uses selectinload to avoid N+1 queries when accessing messages.

        Args:
            conversation_id: Conversation UUID
            message_limit: Maximum messages to load

        Returns:
            Conversation with messages loaded, or None

        Example:
            >>> conv = await repo.get_conversation_with_messages(conv_id, limit=10)
            >>> if conv:
            ...     # Messages are already loaded, no extra query
            ...     for msg in conv.messages[:10]:
            ...         print(msg.content)
        """
        try:
            # Note: selectinload doesn't support limit() in SQLAlchemy
            # We load the conversation with messages and then slice in Python
            stmt = (
                select(Conversation)
                .where(Conversation.id == conversation_id)
                .options(selectinload(Conversation.messages))
            )

            result = await self.db.execute(stmt)
            conversation = result.scalar_one_or_none()

            if conversation:
                # Limit messages in Python (already ordered by DESC in relationship definition)
                if len(conversation.messages) > message_limit:
                    conversation.messages = conversation.messages[:message_limit]

                logger.debug(
                    "conversation_with_messages_loaded",
                    conversation_id=str(conversation_id),
                    message_count=len(conversation.messages),
                )

            return conversation

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_conversation_with_messages_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def create_with_audit(
        self,
        user_id: UUID,
        title: str,
        initial_message_count: int = 0,
        initial_tokens: int = 0,
    ) -> Conversation:
        """
        Create conversation with audit log entry in a single operation.

        Encapsulates conversation creation + audit log for atomicity.

        Args:
            user_id: User UUID (also used as conversation_id for 1:1 mapping)
            title: Conversation title
            initial_message_count: Starting message count (default: 0)
            initial_tokens: Starting token count (default: 0)

        Returns:
            Created conversation with audit log

        Example:
            >>> conversation = await repo.create_with_audit(
            ...     user_id=user_id,
            ...     title="New conversation",
            ...     initial_message_count=0,
            ...     initial_tokens=0
            ... )
        """
        from datetime import UTC, datetime

        try:
            # Create conversation
            conversation = Conversation(
                id=user_id,
                user_id=user_id,
                title=title,
                message_count=initial_message_count,
                total_tokens=initial_tokens,
            )
            self.db.add(conversation)

            # Create audit log
            audit = ConversationAuditLog(
                user_id=user_id,
                conversation_id=user_id,
                action="created",
                message_count_at_action=initial_message_count,
                audit_metadata={FIELD_CREATED_AT: datetime.now(UTC).isoformat()},
            )
            self.db.add(audit)

            await self.db.flush()
            await self.db.refresh(conversation)

            logger.info(
                "conversation_created_with_audit",
                conversation_id=str(conversation.id),
                user_id=str(user_id),
                title=title,
            )

            return conversation

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_conversation_with_audit_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def create_audit_log(
        self,
        user_id: UUID,
        conversation_id: UUID,
        action: str,
        message_count_at_action: int,
        metadata: dict | None = None,
    ) -> ConversationAuditLog:
        """
        Create an audit log entry for conversation operations.

        Args:
            user_id: User UUID
            conversation_id: Conversation UUID
            action: Action type (e.g., "created", "reset", "deleted")
            message_count_at_action: Message count when action occurred
            metadata: Additional metadata (JSON)

        Returns:
            Created audit log

        Example:
            >>> audit = await repo.create_audit_log(
            ...     user_id=user_id,
            ...     conversation_id=conv_id,
            ...     action="reset",
            ...     message_count_at_action=10,
            ...     metadata={"total_tokens": 1000}
            ... )
        """
        try:
            audit = ConversationAuditLog(
                user_id=user_id,
                conversation_id=conversation_id,
                action=action,
                message_count_at_action=message_count_at_action,
                audit_metadata=metadata or {},
            )
            self.db.add(audit)
            await self.db.flush()
            await self.db.refresh(audit)

            logger.info(
                "audit_log_created",
                conversation_id=str(conversation_id),
                action=action,
                user_id=str(user_id),
            )

            return audit

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_audit_log_failed",
                conversation_id=str(conversation_id),
                action=action,
                error=str(e),
            )
            raise

    async def create_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationMessage:
        """
        Create a conversation message.

        Args:
            conversation_id: Conversation UUID
            role: Message role ("user" or "assistant")
            content: Message content
            metadata: Additional metadata (JSON)

        Returns:
            Created message

        Example:
            >>> message = await repo.create_message(
            ...     conversation_id=conv_id,
            ...     role="user",
            ...     content="Hello",
            ...     metadata={"run_id": "abc123"}
            ... )
        """
        try:
            message = ConversationMessage(
                conversation_id=conversation_id,
                role=role,
                content=content,
                message_metadata=metadata or {},
            )
            self.db.add(message)
            await self.db.flush()
            await self.db.refresh(message)

            logger.debug(
                "message_created",
                conversation_id=str(conversation_id),
                role=role,
                content_length=len(content),
            )

            return message

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_message_failed",
                conversation_id=str(conversation_id),
                role=role,
                error=str(e),
            )
            raise

    async def get_last_user_message(
        self,
        conversation_id: UUID,
    ) -> ConversationMessage | None:
        """
        Get the most recent user message for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Last user message or None if no user messages exist

        Example:
            >>> last_msg = await repo.get_last_user_message(conv_id)
            >>> if last_msg:
            ...     print(f"Last user message: {last_msg.content}")
        """
        from sqlalchemy import desc

        try:
            stmt = (
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.role == "user",
                )
                .order_by(desc(ConversationMessage.created_at))
                .limit(1)
            )

            result = await self.db.execute(stmt)
            message = result.scalar_one_or_none()

            if message:
                logger.debug(
                    "last_user_message_found",
                    conversation_id=str(conversation_id),
                    message_id=message.id,
                )

            return message

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_last_user_message_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def get_proactive_messages_after(
        self,
        conversation_id: UUID,
        after_timestamp: datetime,
        limit: int = 5,
    ) -> Sequence[ConversationMessage]:
        """
        Get proactive notification messages created after a given timestamp.

        Retrieves assistant messages with metadata.type starting with 'proactive_'
        (e.g., 'proactive_interest', 'proactive_birthday') created after the
        specified timestamp. Used to inject proactive messages into LangGraph
        state so the LLM has context when a user replies to a notification.

        Args:
            conversation_id: Conversation UUID
            after_timestamp: Only return messages created after this (timezone-aware)
            limit: Maximum number of messages to return

        Returns:
            List of proactive messages ordered by created_at ASC (chronological)

        Example:
            >>> from datetime import UTC, datetime, timedelta
            >>> cutoff = datetime.now(UTC) - timedelta(hours=24)
            >>> messages = await repo.get_proactive_messages_after(
            ...     conversation_id=conv_id,
            ...     after_timestamp=cutoff,
            ...     limit=5,
            ... )
        """
        try:
            stmt = (
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.role == "assistant",
                    ConversationMessage.created_at > after_timestamp,
                    ConversationMessage.message_metadata["type"].astext.like("proactive_%"),
                )
                .order_by(ConversationMessage.created_at.asc())
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            messages = result.scalars().all()

            logger.debug(
                "proactive_messages_retrieved",
                conversation_id=str(conversation_id),
                after_timestamp=after_timestamp.isoformat(),
                count=len(messages),
                limit=limit,
            )

            return messages

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_proactive_messages_after_failed",
                conversation_id=str(conversation_id),
                after_timestamp=after_timestamp.isoformat(),
                error=str(e),
            )
            raise

    async def get_audit_logs(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> Sequence[ConversationAuditLog]:
        """
        Get audit logs for a user's conversations.

        Args:
            user_id: User UUID
            limit: Maximum number of logs to return

        Returns:
            List of audit logs ordered by created_at DESC

        Example:
            >>> logs = await repo.get_audit_logs(user_id, limit=20)
            >>> for log in logs:
            ...     print(f"{log.action} at {log.created_at}")
        """
        try:
            stmt = (
                select(ConversationAuditLog)
                .where(ConversationAuditLog.user_id == user_id)
                .order_by(ConversationAuditLog.created_at.desc())
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            logs = result.scalars().all()

            logger.debug(
                "audit_logs_retrieved",
                user_id=str(user_id),
                count=len(logs),
                limit=limit,
            )

            return logs

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_audit_logs_failed",
                user_id=str(user_id),
                error=str(e),
            )
            raise

    async def get_token_totals(
        self,
        conversation_id: UUID,
    ) -> dict[str, int | float]:
        """
        Get aggregated token totals and historical cost for a conversation.

        Returns sum of all prompt tokens, completion tokens, cached tokens,
        and total cost in EUR (historical cost at time of execution).

        Performance: Single SQL query with SUM aggregations - O(1) regardless
        of conversation length.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Dictionary with standardized keys (from field_names.py):
                - total_tokens_in: Total prompt tokens
                - total_tokens_out: Total completion tokens
                - total_tokens_cache: Total cached tokens
                - total_cost_eur: Historical total cost in EUR

        Example:
            >>> totals = await repo.get_token_totals(conv_id)
            >>> print(f"Used {totals[FIELD_TOTAL_TOKENS_IN]} tokens")
        """
        from sqlalchemy import func

        from src.domains.chat.models import MessageTokenSummary

        try:
            stmt = select(
                func.sum(MessageTokenSummary.total_prompt_tokens).label(FIELD_TOTAL_TOKENS_IN),
                func.sum(MessageTokenSummary.total_completion_tokens).label(FIELD_TOTAL_TOKENS_OUT),
                func.sum(MessageTokenSummary.total_cached_tokens).label(FIELD_TOTAL_TOKENS_CACHE),
                func.sum(MessageTokenSummary.total_cost_eur).label(FIELD_TOTAL_COST_EUR),
                func.sum(MessageTokenSummary.google_api_requests).label(
                    FIELD_TOTAL_GOOGLE_API_REQUESTS
                ),
            ).where(MessageTokenSummary.conversation_id == conversation_id)

            result = await self.db.execute(stmt)
            row = result.one()

            totals = {
                FIELD_TOTAL_TOKENS_IN: int(row.total_tokens_in or 0),
                FIELD_TOTAL_TOKENS_OUT: int(row.total_tokens_out or 0),
                FIELD_TOTAL_TOKENS_CACHE: int(row.total_tokens_cache or 0),
                FIELD_TOTAL_COST_EUR: float(row.total_cost_eur or 0.0),
                FIELD_TOTAL_GOOGLE_API_REQUESTS: int(row.total_google_api_requests or 0),
            }

            logger.debug(
                "token_totals_retrieved",
                conversation_id=str(conversation_id),
                **totals,
            )

            return totals

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_token_totals_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise
