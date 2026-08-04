"""
Conversation repository for database operations.

Implements repository pattern for conversation domain, extending BaseRepository.
Provides data access layer with optimized queries.
"""

from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.field_names import (
    FIELD_CREATED_AT,
    FIELD_FEEDBACK_SUBMITTED,
    FIELD_FEEDBACK_VALUE,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_RUN_ID,
    FIELD_TARGET_ID,
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

            # Prometheus: repository query counter (dashboard 09)
            with suppress(Exception):
                from src.infrastructure.observability.metrics_agents import (
                    conversation_repository_queries_total,
                )

                conversation_repository_queries_total.labels(version="v1").inc()

            logger.debug(
                "messages_retrieved",
                conversation_id=str(conversation_id),
                count=len(messages),
                limit=limit,
            )

            return messages

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            with suppress(Exception):
                from src.infrastructure.observability.metrics_agents import (
                    conversation_repository_errors_total,
                )

                conversation_repository_errors_total.labels(
                    version="v1", error_type=type(e).__name__
                ).inc()
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
        search: str | None = None,
        before_created_at: datetime | None = None,
    ) -> Sequence[tuple[ConversationMessage, dict[str, Any] | None]]:
        """
        Get messages with their token summaries in a single optimized query.

        OPTIMIZATION: Uses LEFT JOIN instead of N+1 queries.
        This is the optimized version that eliminates the N+1 problem.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum number of messages
            search: Optional substring to filter message content. Case- and
                    accent-insensitive (ILIKE + unaccent on both sides); LIKE
                    wildcards in the term are treated as literals.
            before_created_at: Keyset pagination cursor. When provided, only
                returns messages older than this timestamp (strict ``<``).
                Combined with the existing
                ``ix_conversation_messages_conv_created`` index for
                index-only scan, regardless of conversation length.

        Returns:
            List of (message, token_summary_dict) tuples.

            Pagination uses a **keyset (cursor)** strategy, not the
            offset-based ``tuple[list[T], int]`` convention used elsewhere in
            the codebase: a global ``COUNT(*)`` would be O(messages) per
            request (no cheap WHERE filter can short-circuit it) and is
            useless to the scroll-up UI, which only needs ``has_more``.
            ``has_more`` is computed by the caller via the ``limit + 1`` trick.

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
            )

            # Apply optional substring search filter on message content (QW-2):
            # case-insensitive (ILIKE) AND accent-insensitive — unaccent() on
            # both sides, same approach as the admin user search (extension
            # installed by migration add_unaccent_ext_001). LIKE wildcards in
            # the user's term are escaped so "50%" matches the literal text.
            if search:
                escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                stmt = stmt.where(
                    func.unaccent(ConversationMessage.content).ilike(
                        func.unaccent(f"%{escaped}%"), escape="\\"
                    )
                )

            # Keyset pagination: skip messages newer than (or equal to) the cursor.
            # Strict ``<`` matches the "older than" semantics used by the scroll-up
            # caller — the cursor is the ``created_at`` of the oldest message in the
            # previous page, which the client already holds.
            #
            # NOTE: collision on identical microsecond-precision ``created_at`` could
            # skip a message. Negligible in practice — upgrade to a composite
            # (created_at, id) cursor if collisions are observed.
            if before_created_at is not None:
                stmt = stmt.where(ConversationMessage.created_at < before_created_at)

            stmt = stmt.order_by(ConversationMessage.created_at.desc()).limit(limit)

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
                    # Include Google API costs in total for accurate billing
                    llm_cost = float(token_summary.total_cost_eur or 0)
                    google_cost = float(token_summary.google_api_cost_eur or 0)
                    total_cost = llm_cost + google_cost

                    token_dict = {
                        FIELD_RUN_ID: token_summary.run_id,
                        "total_tokens": total_tokens,
                        "prompt_tokens": token_summary.total_prompt_tokens,
                        "completion_tokens": token_summary.total_completion_tokens,
                        "cached_tokens": token_summary.total_cached_tokens,
                        "cost_eur": total_cost if total_cost > 0 else None,
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
            # AsyncSession.execute is typed Result[Any]; rowcount lives on the
            # concrete CursorResult returned for DML. getattr keeps it typed int
            # without a cast (mirrors health_metrics/repository.py).
            count: int = getattr(result, "rowcount", 0) or 0

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
        *,
        stt_provider: str | None = None,
        stt_audio_duration_seconds: Decimal | None = None,
        stt_cost_usd: Decimal | None = None,
        stt_cost_eur: Decimal | None = None,
        stt_usd_to_eur_rate: Decimal | None = None,
        tts_provider: str | None = None,
        tts_model: str | None = None,
        tts_characters: int | None = None,
        tts_cost_usd: Decimal | None = None,
        tts_cost_eur: Decimal | None = None,
        tts_usd_to_eur_rate: Decimal | None = None,
    ) -> ConversationMessage:
        """
        Create a conversation message.

        Args:
            conversation_id: Conversation UUID
            role: Message role ("user" or "assistant")
            content: Message content
            metadata: Additional metadata (JSON)
            stt_provider: STT provider name when this message was produced by
                a remote-STT transcription. NULL otherwise.
            stt_audio_duration_seconds: Duration of the audio segment.
            stt_cost_usd: STT cost in USD at the time of the call.
            stt_cost_eur: STT cost in EUR at the time of the call.
            stt_usd_to_eur_rate: USD→EUR rate used for the conversion.
            tts_provider: TTS provider name when this assistant message was
                synthesised by a paid provider (Edge stays NULL).
            tts_model: TTS model used (e.g. ``tts-1``, ``eleven_turbo_v2_5``).
            tts_characters: Number of characters synthesised for this bubble.
            tts_cost_usd / tts_cost_eur: TTS cost at synthesis time.
            tts_usd_to_eur_rate: USD→EUR rate used (audit trail).

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
                stt_provider=stt_provider,
                stt_audio_duration_seconds=stt_audio_duration_seconds,
                stt_cost_usd=stt_cost_usd,
                stt_cost_eur=stt_cost_eur,
                stt_usd_to_eur_rate=stt_usd_to_eur_rate,
                tts_provider=tts_provider,
                tts_model=tts_model,
                tts_characters=tts_characters,
                tts_cost_usd=tts_cost_usd,
                tts_cost_eur=tts_cost_eur,
                tts_usd_to_eur_rate=tts_usd_to_eur_rate,
            )
            self.db.add(message)
            await self.db.flush()
            await self.db.refresh(message)

            logger.debug(
                "message_created",
                conversation_id=str(conversation_id),
                role=role,
                content_length=len(content),
                stt_provider=stt_provider,
                tts_provider=tts_provider,
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

    async def update_message_tts(
        self,
        message_id: UUID,
        *,
        tts_provider: str,
        tts_model: str | None,
        tts_characters: int,
        tts_cost_usd: Decimal | None,
        tts_cost_eur: Decimal | None,
        tts_usd_to_eur_rate: Decimal | None,
    ) -> None:
        """Backfill TTS attribution on an already-archived assistant row.

        TTS happens AFTER the archive_message call (the voice synthesis
        finalisation runs once the LangGraph TrackingContext has exited).
        Rather than restructuring the run lifecycle, we archive the assistant
        bubble first with NULL TTS columns and UPDATE them once the synthesis
        records are flushed by the tracker.

        Idempotent: re-running with the same values is a no-op; the partial
        index ``ix_conversation_messages_tts_provider`` is updated only when
        the column transitions from NULL to non-NULL.

        Args:
            message_id: ID of the assistant ConversationMessage row.
            tts_provider: Provider name (paid only — Edge never reaches this).
            tts_model: Model used for synthesis.
            tts_characters: Total characters synthesised for the bubble.
            tts_cost_usd / tts_cost_eur: Cost at synthesis time.
            tts_usd_to_eur_rate: Exchange rate (audit trail).
        """
        from sqlalchemy import update as sa_update

        try:
            stmt = (
                sa_update(ConversationMessage)
                .where(ConversationMessage.id == message_id)
                .values(
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                    tts_characters=tts_characters,
                    tts_cost_usd=tts_cost_usd,
                    tts_cost_eur=tts_cost_eur,
                    tts_usd_to_eur_rate=tts_usd_to_eur_rate,
                )
            )
            await self.db.execute(stmt)
            await self.db.flush()

            logger.debug(
                "message_tts_updated",
                message_id=str(message_id),
                tts_provider=tts_provider,
                tts_characters=tts_characters,
                tts_cost_eur=float(tts_cost_eur) if tts_cost_eur is not None else None,
            )
        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            # Non-fatal: TTS was already produced and played, the cost is
            # also captured on user_statistics by create_or_update — losing
            # the per-message detail is degraded but not catastrophic.
            logger.warning(
                "update_message_tts_failed",
                message_id=str(message_id),
                error_type=type(e).__name__,
                error=str(e),
            )

    async def mark_proactive_feedback_submitted(
        self,
        user_id: UUID,
        target_id: UUID,
        feedback_value: str,
        run_id: str | None = None,
    ) -> int:
        """Persist proactive feedback state on the related message(s).

        Updates ``message_metadata`` JSONB on every ConversationMessage whose
        metadata references this ``target_id`` — an interest for a
        ``proactive_interest`` card, a heartbeat notification for a
        ``proactive_heartbeat`` one. The update adds two
        keys: ``feedback_submitted=true`` and ``feedback_value=<value>``.

        Scoped by ``user_id`` via conversation join to prevent cross-tenant
        writes. Uses ``jsonb_set`` with ``coalesce`` to handle NULL metadata.

        **``run_id`` narrows the write to ONE card.** An interest card carries
        the INTEREST as its ``target_id``, so target_id alone marks every
        notification that interest ever produced. Measured on the development
        database on 2026-08-03, one interest carried nine archived cards: a
        single verdict disabled the buttons on eight notifications the audit
        trail knew nothing about, leaving them unanswerable and permanently
        listed as "no feedback" in the history. The card carries the
        notification's ``run_id``, which is the granularity
        ``update_feedback_by_run_id`` already uses — passing it here makes both
        writes agree on what "this notification" means.

        Omitting it keeps the historical breadth, which is what the settings
        list (no notification behind the verdict) and heartbeat cards (whose
        ``target_id`` IS the notification) need.

        Args:
            user_id: Owner of the messages (security filter — never replaced by
                the run_id, which travels in a client payload and is not a
                secret).
            target_id: Identifier referenced as ``target_id`` in message metadata
                (interest id, heartbeat notification id, ...).
            feedback_value: One of "thumbs_up", "thumbs_down", "block".
            run_id: When given, only the card carrying this exact run_id is
                marked. An unknown value marks NOTHING rather than falling back
                to every card — the fallback would restore the over-reach.

        Returns:
            Number of messages updated (0 if no matching proactive messages).

        Raises:
            SQLAlchemyError: On database failure.
        """
        from sqlalchemy import cast, update
        from sqlalchemy.dialects.postgresql import JSONB, array

        try:
            conv_ids_subq = select(Conversation.id).where(Conversation.user_id == user_id)
            empty_jsonb = cast("{}", JSONB)

            predicates = [
                ConversationMessage.conversation_id.in_(conv_ids_subq),
                ConversationMessage.message_metadata[FIELD_TARGET_ID].astext == str(target_id),
            ]
            if run_id is not None:
                # ADDED to the owner scope, never substituted for it.
                predicates.append(
                    ConversationMessage.message_metadata[FIELD_RUN_ID].astext == run_id
                )

            stmt = (
                update(ConversationMessage)
                .where(*predicates)
                .values(
                    message_metadata=func.jsonb_set(
                        func.jsonb_set(
                            func.coalesce(
                                ConversationMessage.message_metadata,
                                empty_jsonb,
                            ),
                            array([FIELD_FEEDBACK_SUBMITTED]),
                            func.to_jsonb(True),
                        ),
                        array([FIELD_FEEDBACK_VALUE]),
                        func.to_jsonb(feedback_value),
                    )
                )
            )
            result = await self.db.execute(stmt)
            count: int = getattr(result, "rowcount", 0) or 0

            logger.debug(
                "interest_feedback_marked_on_messages",
                user_id=str(user_id),
                target_id=str(target_id),
                feedback_value=feedback_value,
                # Stated because it decides the BREADTH of the write: without
                # it the verdict lands on every card of the target.
                scoped_to_run=run_id is not None,
                messages_updated=count,
            )

            return count

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "mark_proactive_feedback_submitted_failed",
                user_id=str(user_id),
                target_id=str(target_id),
                error=str(e),
            )
            raise

    async def merge_message_metadata(
        self,
        message_id: UUID,
        extra: dict[str, Any],
    ) -> None:
        """Merge additional key-value pairs into an existing message's metadata.

        Uses a shallow merge: existing keys not present in *extra* are preserved,
        keys present in *extra* overwrite the old value.

        Args:
            message_id: Primary key of the ConversationMessage to update.
            extra: Dict of fields to merge into ``message_metadata``.

        Raises:
            SQLAlchemyError: On database failure.
        """
        try:
            stmt = select(ConversationMessage).where(ConversationMessage.id == message_id)
            result = await self.db.execute(stmt)
            message = result.scalar_one_or_none()

            if message is None:
                logger.warning(
                    "merge_message_metadata_not_found",
                    message_id=str(message_id),
                )
                return

            current = message.message_metadata or {}
            message.message_metadata = {**current, **extra}
            await self.db.flush()

            logger.debug(
                "message_metadata_merged",
                message_id=str(message_id),
                extra_keys=list(extra.keys()),
            )

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "merge_message_metadata_failed",
                message_id=str(message_id),
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
            # Include Google API costs in total cost for accurate billing
            stmt = select(
                func.sum(MessageTokenSummary.total_prompt_tokens).label(FIELD_TOTAL_TOKENS_IN),
                func.sum(MessageTokenSummary.total_completion_tokens).label(FIELD_TOTAL_TOKENS_OUT),
                func.sum(MessageTokenSummary.total_cached_tokens).label(FIELD_TOTAL_TOKENS_CACHE),
                (
                    func.sum(MessageTokenSummary.total_cost_eur)
                    + func.coalesce(func.sum(MessageTokenSummary.google_api_cost_eur), 0)
                ).label(FIELD_TOTAL_COST_EUR),
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
