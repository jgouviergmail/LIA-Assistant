"""
Conversation service - business logic for conversation management.

Handles conversation lifecycle:
- Lazy creation on first message
- Message archival for UI
- Conversation reset with audit trail
- Statistics tracking
"""

from contextlib import suppress
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_publication import (
    CurrentPrimaryPublication,
    PinnedReservationPublication,
    PinnedRunPublication,
)
from src.core.conversation_target import ConversationRef
from src.core.exceptions import raise_conversation_not_found
from src.core.field_names import (
    FIELD_TOKENS_IN,
)
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.legacy_reset import reset_primary
from src.domains.conversations.lifecycle_schemas import ConversationOperationResponse
from src.domains.conversations.message_tokens import enriched_message, shown_with_tokens_once
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.domains.conversations.publication_repository import ConversationPublicationRepository
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.sync_signal import (
    arm_after_archive,
)
from src.domains.conversations.titles import default_conversation_title
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ConversationService:
    """
    Service for managing user conversations and message archival.

    Implements lazy creation pattern: conversations created on first message only.
    Follows existing patterns from auth/users services.
    """

    async def get_or_create_conversation(
        self, user_id: UUID, db: AsyncSession, language: str | None = None
    ) -> Conversation:
        """Resolve Main through the catalogue's single creation door.

        Existing readers retain their short read-only path. First use and
        legacy reactivation serialize with annex creation under the owner lock.

        Args:
            user_id: Account owning Main.
            db: Caller-owned database session.
            language: Declared language used only for a new or reactivated title.

        Returns:
            The unique active Main, never an annex selected by recent activity.
        """
        conversation = await ConversationRepository(db).get_active_for_user(user_id)
        if conversation is not None:
            return conversation
        return await ConversationCatalogueService(db).ensure_primary_row(user_id, language)

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
        language: str | None = None,
        *,
        operation_id: UUID | None = None,
        expected_revision: int | None = None,
    ) -> ConversationOperationResponse | None:
        """Reset Main through the same atomic lifecycle as an explicit target.

        The language parameter remains for callers compiled against the legacy
        signature; a reset now preserves the discussion's existing title.
        """
        return await reset_primary(
            user_id, db, operation_id=operation_id, expected_revision=expected_revision
        )

    async def archive_message(
        self,
        conversation_id: (
            UUID | PinnedRunPublication | CurrentPrimaryPublication | PinnedReservationPublication
        ),
        role: str,
        content: str,
        metadata: dict[str, Any] | None,
        db: AsyncSession,
        *,
        stt_provider: str | None = None,
        stt_audio_duration_seconds: float | None = None,
        stt_cost_usd: float | None = None,
        stt_cost_eur: float | None = None,
        # TTS attribution (assistant messages only).
        tts_provider: str | None = None,
        tts_model: str | None = None,
        tts_characters: int | None = None,
        tts_cost_usd: float | None = None,
        tts_cost_eur: float | None = None,
        tts_usd_to_eur_rate: float | None = None,
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
            stt_provider: STT provider name when this message is the textual
                output of a remote-STT transcription (only meaningful for
                ``role='user'``). None otherwise.
            stt_audio_duration_seconds: Authoritative audio duration returned
                by the STT provider (e.g. ElevenLabs ``audio_duration_secs``).
            stt_cost_usd: STT cost in USD computed at transcription time
                (forwarded from the WebSocket TranscriptionResult).
            stt_cost_eur: Same in EUR.
            tts_provider: TTS provider that synthesised the assistant text
                (paid providers only — Edge stays NULL). Forwarded from the
                tracker via ``get_tts_usage_for_archive()``. Only meaningful
                for ``role='assistant'``.
            tts_model: TTS model used (e.g. ``tts-1``, ``eleven_turbo_v2_5``).
            tts_characters: Total characters synthesised for this assistant
                bubble across all parallel + sync TTS calls of the run.
            tts_cost_usd / tts_cost_eur: Aggregated cost for the bubble.
            tts_usd_to_eur_rate: Exchange rate used at synthesis time
                (audit trail mirror of STT).

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
        from decimal import Decimal

        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        resolved_id, metadata = await ConversationPublicationRepository(db).prepare(
            conversation_id, metadata
        )
        conversation_id = resolved_id

        # Convert STT floats to Decimal for the DB columns. Only attach the
        # cost data on user messages produced by a remote provider — assistant
        # messages and local-Sherpa user messages keep all stt_* columns NULL.
        stt_provider_db: str | None = None
        stt_duration_db: Decimal | None = None
        stt_cost_usd_db: Decimal | None = None
        stt_cost_eur_db: Decimal | None = None
        stt_rate_db: Decimal | None = None
        if (
            role == "user"
            and stt_provider
            and stt_audio_duration_seconds is not None
            and stt_audio_duration_seconds > 0
        ):
            stt_provider_db = stt_provider
            stt_duration_db = Decimal(str(stt_audio_duration_seconds))
            if stt_cost_usd is not None:
                stt_cost_usd_db = Decimal(str(stt_cost_usd))
            if stt_cost_eur is not None:
                stt_cost_eur_db = Decimal(str(stt_cost_eur))
            stt_rate_db = Decimal(str(get_cached_usd_eur_rate()))

        # Mirror logic for TTS — only attach on assistant rows produced by a
        # paid provider (Edge stays NULL: free, no audit value to expose).
        tts_provider_db: str | None = None
        tts_model_db: str | None = None
        tts_characters_db: int | None = None
        tts_cost_usd_db: Decimal | None = None
        tts_cost_eur_db: Decimal | None = None
        tts_rate_db: Decimal | None = None
        if (
            role == "assistant"
            and tts_provider
            and tts_characters is not None
            and tts_characters > 0
        ):
            tts_provider_db = tts_provider
            tts_model_db = tts_model
            tts_characters_db = int(tts_characters)
            if tts_cost_usd is not None:
                tts_cost_usd_db = Decimal(str(tts_cost_usd))
            if tts_cost_eur is not None:
                tts_cost_eur_db = Decimal(str(tts_cost_eur))
            tts_rate_db = (
                Decimal(str(tts_usd_to_eur_rate))
                if tts_usd_to_eur_rate is not None
                else Decimal(str(get_cached_usd_eur_rate()))
            )

        repo = ConversationRepository(db)
        message = await repo.create_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata,
            stt_provider=stt_provider_db,
            stt_audio_duration_seconds=stt_duration_db,
            stt_cost_usd=stt_cost_usd_db,
            stt_cost_eur=stt_cost_eur_db,
            stt_usd_to_eur_rate=stt_rate_db,
            tts_provider=tts_provider_db,
            tts_model=tts_model_db,
            tts_characters=tts_characters_db,
            tts_cost_usd=tts_cost_usd_db,
            tts_cost_eur=tts_cost_eur_db,
            tts_usd_to_eur_rate=tts_rate_db,
        )

        # Prometheus metric: dashboard 09 "Messages by Role"
        with suppress(Exception):
            from src.infrastructure.observability.metrics_agents import (
                conversation_message_archived_total,
            )

            conversation_message_archived_total.labels(role=role).inc()

        # Every path that writes a message comes through here — the chat, a
        # Telegram turn, a voice relay, a routine, a reminder, another device —
        # so the person's open tabs are told HERE, once the caller commits
        # (ADR-320).
        await arm_after_archive(db, message)

        # Note: Caller is responsible for commit to allow batching

        return message

    async def update_message_tts(
        self,
        message_id: UUID,
        tts_data: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        """Backfill TTS attribution on an already-archived assistant message.

        Called from the agents stream after the voice synthesis flow
        finalises (PATH 1 parallel drain or PATH 2 sync fallback). The
        ``tts_data`` dict comes verbatim from
        :meth:`TrackingContext.get_tts_usage_for_archive`, so this method
        only converts numeric types to ``Decimal`` and delegates to the
        repository.

        No-op when ``tts_data`` is missing the provider field — this happens
        for free (Edge) or skipped TTS, in which case all columns stay NULL.

        Caller is responsible for the DB commit.
        """
        from decimal import Decimal

        provider = tts_data.get("tts_provider")
        characters = tts_data.get("tts_characters")
        if not provider or not characters:
            return

        def _to_decimal(value: Any) -> Decimal | None:
            if value is None:
                return None
            return value if isinstance(value, Decimal) else Decimal(str(value))

        repo = ConversationRepository(db)
        await repo.update_message_tts(
            message_id,
            tts_provider=str(provider),
            tts_model=tts_data.get("tts_model"),
            tts_characters=int(characters),
            tts_cost_usd=_to_decimal(tts_data.get("tts_cost_usd")),
            tts_cost_eur=_to_decimal(tts_data.get("tts_cost_eur")),
            tts_usd_to_eur_rate=_to_decimal(tts_data.get("tts_usd_to_eur_rate")),
        )

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
            ...     "search jean",
            ...     {"hitl_edit": True, "original_content": "search jean"}
            ... )
        """
        repo = ConversationRepository(db)
        last_user_message = await repo.get_last_user_message(conversation_id)

        if last_user_message:
            # Store original content in metadata before update.
            # Build a NEW dict: mutating and reassigning the same object makes
            # SQLAlchemy change detection skip the JSONB UPDATE silently.
            original_content = last_user_message.content
            updated_metadata = dict(last_user_message.message_metadata or {})

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
                original_content_length=len(original_content),
                new_content_length=len(new_content),
            )

            return last_user_message
        else:
            logger.warning(
                "no_user_message_to_update",
                conversation_id=str(conversation_id),
            )
            return None

    async def patch_message_metadata(
        self,
        message_id: UUID,
        extra: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        """Merge extra fields into an existing message's metadata.

        Args:
            message_id: Primary key of the ConversationMessage.
            extra: Key-value pairs to merge (shallow) into existing metadata.
            db: Database session (caller manages commit).
        """
        repo = ConversationRepository(db)
        await repo.merge_message_metadata(message_id, extra)

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
        await ConversationPublicationRepository(db).resolve(conversation_id)
        repo = ConversationRepository(db)
        if await repo.increment_stats(conversation_id, messages=message_increment, tokens=tokens):
            logger.debug(
                "conversation_stats_incremented",
                conversation_id=str(conversation_id),
                message_increment=message_increment,
                token_increment=tokens,
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
    ) -> list[ConversationMessage]:
        """
        Get conversation message history for UI display.

        Messages are returned in descending order (newest first) for pagination.
        By default, shows ALL messages including HITL APPROVE/REJECT responses
        for complete conversation history and accurate token/message counting.

        Every message is returned, HITL interactions included: hiding the
        approve/reject turns used to be an option, but the predicate behind it
        was hardcoded to "filter nothing" and no caller ever asked for it, so
        the option, its two filter passes and the docstring describing their
        rules were removed rather than left describing behaviour the code did
        not have.

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session

        Returns:
            List of ConversationMessage (newest first)

        Example:
            >>> messages = await service.get_messages(user_id, limit=50, db=db)
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

        logger.debug(
            "messages_loaded",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=len(messages),
            limit=limit,
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

    async def get_messages_with_tokens_v2(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        before_created_at: datetime | None = None,
        *,
        target: ConversationRef | None = None,
        before_message_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """
        The active conversation's messages with their token summaries, in one query.

        One LEFT JOIN reads the messages and their runs' token summaries together
        (the loader it replaced read the summaries in a second query). Words are
        searched elsewhere, across every discussion (``discussion_search``).

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            before_created_at: Keyset pagination cursor (scroll-up). When set,
                only returns messages strictly older than this timestamp.
            target: The resolved discussion; Main when omitted.
            before_message_id: The primary key completing a composite cursor.

        Returns:
            List of dicts with message fields + tokens_in/out/cache/cost_eur, newest
            first; an answer with no visible text is left out, and a run's tokens
            show on its newest answer only.
        """
        # An explicit resolved target never falls back to Main.
        if target is not None and target.owner_id != user_id:
            raise_conversation_not_found(target.id)
        conversation = target or await self.get_active_conversation(user_id, db)

        if not conversation:
            return []

        # Use optimized repository method (single LEFT JOIN query)
        # Returns messages with token summary including cost_eur (historical cost)
        repo = ConversationRepository(db)
        results = await repo.get_messages_with_token_summaries(
            conversation_id=conversation.id,
            limit=limit,
            before_created_at=before_created_at,
            before_message_id=before_message_id,
        )

        enriched_messages = shown_with_tokens_once(
            [enriched_message(message, token_dict) for message, token_dict in results]
        )

        logger.debug(
            "messages_with_tokens_loaded_v2_optimized",
            user_id=str(user_id),
            conversation_id=str(conversation.id),
            count=len(enriched_messages),
            with_tokens=len([m for m in enriched_messages if m.get(FIELD_TOKENS_IN) is not None]),
            optimization="left_join_repository",
        )

        return enriched_messages

    async def get_messages_with_tokens_auto(
        self,
        user_id: UUID,
        limit: int,
        db: AsyncSession,
        before_created_at: datetime | None = None,
        *,
        target: ConversationRef | None = None,
        before_message_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """
        The history page's loader: ``get_messages_with_tokens_v2``, timed.

        The flag that once chose between two implementations is gone; the
        duration histogram keeps its ``version`` label (``v2``), unchanged.

        Args:
            user_id: User UUID
            limit: Maximum number of messages to return
            db: Database session
            before_created_at: Keyset pagination cursor (scroll-up). When set,
                only returns messages strictly older than this timestamp.
            target: The resolved discussion; Main when omitted.
            before_message_id: The primary key completing a composite cursor.

        Returns:
            List of dicts with message fields + tokens_in/out/cache/cost_eur
        """
        from src.infrastructure.observability.metrics_agents import (
            conversation_messages_query_duration_seconds,
        )

        # Always use optimized v2 implementation (N+1 query fix)
        with conversation_messages_query_duration_seconds.labels(version="v2").time():
            return await self.get_messages_with_tokens_v2(
                user_id,
                limit,
                db,
                before_created_at=before_created_at,
                target=target,
                before_message_id=before_message_id,
            )

    def _generate_title(self, language: str | None = None) -> str:
        """
        Generate the default conversation title, localized.

        The raw locale is resolved here (``zh`` → ``zh-CN``, ``fr-FR`` →
        ``fr``, absent → the declared language) before ``APIMessages`` reads its
        table.

        The date is taken from an aware UTC datetime, per the systemic rule
        forbidding ``date.today()``.

        Args:
            language: Raw or canonical language code. ``None`` writes the
                title in the declared language (ADR-323).

        Returns:
            Localized title, e.g. ``"Conversation du 26/07/2026"``.
        """
        return default_conversation_title(language)
