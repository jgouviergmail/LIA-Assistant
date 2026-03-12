"""
ConversationOrchestrator: Manage conversation lifecycle and persistence.

Responsibilities:
- Setup conversation (get or create)
- Setup tracking context for tokens/messages
- Fetch user OAuth scopes
- Persist messages to database
- Finalize conversation with token summary

Design Note:
    This service is intentionally generic and does NOT depend on agent-specific
    types (like GraphState) to maintain loose coupling. It uses duck typing
    (dict[str, Any]) for state objects to avoid import-time dependencies.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.chat.service import TrackingContext
from src.domains.connectors.models import Connector, ConnectorStatus
from src.domains.conversations.service import ConversationService

logger = get_logger(__name__)


class ConversationContext:
    """
    Context for conversation execution.

    Contains all information needed for graph execution:
    - conversation_id: UUID for thread_id
    - tracking_context: Token/message tracking
    - oauth_scopes: User's OAuth permissions
    - previous_tokens_summary: Token summary from DB BEFORE this request (for HITL incremental display)
    """

    def __init__(
        self,
        conversation_id: uuid.UUID,
        tracking_context: "TrackingContext",
        oauth_scopes: list[str],
        previous_tokens_summary: TokenSummaryDTO | None = None,
    ):
        self.conversation_id = conversation_id
        self.tracking_context = tracking_context
        self.oauth_scopes = oauth_scopes
        self.previous_tokens_summary = previous_tokens_summary or TokenSummaryDTO.zero()


class ConversationSummary:
    """Summary of conversation after finalization."""

    def __init__(
        self,
        conversation_id: uuid.UUID | None,
        message_count: int,
        token_summary: TokenSummaryDTO,
    ):
        self.conversation_id = conversation_id
        self.message_count = message_count
        self.token_summary = token_summary


class ConversationOrchestrator:
    """
    Service for managing conversation lifecycle and persistence.

    Responsibilities:
    - Get or create conversation
    - Setup tracking context
    - Fetch user OAuth scopes
    - Persist messages
    - Finalize with token summary
    """

    async def setup_conversation(
        self,
        user_id: uuid.UUID,
        session_id: str,
        run_id: str,
        db: AsyncSession,
    ) -> ConversationContext:
        """
        Setup conversation: get/create, setup tracking, fetch OAuth scopes.

        Args:
            user_id: User UUID
            session_id: Session identifier
            run_id: Unique run identifier
            db: Database session

        Returns:
            ConversationContext with conversation_id, tracking_context, oauth_scopes

        Example:
            >>> context = await orchestrator.setup_conversation(user_id, session_id, run_id, db)
            >>> print(context.conversation_id)
            >>> print(len(context.oauth_scopes))
        """
        # Get or create conversation
        conv_service = ConversationService()
        conversation = await conv_service.get_or_create_conversation(user_id, db)
        conversation_id = conversation.id

        logger.info(
            "conversation_setup_started",
            run_id=run_id,
            conversation_id=str(conversation_id),
            user_id=str(user_id),
        )

        # Fetch OAuth scopes from user's active connectors
        oauth_scopes = await self._get_user_oauth_scopes(user_id, db)

        # === HITL Token Fix: Capture PREVIOUS tokens BEFORE tracking starts ===
        # For HITL flows (same run_id across multiple requests), we need to know
        # how many tokens were already consumed to calculate incremental display.
        previous_tokens_summary = await self._get_previous_tokens_from_db(run_id, db)

        # Create tracking context
        tracking_context = TrackingContext(run_id, user_id, session_id, conversation_id)

        logger.info(
            "conversation_setup_complete",
            run_id=run_id,
            conversation_id=str(conversation_id),
            oauth_scopes_count=len(oauth_scopes),
            previous_tokens_in=previous_tokens_summary.tokens_in,
            previous_tokens_out=previous_tokens_summary.tokens_out,
        )

        return ConversationContext(
            conversation_id=conversation_id,
            tracking_context=tracking_context,
            oauth_scopes=oauth_scopes,
            previous_tokens_summary=previous_tokens_summary,
        )

    async def persist_messages(
        self,
        conversation_id: uuid.UUID,
        messages: list[Any],  # list[Message]
        tracking_context: "TrackingContext",
    ) -> None:
        """
        Persist messages to database.

        Args:
            conversation_id: Conversation UUID
            messages: List of messages from graph state
            tracking_context: Token tracking context

        Example:
            >>> await orchestrator.persist_messages(conv_id, state["messages"], tracker)
        """
        # TODO: Implement message persistence
        # This will be extracted from existing chat service logic
        logger.info(
            "messages_persisted",
            conversation_id=str(conversation_id),
            messages_count=len(messages),
        )

    async def finalize_conversation(
        self,
        tracking_context: "TrackingContext",
        final_state: dict[str, Any],
    ) -> ConversationSummary:
        """
        Finalize conversation: compute token summary.

        Args:
            tracking_context: Token tracking context
            final_state: Final graph state (dict with "messages" key)

        Returns:
            ConversationSummary with token totals

        Example:
            >>> summary = await orchestrator.finalize_conversation(tracker, state)
            >>> print(f"Total: {summary.token_summary.tokens_in + summary.token_summary.tokens_out}")
        """
        # Compute token summary from tracking context using factory method
        token_summary = TokenSummaryDTO.from_tracker(tracking_context)

        messages = final_state.get("messages", [])

        logger.info(
            "conversation_finalized",
            conversation_id=str(tracking_context.conversation_id),
            message_count=len(messages),
            tokens_in=token_summary.tokens_in,
            tokens_out=token_summary.tokens_out,
            cost_eur=token_summary.cost_eur,
        )

        return ConversationSummary(
            conversation_id=tracking_context.conversation_id,
            message_count=len(messages),
            token_summary=token_summary,
        )

    # ============================================================================
    # PRIVATE METHODS
    # ============================================================================

    async def _get_user_oauth_scopes(self, user_id: uuid.UUID, db: AsyncSession) -> list[str]:
        """
        Fetch OAuth scopes from user's active connectors.

        Retrieves all scopes from connectors where:
        - user_id matches
        - is_active = True
        - Flattens and deduplicates scopes

        Args:
            user_id: User UUID
            db: Database session

        Returns:
            List of OAuth scopes
        """
        # Query active connectors
        stmt = select(Connector).where(
            Connector.user_id == user_id, Connector.status == ConnectorStatus.ACTIVE
        )
        result = await db.execute(stmt)
        connectors = result.scalars().all()

        # Extract and deduplicate scopes
        scopes: set[str] = set()
        connector_details = []
        for connector in connectors:
            connector_details.append(
                {
                    "type": connector.connector_type.value,
                    "status": connector.status.value,
                    "scopes_count": len(connector.scopes) if connector.scopes else 0,
                }
            )
            if connector.scopes:
                scopes.update(connector.scopes)

        scopes_list = list(scopes)

        # INFO level log to diagnose scope loading issues
        # Generalized scope detection for all connector types
        scope_summary = {
            "gmail": any("gmail" in s for s in scopes_list),
            "events": any("events" in s for s in scopes_list),
            "drive": any("drive" in s for s in scopes_list),
            "contacts": any("contacts" in s or "people" in s for s in scopes_list),
            "tasks": any("tasks" in s for s in scopes_list),
        }
        logger.info(
            "oauth_scopes_fetched",
            user_id=str(user_id),
            connectors_count=len(connectors),
            connector_details=connector_details,
            scopes_count=len(scopes_list),
            scope_summary=scope_summary,
        )

        return scopes_list

    async def _get_previous_tokens_from_db(self, run_id: str, db: AsyncSession) -> TokenSummaryDTO:
        """
        Query DB for existing token summary for this run_id.

        For HITL flows, the same run_id is reused across multiple requests.
        This method captures the PREVIOUS total before the current request starts,
        allowing us to calculate incremental tokens for display.

        Args:
            run_id: LangGraph run identifier
            db: AsyncSession - reuse existing DB session from caller

        Returns:
            TokenSummaryDTO with previous totals, or zero if no existing record
        """
        from src.domains.chat.repository import ChatRepository

        try:
            chat_repo = ChatRepository(db)
            summary = await chat_repo.get_token_summary_by_run_id(run_id)

            if summary:
                previous = TokenSummaryDTO(
                    tokens_in=summary.total_prompt_tokens,
                    tokens_out=summary.total_completion_tokens,
                    tokens_cache=summary.total_cached_tokens,
                    cost_eur=float(summary.total_cost_eur),
                    message_count=0,  # MessageTokenSummary doesn't have message_count
                )
                logger.info(
                    "previous_tokens_retrieved_from_db",
                    run_id=run_id,
                    tokens_in=previous.tokens_in,
                    tokens_out=previous.tokens_out,
                )
                return previous
            else:
                logger.debug(
                    "no_previous_tokens_in_db",
                    run_id=run_id,
                )
                return TokenSummaryDTO.zero()

        except Exception as e:
            logger.warning(
                "previous_tokens_query_failed",
                run_id=run_id,
                error=str(e),
            )
            return TokenSummaryDTO.zero()
