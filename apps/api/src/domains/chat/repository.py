"""
Chat repository for token tracking database operations.

Implements repository pattern for MessageTokenSummary and TokenUsageLog models.
Provides data access layer for token tracking and statistics.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_MESSAGE_COUNT,
    FIELD_MODEL_NAME,
    FIELD_NODE_NAME,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.core.repository import BaseRepository
from src.domains.chat.models import (
    MessageTokenSummary,
    TokenUsageLog,
    UserStatistics,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ChatRepository(BaseRepository[MessageTokenSummary]):
    """
    Repository for chat token tracking operations.

    Provides methods for managing token summaries, usage logs, and user statistics.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize chat repository.

        Args:
            db: SQLAlchemy async session
        """
        super().__init__(db, MessageTokenSummary)

    async def get_token_summary_by_run_id(
        self,
        run_id: str,
    ) -> MessageTokenSummary | None:
        """
        Get token summary by run_id.

        Used for UPSERT check when persisting token data.

        Args:
            run_id: Run ID string

        Returns:
            MessageTokenSummary or None if not found

        Example:
            >>> summary = await repo.get_token_summary_by_run_id("run_123")
            >>> if summary:
            ...     print(f"Found summary with {summary.total_prompt_tokens} tokens")
        """
        try:
            stmt = select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)

            result = await self.db.execute(stmt)
            summary = result.scalar_one_or_none()

            if summary:
                logger.debug(
                    "token_summary_found",
                    run_id=run_id,
                    prompt_tokens=summary.total_prompt_tokens,
                )

            return summary

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_token_summary_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def bulk_create_token_logs(
        self,
        run_id: str,
        user_id: UUID,
        logs: list[dict],
    ) -> list[TokenUsageLog]:
        """
        Bulk create token usage logs.

        Efficiently creates multiple token logs in a single batch operation.

        Args:
            run_id: Run ID for all logs
            user_id: User UUID
            logs: List of log dictionaries with keys:
                - node_name: str
                - model_name: str (use FIELD_MODEL_NAME constant)
                - prompt_tokens: int
                - completion_tokens: int
                - cached_tokens: int
                - cost_usd: Decimal
                - cost_eur: Decimal
                - usd_to_eur_rate: Decimal

        Returns:
            List of created TokenUsageLog objects

        Example:
            >>> logs = [
            ...     {FIELD_NODE_NAME: "router", "model_name": "gpt-4.1-mini", ...},
            ...     {FIELD_NODE_NAME: "agent", "model_name": "gpt-4.1-mini", ...},
            ... ]
            >>> created_logs = await repo.bulk_create_token_logs("run_123", user_id, logs)
        """
        try:
            log_entries = []
            for log_data in logs:
                log_entry = TokenUsageLog(
                    user_id=user_id,
                    run_id=run_id,
                    node_name=log_data[FIELD_NODE_NAME],
                    model_name=log_data[FIELD_MODEL_NAME],
                    prompt_tokens=log_data["prompt_tokens"],
                    completion_tokens=log_data["completion_tokens"],
                    cached_tokens=log_data["cached_tokens"],
                    cost_usd=Decimal(str(log_data["cost_usd"])),
                    cost_eur=Decimal(str(log_data[FIELD_COST_EUR])),
                    usd_to_eur_rate=log_data.get("usd_to_eur_rate"),
                )
                log_entries.append(log_entry)

            self.db.add_all(log_entries)
            await self.db.flush()

            logger.info(
                "token_logs_bulk_created",
                run_id=run_id,
                count=len(log_entries),
            )

            return log_entries

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "bulk_create_token_logs_failed",
                run_id=run_id,
                error_type=type(e).__name__,
                count=len(logs),
                error=str(e),
            )
            raise

    async def create_or_update_token_summary(
        self,
        run_id: str,
        user_id: UUID,
        session_id: str | None,
        conversation_id: UUID | None,
        summary_data: dict,
    ) -> MessageTokenSummary:
        """
        Create or update token summary (UPSERT) with atomic UPDATE to prevent race conditions.

        This method uses an atomic UPDATE statement followed by INSERT if no rows were updated.
        This prevents race conditions where two concurrent commits could lose token data.

        Args:
            run_id: Run ID
            user_id: User UUID
            session_id: Session ID (optional)
            conversation_id: UUID (optional)
            summary_data: Dictionary with:
                - tokens_in: int (prompt tokens)
                - tokens_out: int (completion tokens)
                - tokens_cache: int (cached tokens)
                - cost_eur: Decimal

        Returns:
            Created or updated MessageTokenSummary

        Example:
            >>> summary = await repo.create_or_update_token_summary(
            ...     run_id="run_123",
            ...     user_id=user_id,
            ...     session_id="session_123",
            ...     conversation_id=conv_id,
            ...     summary_data={FIELD_TOKENS_IN: 100, FIELD_TOKENS_OUT: 50, ...}
            ... )
        """
        from sqlalchemy import update

        try:
            # Step 1: Try atomic UPDATE first (if record exists)
            # This prevents race conditions by incrementing values directly in SQL
            stmt = (
                update(MessageTokenSummary)
                .where(MessageTokenSummary.run_id == run_id)
                .values(
                    total_prompt_tokens=MessageTokenSummary.total_prompt_tokens
                    + summary_data[FIELD_TOKENS_IN],
                    total_completion_tokens=MessageTokenSummary.total_completion_tokens
                    + summary_data[FIELD_TOKENS_OUT],
                    total_cached_tokens=MessageTokenSummary.total_cached_tokens
                    + summary_data[FIELD_TOKENS_CACHE],
                    total_cost_eur=MessageTokenSummary.total_cost_eur
                    + Decimal(str(summary_data[FIELD_COST_EUR])),
                    # Google API tracking
                    google_api_requests=MessageTokenSummary.google_api_requests
                    + summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0),
                    google_api_cost_eur=MessageTokenSummary.google_api_cost_eur
                    + Decimal(str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))),
                )
            )

            result = await self.db.execute(stmt)
            await self.db.flush()

            if result.rowcount > 0:  # type: ignore[attr-defined]
                # Update succeeded - fetch and return updated record
                updated = await self.get_token_summary_by_run_id(run_id)

                # Safety: Should always exist after UPDATE, but handle edge case
                if updated is None:
                    raise RuntimeError(f"Token summary not found after UPDATE: {run_id}")

                logger.info(
                    "token_summary_updated_atomic",
                    run_id=run_id,
                    tokens_added=summary_data[FIELD_TOKENS_IN] + summary_data[FIELD_TOKENS_OUT],
                )

                return updated

            # Step 2: INSERT if UPDATE affected 0 rows (record didn't exist)
            message_summary = MessageTokenSummary(
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
                conversation_id=conversation_id,
                total_prompt_tokens=summary_data[FIELD_TOKENS_IN],
                total_completion_tokens=summary_data[FIELD_TOKENS_OUT],
                total_cached_tokens=summary_data[FIELD_TOKENS_CACHE],
                total_cost_eur=Decimal(str(summary_data[FIELD_COST_EUR])),
                # Google API tracking
                google_api_requests=summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0),
                google_api_cost_eur=Decimal(str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))),
            )
            self.db.add(message_summary)
            await self.db.flush()
            await self.db.refresh(message_summary)

            logger.info(
                "token_summary_created",
                run_id=run_id,
            )

            return message_summary

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_or_update_token_summary_failed",
                run_id=run_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def get_token_summaries_by_run_ids(
        self,
        run_ids: list[str],
    ) -> dict[str, MessageTokenSummary]:
        """
        Get token summaries by multiple run IDs (batch query).

        Optimized batch query to avoid N+1 problem.

        Args:
            run_ids: List of run ID strings

        Returns:
            Dictionary mapping run_id -> MessageTokenSummary

        Example:
            >>> summaries = await repo.get_token_summaries_by_run_ids(["run_1", "run_2"])
            >>> for run_id, summary in summaries.items():
            ...     print(f"{run_id}: {summary.total_prompt_tokens} tokens")
        """
        try:
            if not run_ids:
                return {}

            stmt = select(MessageTokenSummary).where(MessageTokenSummary.run_id.in_(run_ids))

            result = await self.db.execute(stmt)
            summaries = result.scalars().all()

            # Build dictionary
            summaries_dict = {s.run_id: s for s in summaries}

            logger.debug(
                "token_summaries_batch_retrieved",
                requested_count=len(run_ids),
                found_count=len(summaries_dict),
            )

            return summaries_dict

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_token_summaries_batch_failed",
                run_ids_count=len(run_ids),
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def get_token_logs_by_run_id(
        self,
        run_id: str,
    ) -> Sequence[TokenUsageLog]:
        """
        Get all token logs for a specific run_id.

        Args:
            run_id: Run ID string

        Returns:
            List of TokenUsageLog objects

        Example:
            >>> logs = await repo.get_token_logs_by_run_id("run_123")
            >>> for log in logs:
            ...     print(f"{log.node_name}: {log.prompt_tokens} tokens")
        """
        try:
            stmt = select(TokenUsageLog).where(TokenUsageLog.run_id == run_id)

            result = await self.db.execute(stmt)
            logs = result.scalars().all()

            logger.debug(
                "token_logs_retrieved",
                run_id=run_id,
                count=len(logs),
            )

            return logs

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_token_logs_failed",
                run_id=run_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def get_token_logs_by_run_ids(
        self,
        run_ids: list[str],
    ) -> dict[str, list[TokenUsageLog]]:
        """
        Get token logs for multiple run IDs (batch query).

        Args:
            run_ids: List of run ID strings

        Returns:
            Dictionary mapping run_id -> list of TokenUsageLog

        Example:
            >>> logs_dict = await repo.get_token_logs_by_run_ids(["run_1", "run_2"])
            >>> for run_id, logs in logs_dict.items():
            ...     print(f"{run_id}: {len(logs)} log entries")
        """
        try:
            if not run_ids:
                return {}

            stmt = select(TokenUsageLog).where(TokenUsageLog.run_id.in_(run_ids))

            result = await self.db.execute(stmt)
            all_logs = result.scalars().all()

            # Group by run_id
            logs_dict: dict[str, list[TokenUsageLog]] = {}
            for log in all_logs:
                if log.run_id not in logs_dict:
                    logs_dict[log.run_id] = []
                logs_dict[log.run_id].append(log)

            logger.debug(
                "token_logs_batch_retrieved",
                requested_run_ids=len(run_ids),
                found_run_ids=len(logs_dict),
                total_logs=len(all_logs),
            )

            return logs_dict

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_token_logs_batch_failed",
                run_ids_count=len(run_ids),
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def link_token_summary_to_conversation(
        self,
        run_id: str,
        conversation_id: UUID,
    ) -> MessageTokenSummary | None:
        """
        Link a token summary to a conversation by updating conversation_id.

        Used when token summary is created before conversation is established.

        Args:
            run_id: Run ID to find the summary
            conversation_id: Conversation UUID to link to

        Returns:
            Updated MessageTokenSummary or None if not found

        Example:
            >>> summary = await repo.link_token_summary_to_conversation(
            ...     "run_123",
            ...     conversation_id
            ... )
        """
        try:
            summary = await self.get_token_summary_by_run_id(run_id)

            if summary:
                summary.conversation_id = conversation_id
                await self.db.flush()
                await self.db.refresh(summary)

                logger.info(
                    "token_summary_linked_to_conversation",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                )

            return summary

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "link_token_summary_failed",
                run_id=run_id,
                error_type=type(e).__name__,
                conversation_id=str(conversation_id),
                error=str(e),
            )
            raise

    async def delete_token_summaries_for_conversation(
        self,
        conversation_id: UUID,
    ) -> int:
        """
        Delete all token summaries for a conversation (for reset operation).

        Args:
            conversation_id: Conversation UUID

        Returns:
            Number of token summaries deleted

        Example:
            >>> count = await repo.delete_token_summaries_for_conversation(conv_id)
            >>> print(f"Deleted {count} token summaries")
        """
        from sqlalchemy import delete

        try:
            stmt = delete(MessageTokenSummary).where(
                MessageTokenSummary.conversation_id == conversation_id
            )

            result = await self.db.execute(stmt)
            count: int = result.rowcount  # type: ignore[attr-defined]

            logger.info(
                "token_summaries_deleted_for_conversation",
                conversation_id=str(conversation_id),
                count=count,
            )

            return count

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "delete_token_summaries_for_conversation_failed",
                conversation_id=str(conversation_id),
                error_type=type(e).__name__,
                error=str(e),
            )
            raise


class UserStatisticsRepository(BaseRepository[UserStatistics]):
    """
    Repository for user statistics operations.

    Provides methods for managing user token usage statistics.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize user statistics repository.

        Args:
            db: SQLAlchemy async session
        """
        super().__init__(db, UserStatistics)

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> UserStatistics | None:
        """
        Get user statistics by user_id.

        Args:
            user_id: User UUID

        Returns:
            UserStatistics or None if not found

        Example:
            >>> stats = await repo.get_by_user_id(user_id)
            >>> if stats:
            ...     print(f"User has used {stats.total_prompt_tokens} tokens")
        """
        try:
            stmt = select(UserStatistics).where(UserStatistics.user_id == user_id)

            result = await self.db.execute(stmt)
            stats = result.scalar_one_or_none()

            if stats:
                logger.debug(
                    "user_statistics_found",
                    user_id=str(user_id),
                    total_messages=stats.total_messages,
                )

            return stats

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_user_statistics_failed",
                user_id=str(user_id),
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def create_or_update(
        self,
        user_id: UUID,
        current_cycle_start: datetime,
        summary_data: dict,
        is_new_cycle: bool = False,
    ) -> UserStatistics:
        """
        Create or update user statistics (UPSERT).

        Args:
            user_id: User UUID
            current_cycle_start: Current billing cycle start datetime (timezone-aware)
            summary_data: Dictionary with token counts:
                - tokens_in: int
                - tokens_out: int
                - tokens_cache: int
                - cost_eur: Decimal
                - message_count: int (use FIELD_MESSAGE_COUNT constant)
            is_new_cycle: If True, reset cycle counters

        Returns:
            Created or updated UserStatistics

        Example:
            >>> from datetime import UTC, datetime
            >>> stats = await repo.create_or_update(
            ...     user_id=user_id,
            ...     current_cycle_start=datetime.now(UTC),
            ...     summary_data={FIELD_TOKENS_IN: 100, ...},
            ...     is_new_cycle=False
            ... )
        """
        try:
            stats = await self.get_by_user_id(user_id)

            if stats:
                # Update existing
                stats.total_prompt_tokens += summary_data[FIELD_TOKENS_IN]
                stats.total_completion_tokens += summary_data[FIELD_TOKENS_OUT]
                stats.total_cached_tokens += summary_data[FIELD_TOKENS_CACHE]
                stats.total_cost_eur += Decimal(str(summary_data[FIELD_COST_EUR]))
                stats.total_messages += summary_data[FIELD_MESSAGE_COUNT]
                # Google API totals
                stats.total_google_api_requests += summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0)
                stats.total_google_api_cost_eur += Decimal(
                    str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))
                )

                if is_new_cycle:
                    # Reset cycle counters
                    stats.current_cycle_start = current_cycle_start
                    stats.cycle_prompt_tokens = summary_data[FIELD_TOKENS_IN]
                    stats.cycle_completion_tokens = summary_data[FIELD_TOKENS_OUT]
                    stats.cycle_cached_tokens = summary_data[FIELD_TOKENS_CACHE]
                    stats.cycle_cost_eur = Decimal(str(summary_data[FIELD_COST_EUR]))
                    stats.cycle_messages = summary_data[FIELD_MESSAGE_COUNT]
                    # Google API cycle (reset)
                    stats.cycle_google_api_requests = summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0)
                    stats.cycle_google_api_cost_eur = Decimal(
                        str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))
                    )
                else:
                    # Increment cycle counters
                    stats.cycle_prompt_tokens += summary_data[FIELD_TOKENS_IN]
                    stats.cycle_completion_tokens += summary_data[FIELD_TOKENS_OUT]
                    stats.cycle_cached_tokens += summary_data[FIELD_TOKENS_CACHE]
                    stats.cycle_cost_eur += Decimal(str(summary_data[FIELD_COST_EUR]))
                    stats.cycle_messages += summary_data[FIELD_MESSAGE_COUNT]
                    # Google API cycle (increment)
                    stats.cycle_google_api_requests += summary_data.get(
                        FIELD_GOOGLE_API_REQUESTS, 0
                    )
                    stats.cycle_google_api_cost_eur += Decimal(
                        str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))
                    )

                await self.db.flush()
                await self.db.refresh(stats)

                logger.info(
                    "user_statistics_updated",
                    user_id=str(user_id),
                    new_cycle=is_new_cycle,
                )

                return stats
            else:
                # Create new
                stats = UserStatistics(
                    user_id=user_id,
                    current_cycle_start=current_cycle_start,
                    total_prompt_tokens=summary_data[FIELD_TOKENS_IN],
                    total_completion_tokens=summary_data[FIELD_TOKENS_OUT],
                    total_cached_tokens=summary_data[FIELD_TOKENS_CACHE],
                    total_cost_eur=Decimal(str(summary_data[FIELD_COST_EUR])),
                    total_messages=summary_data[FIELD_MESSAGE_COUNT],
                    # Google API totals
                    total_google_api_requests=summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0),
                    total_google_api_cost_eur=Decimal(
                        str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))
                    ),
                    cycle_prompt_tokens=summary_data[FIELD_TOKENS_IN],
                    cycle_completion_tokens=summary_data[FIELD_TOKENS_OUT],
                    cycle_cached_tokens=summary_data[FIELD_TOKENS_CACHE],
                    cycle_cost_eur=Decimal(str(summary_data[FIELD_COST_EUR])),
                    cycle_messages=summary_data[FIELD_MESSAGE_COUNT],
                    # Google API cycle
                    cycle_google_api_requests=summary_data.get(FIELD_GOOGLE_API_REQUESTS, 0),
                    cycle_google_api_cost_eur=Decimal(
                        str(summary_data.get(FIELD_GOOGLE_API_COST_EUR, 0))
                    ),
                )
                self.db.add(stats)
                await self.db.flush()
                await self.db.refresh(stats)

                logger.info(
                    "user_statistics_created",
                    user_id=str(user_id),
                )

                return stats

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_or_update_user_statistics_failed",
                user_id=str(user_id),
                error_type=type(e).__name__,
                error=str(e),
            )
            raise
