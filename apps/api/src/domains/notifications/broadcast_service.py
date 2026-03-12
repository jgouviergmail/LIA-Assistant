"""
Service for admin broadcast messages.

Handles sending broadcast messages to all active users via:
- SSE (Server-Sent Events) for real-time delivery
- FCM (Firebase Cloud Messaging) for push notifications

Messages are automatically translated to each user's preferred language.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import _
from src.core.i18n_types import LANGUAGE_NAMES, Language
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.notifications.models import AdminBroadcast
from src.domains.notifications.repository import BroadcastRepository
from src.domains.notifications.schemas import BroadcastInfo
from src.domains.notifications.service import FCMNotificationService
from src.domains.users.repository import UserRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm import get_llm

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = structlog.get_logger(__name__)

# Default source language for admin broadcasts
DEFAULT_SOURCE_LANGUAGE: Language = "fr"


@dataclass
class BroadcastResult:
    """Result of sending a broadcast message."""

    success: bool
    broadcast_id: UUID
    total_users: int
    fcm_sent: int
    fcm_failed: int


class BroadcastService:
    """
    Service for admin broadcast operations.

    Handles:
    - Sending broadcasts to all active users
    - Automatic message translation to user's preferred language
    - SSE real-time delivery
    - FCM push notifications (batch)
    - Tracking read receipts
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize broadcast service.

        Args:
            db: SQLAlchemy async session
        """
        self.db = db
        self.broadcast_repo = BroadcastRepository(db)
        self.user_repo = UserRepository(db)
        self.fcm_service = FCMNotificationService(db)

    async def send_broadcast(
        self,
        message: str,
        admin_user_id: UUID,
        expires_in_days: int | None = None,
        source_language: Language = DEFAULT_SOURCE_LANGUAGE,
        user_ids: list[UUID] | None = None,
    ) -> BroadcastResult:
        """
        Send a broadcast message to users.

        Flow:
        1. Create broadcast record (Archive-First pattern)
        2. Get users grouped by language preference (all or selected)
        3. Translate message to each language
        4. Send SSE + FCM to each language group with translated message
        5. Update stats

        Args:
            message: The broadcast message content
            admin_user_id: Admin user ID who is sending
            expires_in_days: Optional expiration in days (null = never)
            source_language: Language of the original message (default: fr)
            user_ids: Optional list of user IDs to target (None = all active users)

        Returns:
            BroadcastResult with delivery stats
        """
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

        # Create broadcast (Archive-First: persist before sending)
        broadcast = await self.broadcast_repo.create_broadcast(
            message=message,
            sent_by=admin_user_id,
            expires_at=expires_at,
        )
        await self.db.commit()

        is_targeted = user_ids is not None and len(user_ids) > 0

        logger.info(
            "broadcast_created",
            broadcast_id=str(broadcast.id),
            admin_user_id=str(admin_user_id),
            expires_at=expires_at.isoformat() if expires_at else None,
            is_targeted=is_targeted,
            target_user_count=len(user_ids) if user_ids else None,
        )

        # Get users grouped by language (all or selected)
        if is_targeted and user_ids:  # Explicit check for mypy type narrowing
            users_by_language = await self.user_repo.get_selected_users_grouped_by_language(
                user_ids
            )
        else:
            users_by_language = await self.user_repo.get_active_users_grouped_by_language()
        total_users = sum(len(users) for users in users_by_language.values())

        logger.info(
            "broadcast_sending",
            broadcast_id=str(broadcast.id),
            total_users=total_users,
            languages=list(users_by_language.keys()),
        )

        # Translate message to each target language
        translations = await self._translate_to_languages(
            message=message,
            source_language=source_language,
            target_languages=[lang for lang in users_by_language if lang != source_language],
        )
        translations[source_language] = message  # Add original message

        # Send SSE + FCM to each language group
        fcm_sent, fcm_failed = await self._broadcast_to_users_by_language(
            users_by_language=users_by_language,
            broadcast_id=broadcast.id,
            translations=translations,
        )

        # Update stats
        await self.broadcast_repo.update_stats(
            broadcast_id=broadcast.id,
            total_recipients=total_users,
            fcm_sent=fcm_sent,
            fcm_failed=fcm_failed,
        )
        await self.db.commit()

        logger.info(
            "broadcast_sent",
            broadcast_id=str(broadcast.id),
            total_users=total_users,
            fcm_sent=fcm_sent,
            fcm_failed=fcm_failed,
        )

        return BroadcastResult(
            success=True,
            broadcast_id=broadcast.id,
            total_users=total_users,
            fcm_sent=fcm_sent,
            fcm_failed=fcm_failed,
        )

    async def _translate_to_languages(
        self,
        message: str,
        source_language: Language,
        target_languages: list[str],
    ) -> dict[str, str]:
        """
        Translate message to multiple target languages.

        Args:
            message: Original message
            source_language: Source language code
            target_languages: List of target language codes

        Returns:
            Dict mapping language code to translated message
        """
        translations: dict[str, str] = {}

        if not target_languages:
            return translations

        llm = get_llm("broadcast_translator")
        prompt_template = load_prompt("broadcast_translation_prompt", version="v1")

        for target_lang in target_languages:
            try:
                translated = await self._translate_message(
                    llm=llm,
                    message=message,
                    source_language=source_language,
                    target_language=target_lang,
                    prompt_template=prompt_template,
                )
                translations[target_lang] = translated

                logger.debug(
                    "broadcast_translation_success",
                    source_language=source_language,
                    target_language=target_lang,
                )

            except Exception as e:
                logger.warning(
                    "broadcast_translation_failed",
                    target_language=target_lang,
                    error=str(e),
                    fallback="original_message",
                )
                translations[target_lang] = message

        return translations

    async def _translate_message(
        self,
        llm: "BaseChatModel",
        message: str,
        source_language: Language,
        target_language: str,
        prompt_template: str,
    ) -> str:
        """
        Translate a single message using LLM.

        Args:
            llm: LLM instance
            message: Message to translate
            source_language: Source language code
            target_language: Target language code
            prompt_template: System prompt template

        Returns:
            Translated message
        """
        source_name = LANGUAGE_NAMES.get(source_language, source_language)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)

        system_prompt = prompt_template.format(
            source_language=source_name,
            target_language=target_name,
        )

        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

        invoke_config = enrich_config_with_node_metadata(None, "broadcast_translation")
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=message),
            ],
            config=invoke_config,
        )

        translated = str(response.content).strip()

        # Remove surrounding quotes if present
        if (translated.startswith('"') and translated.endswith('"')) or (
            translated.startswith("'") and translated.endswith("'")
        ):
            translated = translated[1:-1]

        return translated

    async def _broadcast_to_users_by_language(
        self,
        users_by_language: dict[str, list[UUID]],
        broadcast_id: UUID,
        translations: dict[str, str],
    ) -> tuple[int, int]:
        """
        Send broadcast to users grouped by language.

        Args:
            users_by_language: Dict mapping language to user IDs
            broadcast_id: Broadcast UUID
            translations: Dict mapping language to translated message

        Returns:
            Tuple of (fcm_sent, fcm_failed)
        """
        redis = await get_redis_cache()
        if redis is None:
            logger.error("broadcast_redis_unavailable")
            return 0, 0

        total_fcm_sent = 0
        total_fcm_failed = 0

        for language, user_ids in users_by_language.items():
            message = translations.get(language, translations.get(DEFAULT_SOURCE_LANGUAGE, ""))
            fcm_title = _("Important message", language)  # type: ignore[arg-type]

            # Collect FCM tokens for this language group
            fcm_tokens: list[str] = []

            for user_id in user_ids:
                # Publish to SSE channel with translated message
                payload = {
                    "type": "admin_broadcast",
                    "broadcast_id": str(broadcast_id),
                    "message": message,
                }
                await redis.publish(
                    f"user_notifications:{user_id}",
                    json.dumps(payload),
                )

                # Collect FCM tokens
                tokens = await self.fcm_service.get_active_tokens(user_id)
                fcm_tokens.extend(token.token for token in tokens)

            # Send FCM batch for this language group
            if fcm_tokens:
                fcm_body = message[:100] + "..." if len(message) > 100 else message
                fcm_sent, fcm_failed = await self.fcm_service.send_multicast(
                    tokens=fcm_tokens,
                    title=fcm_title,
                    body=fcm_body,
                    data={
                        "type": "admin_broadcast",
                        "broadcast_id": str(broadcast_id),
                        "message": message,
                    },
                )
                total_fcm_sent += fcm_sent
                total_fcm_failed += fcm_failed

        return total_fcm_sent, total_fcm_failed

    async def get_unread_broadcasts(
        self,
        user_id: UUID,
        user_language: Language = DEFAULT_SOURCE_LANGUAGE,
    ) -> list[BroadcastInfo]:
        """
        Get unread broadcasts for a user, translated to their language.

        Args:
            user_id: User UUID
            user_language: User's preferred language

        Returns:
            List of BroadcastInfo with translated messages
        """
        broadcasts = await self.broadcast_repo.get_unread_for_user(user_id)

        result = []
        for broadcast in broadcasts:
            info = await self._to_broadcast_info(broadcast, user_language)
            result.append(info)

        return result

    async def mark_broadcast_read(self, user_id: UUID, broadcast_id: UUID) -> bool:
        """
        Mark a broadcast as read for a user.

        Args:
            user_id: User UUID
            broadcast_id: Broadcast UUID

        Returns:
            True (idempotent operation)
        """
        result = await self.broadcast_repo.mark_as_read(user_id, broadcast_id)
        await self.db.commit()

        logger.debug(
            "broadcast_marked_read",
            user_id=str(user_id),
            broadcast_id=str(broadcast_id),
        )

        return result

    async def _to_broadcast_info(
        self,
        broadcast: AdminBroadcast,
        user_language: Language = DEFAULT_SOURCE_LANGUAGE,
    ) -> BroadcastInfo:
        """
        Convert AdminBroadcast model to BroadcastInfo schema with translation.

        Args:
            broadcast: AdminBroadcast model
            user_language: User's preferred language for translation

        Returns:
            BroadcastInfo schema with translated message
        """
        sender_name = None
        if broadcast.sender:
            sender_name = broadcast.sender.full_name or broadcast.sender.email

        # Translate message if user's language differs from source
        message = broadcast.message
        if user_language != DEFAULT_SOURCE_LANGUAGE:
            try:
                translations = await self._translate_to_languages(
                    message=message,
                    source_language=DEFAULT_SOURCE_LANGUAGE,
                    target_languages=[user_language],
                )
                message = translations.get(user_language, message)
            except Exception as e:
                logger.warning(
                    "broadcast_info_translation_failed",
                    broadcast_id=str(broadcast.id),
                    user_language=user_language,
                    error=str(e),
                )

        return BroadcastInfo(
            id=broadcast.id,
            message=message,
            sent_at=broadcast.created_at,
            sender_name=sender_name,
        )
