"""
Notification Dispatcher for Proactive Tasks.

Dispatches proactive notifications via all available channels:
- FCM Push (mobile + web)
- Redis Pub/Sub (SSE real-time)
- Conversation archive (historique)

Follows the established pattern from reminder_notification.py but
provides a generic, reusable interface for all proactive tasks.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_notification_errors_total,
    channel_notifications_sent_total,
)

logger = get_logger(__name__)


@dataclass
class NotificationResult:
    """
    Result of notification dispatch.

    Attributes:
        success: Whether notification was sent successfully
        fcm_success: Number of successful FCM deliveries
        fcm_failed: Number of failed FCM deliveries
        sse_sent: Whether SSE was published
        archived: Whether message was archived
        channel_sent: Number of channel messages sent (Telegram, etc.)
        error: Error message if dispatch failed
        conversation_id: Conversation ID where message was archived
        message_id: Message ID in conversation archive
    """

    success: bool
    fcm_success: int = 0
    fcm_failed: int = 0
    sse_sent: bool = False
    archived: bool = False
    channel_sent: int = 0
    error: str | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None

    @classmethod
    def failure(cls, error: str) -> "NotificationResult":
        """Create a failure result."""
        return cls(success=False, error=error)


async def send_notification_to_channels(
    user_id: UUID,
    title: str,
    body: str,
    task_type: str,
    target_id: str,
    db: AsyncSession,
) -> int:
    """
    Send notification to all active external channels (Telegram, etc.) for a user.

    This is the single entry point for channel dispatch, used by both
    NotificationDispatcher (proactive tasks) and reminder_notification.

    Args:
        user_id: User UUID
        title: Notification title
        body: Full notification body (channel senders handle splitting)
        task_type: Task type for data payload (e.g., "interest", "reminder")
        target_id: Target ID for tracking
        db: Database session

    Returns:
        Number of successfully sent channel messages
    """
    from src.domains.channels.repository import UserChannelBindingRepository

    repo = UserChannelBindingRepository(db)
    bindings = await repo.get_active_for_user(user_id)

    if not bindings:
        return 0

    sent = 0
    for binding in bindings:
        try:
            success = await _send_to_channel(
                channel_type=binding.channel_type,
                channel_user_id=binding.channel_user_id,
                title=title,
                body=body,
                task_type=task_type,
                target_id=target_id,
            )
            if success:
                sent += 1
                channel_notifications_sent_total.labels(
                    channel_type=binding.channel_type,
                    task_type=task_type,
                ).inc()
        except Exception as e:
            channel_notification_errors_total.labels(
                channel_type=binding.channel_type,
                error_type=type(e).__name__,
            ).inc()
            logger.warning(
                "channel_send_failed",
                channel_type=binding.channel_type,
                channel_user_id=binding.channel_user_id[:8],
                user_id=str(user_id),
                error=str(e),
            )

    return sent


async def _send_to_channel(
    channel_type: str,
    channel_user_id: str,
    title: str,
    body: str,
    task_type: str,
    target_id: str,
) -> bool:
    """
    Send notification to a specific channel binding.

    Routes to the correct sender based on channel_type.
    New channel types (Discord, WhatsApp, etc.) should be added here.
    """
    from src.core.constants import CHANNEL_TYPE_TELEGRAM

    if channel_type == CHANNEL_TYPE_TELEGRAM:
        from src.infrastructure.channels.telegram.sender import TelegramSender

        sender = TelegramSender()
        return await sender.send_notification(
            channel_user_id=channel_user_id,
            title=title,
            body=body,
            data={
                "type": task_type,
                "target_id": target_id,
            },
        )

    logger.warning(
        "channel_type_unsupported",
        channel_type=channel_type,
    )
    return False


class NotificationDispatcher:
    """
    Dispatches proactive notifications via all available channels.

    Channels:
    1. FCM Push (mobile + web) - if tokens registered
    2. Redis Pub/Sub (SSE real-time) - for connected clients
    3. Conversation archive (historique) - for persistence and UI
    4. External channels (Telegram, etc.) - if bindings exist

    Usage:
        >>> dispatcher = NotificationDispatcher()
        >>> result = await dispatcher.dispatch(
        ...     user=user,
        ...     content="Here's an interesting fact about...",
        ...     task_type="interest",
        ...     target_id=str(interest.id),
        ...     metadata={"source": "wikipedia", "article_url": "..."},
        ...     db=db,
        ... )
    """

    def __init__(
        self,
        fcm_enabled: bool = True,
        sse_enabled: bool = True,
        archive_enabled: bool = True,
        channel_enabled: bool | None = None,
    ):
        """
        Initialize notification dispatcher.

        Args:
            fcm_enabled: Whether to send FCM push notifications
            sse_enabled: Whether to publish to Redis for SSE
            archive_enabled: Whether to archive in conversation
            channel_enabled: Whether to send via external channels (Telegram, etc.)
                If None, auto-detects from settings.channels_enabled.
        """
        self.fcm_enabled = fcm_enabled
        self.sse_enabled = sse_enabled
        self.archive_enabled = archive_enabled
        if channel_enabled is None:
            self.channel_enabled = getattr(settings, "channels_enabled", False)
        else:
            self.channel_enabled = channel_enabled

    async def dispatch(
        self,
        user: Any,
        content: str,
        task_type: str,
        target_id: str,
        metadata: dict[str, Any],
        db: AsyncSession,
        title: str | None = None,
        run_id: str | None = None,
        commit_before_notification: bool = True,
        push_enabled: bool = True,
    ) -> NotificationResult:
        """
        Dispatch notification via all enabled channels.

        Args:
            user: User model instance
            content: Notification content
            task_type: Task type identifier (e.g., "interest", "birthday")
            target_id: Target identifier for tracking
            metadata: Additional metadata for the notification
            db: Database session
            title: Optional notification title (defaults to localized title)
            run_id: Optional run_id for token tracking linkage
            commit_before_notification: If True (default), commits the archived message
                before sending FCM/SSE. Prevents race condition where user clicks
                FCM notification before message is visible in database.
            push_enabled: Whether to send push notifications (FCM, Telegram).
                When False, only archive + SSE are used. Defaults to True.

        Returns:
            NotificationResult with dispatch status for each channel
        """
        result = NotificationResult(success=True)

        # Generate title if not provided
        if title is None:
            title = self._get_localized_title(
                task_type, getattr(user, "language", settings.default_language)
            )

        # Build complete metadata
        full_metadata = {
            "type": f"proactive_{task_type}",
            "target_id": target_id,
            "feedback_enabled": settings.proactive_feedback_enabled,
            "sent_at": datetime.now(UTC).isoformat(),
            **metadata,
        }
        if run_id:
            full_metadata["run_id"] = run_id

        # CRITICAL: Order of operations matters for race condition prevention!
        # Archive FIRST (persists to DB), then external notifications (FCM/SSE)
        # This ensures the message exists in DB before user can click FCM notification

        # 1. Archive in conversation FIRST
        if self.archive_enabled:
            try:
                archive_result = await self._archive_message(
                    user=user,
                    content=content,
                    metadata=full_metadata,
                    db=db,
                )
                result.archived = archive_result.get("archived", False)
                result.conversation_id = archive_result.get("conversation_id")
                result.message_id = archive_result.get("message_id")

                # CRITICAL: Commit BEFORE sending external notifications
                # This ensures the message is visible in the database before
                # the user receives and clicks on the FCM notification.
                # Prevents race condition: FCM received → user clicks → loads history
                # → message not yet committed → not displayed!
                if commit_before_notification:
                    await db.commit()

            except Exception as e:
                logger.warning(
                    "proactive_archive_failed",
                    task_type=task_type,
                    user_id=str(user.id),
                    error=str(e),
                )

        # 2. Send FCM Push (external notification) — skip if push_enabled=False
        if self.fcm_enabled and push_enabled:
            try:
                fcm_result = await self._send_fcm(
                    user=user,
                    title=title,
                    body=self._truncate_for_notification(content),
                    task_type=task_type,
                    target_id=target_id,
                    db=db,
                )
                result.fcm_success = fcm_result.get("success", 0)
                result.fcm_failed = fcm_result.get("failed", 0)
            except Exception as e:
                logger.warning(
                    "proactive_fcm_failed",
                    task_type=task_type,
                    user_id=str(user.id),
                    error=str(e),
                )

        # 3. Publish to Redis for SSE (real-time in-app)
        if self.sse_enabled:
            try:
                await self._publish_sse(
                    user_id=user.id,
                    content=content,
                    title=title,
                    task_type=task_type,
                    target_id=target_id,
                    metadata=full_metadata,
                )
                result.sse_sent = True
            except Exception as e:
                logger.warning(
                    "proactive_sse_failed",
                    task_type=task_type,
                    user_id=str(user.id),
                    error=str(e),
                )

        # 4. Send via external channels (Telegram, etc.) — skip if push_enabled=False
        if self.channel_enabled and push_enabled:
            try:
                channel_result = await self._send_channels(
                    user_id=user.id,
                    title=title,
                    body=content,
                    task_type=f"proactive_{task_type}",
                    target_id=target_id,
                    db=db,
                )
                result.channel_sent = channel_result
            except Exception as e:
                logger.warning(
                    "proactive_channels_failed",
                    task_type=task_type,
                    user_id=str(user.id),
                    error=str(e),
                )

        # Determine overall success
        # Consider successful if at least one channel worked
        result.success = (
            result.sse_sent or result.archived or result.fcm_success > 0 or result.channel_sent > 0
        )

        logger.info(
            "proactive_notification_dispatched",
            task_type=task_type,
            user_id=str(user.id),
            target_id=target_id[:12] if target_id else None,
            success=result.success,
            fcm_success=result.fcm_success,
            fcm_failed=result.fcm_failed,
            sse_sent=result.sse_sent,
            archived=result.archived,
            channel_sent=result.channel_sent,
        )

        return result

    async def _send_fcm(
        self,
        user: Any,
        title: str,
        body: str,
        task_type: str,
        target_id: str,
        db: AsyncSession,
    ) -> dict[str, int]:
        """
        Send FCM push notification.

        Args:
            user: User model instance
            title: Notification title
            body: Notification body (truncated)
            task_type: Task type for data payload
            target_id: Target ID for tracking
            db: Database session

        Returns:
            Dict with success/failed counts
        """
        from src.domains.notifications.service import FCMNotificationService

        fcm_service = FCMNotificationService(db)

        fcm_result = await fcm_service.send_to_user(
            user_id=user.id,
            title=title,
            body=body,
            data={
                "type": f"proactive_{task_type}",
                "target_id": target_id,
                "feedback_enabled": "true",  # FCM data values must be strings
                "click_action": "OPEN_CHAT",
            },
        )

        return {
            "success": fcm_result.success_count,
            "failed": fcm_result.failure_count,
        }

    async def _publish_sse(
        self,
        user_id: UUID,
        content: str,
        title: str,
        task_type: str,
        target_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Publish notification to Redis for SSE real-time delivery.

        Args:
            user_id: User UUID
            content: Full notification content
            title: Notification title
            task_type: Task type identifier
            target_id: Target identifier
            metadata: Full metadata dict
        """
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            logger.warning(
                "proactive_sse_redis_unavailable",
                user_id=str(user_id),
                task_type=task_type,
            )
            return

        channel = f"user_notifications:{user_id}"
        payload = {
            "type": f"proactive_{task_type}",
            "content": content,
            "title": title,
            "target_id": target_id,
            "metadata": metadata,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await redis.publish(
            channel,
            json.dumps(payload, ensure_ascii=False),
        )

        logger.debug(
            "proactive_sse_published",
            user_id=str(user_id),
            task_type=task_type,
            channel=channel,
        )

    async def _send_channels(
        self,
        user_id: UUID,
        title: str,
        body: str,
        task_type: str,
        target_id: str,
        db: AsyncSession,
    ) -> int:
        """Delegate to module-level send_notification_to_channels()."""
        return await send_notification_to_channels(
            user_id=user_id,
            title=title,
            body=body,
            task_type=task_type,
            target_id=target_id,
            db=db,
        )

    async def _archive_message(
        self,
        user: Any,
        content: str,
        metadata: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Archive notification message in conversation.

        Args:
            user: User model instance
            content: Message content
            metadata: Message metadata
            db: Database session

        Returns:
            Dict with archived status, conversation_id, message_id
        """
        from src.domains.conversations.service import ConversationService

        conv_service = ConversationService()

        # Get or create conversation
        conversation = await conv_service.get_or_create_conversation(user.id, db)

        # Archive the proactive message
        message = await conv_service.archive_message(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            metadata=metadata,
            db=db,
        )

        # Commit is handled by caller (ProactiveTaskRunner)

        logger.debug(
            "proactive_message_archived",
            user_id=str(user.id),
            conversation_id=str(conversation.id),
            message_id=str(message.id),
        )

        return {
            "archived": True,
            "conversation_id": conversation.id,
            "message_id": message.id,
        }

    def _get_localized_title(self, task_type: str, language: str) -> str:
        """
        Get localized notification title for task type.

        Args:
            task_type: Task type identifier
            language: User language code

        Returns:
            Localized title string
        """
        # Define titles per task type and language
        titles: dict[str, dict[str, str]] = {
            "interest": {
                "fr": "Pour toi",
                "en": "For you",
                "es": "Para ti",
                "de": "Für dich",
                "it": "Per te",
                "zh": "为你推荐",
            },
            "birthday": {
                "fr": "Anniversaire",
                "en": "Birthday",
                "es": "Cumpleaños",
                "de": "Geburtstag",
                "it": "Compleanno",
                "zh": "生日",
            },
            "event": {
                "fr": "Événement",
                "en": "Event",
                "es": "Evento",
                "de": "Ereignis",
                "it": "Evento",
                "zh": "活动",
            },
            "summary": {
                "fr": "Résumé",
                "en": "Summary",
                "es": "Resumen",
                "de": "Zusammenfassung",
                "it": "Riepilogo",
                "zh": "摘要",
            },
            "heartbeat": {
                "fr": "Notification proactive",
                "en": "Proactive notification",
                "es": "Notificación proactiva",
                "de": "Proaktive Benachrichtigung",
                "it": "Notifica proattiva",
                "zh": "主动通知",
            },
        }

        # Get task-specific titles or default
        task_titles = titles.get(task_type, {})
        return task_titles.get(language, task_titles.get("en", "Notification"))

    def _truncate_for_notification(self, text: str, max_length: int | None = None) -> str:
        """
        Truncate text for notification body (push notifications have limits).

        Args:
            text: Full text content
            max_length: Maximum length (uses settings.proactive_notification_max_length if not provided)

        Returns:
            Truncated text with ellipsis if needed
        """
        if max_length is None:
            max_length = settings.proactive_notification_max_length
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
