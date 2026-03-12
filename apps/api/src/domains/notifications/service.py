"""
Service for FCM (Firebase Cloud Messaging) notifications.

Provides high-level operations for sending push notifications
and managing FCM tokens.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.repository import FCMTokenRepository

logger = structlog.get_logger(__name__)


@dataclass
class FCMSendResult:
    """Result of sending an FCM notification."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    token: str | None = None


@dataclass
class FCMBatchResult:
    """Result of sending notifications to multiple tokens."""

    success_count: int
    failure_count: int
    results: list[FCMSendResult]


class FCMNotificationService:
    """
    Service for Firebase Cloud Messaging operations.

    Handles:
    - Token registration/management
    - Sending push notifications
    - Token validation and cleanup
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize FCM notification service.

        Args:
            db: SQLAlchemy async session
        """
        self.db = db
        self.repository = FCMTokenRepository(db)
        self._firebase_app = None

    def _get_firebase_app(self) -> Any:
        """
        Get or initialize Firebase app (lazy loading).

        Returns:
            Firebase App instance
        """
        if self._firebase_app is not None:
            return self._firebase_app

        try:
            import firebase_admin
            from firebase_admin import credentials

            from src.core.config import settings

            # Check if already initialized
            try:
                self._firebase_app = firebase_admin.get_app()
            except ValueError:
                # Not initialized, create new app
                cred = credentials.Certificate(settings.firebase_credentials_path)
                self._firebase_app = firebase_admin.initialize_app(cred)

            return self._firebase_app

        except ImportError:
            logger.warning("firebase_admin not installed, FCM disabled")
            return None
        except Exception as e:
            logger.error("firebase_init_failed", error=str(e))
            return None

    # =========================================================================
    # Token Management
    # =========================================================================

    async def register_token(
        self,
        user_id: UUID,
        token: str,
        device_type: str,
        device_name: str | None = None,
    ) -> UserFCMToken:
        """
        Register an FCM token for a user.

        Args:
            user_id: User UUID
            token: FCM token from client
            device_type: Device type (android, ios, web)
            device_name: Optional device name

        Returns:
            Created or updated UserFCMToken
        """
        fcm_token = await self.repository.register_token(
            user_id=user_id,
            token=token,
            device_type=device_type,
            device_name=device_name,
        )

        logger.info(
            "fcm_token_registered",
            user_id=str(user_id),
            device_type=device_type,
            token_id=str(fcm_token.id),
        )

        return fcm_token

    async def unregister_token(self, token: str) -> bool:
        """
        Unregister an FCM token.

        Args:
            token: FCM token to remove

        Returns:
            True if token was removed
        """
        result = await self.repository.unregister_token(token)

        if result:
            logger.info("fcm_token_unregistered", token_prefix=token[:20])

        return result

    async def get_user_tokens(self, user_id: UUID) -> list[UserFCMToken]:
        """
        Get all tokens for a user.

        Args:
            user_id: User UUID

        Returns:
            List of FCM tokens
        """
        return await self.repository.get_all_tokens_for_user(user_id)

    async def get_active_tokens(self, user_id: UUID) -> list[UserFCMToken]:
        """
        Get active tokens for a user.

        Args:
            user_id: User UUID

        Returns:
            List of active FCM tokens
        """
        return await self.repository.get_active_tokens_for_user(user_id)

    async def delete_token_by_id(
        self,
        token_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Delete a token by ID (with user ownership check).

        Args:
            token_id: Token UUID
            user_id: User UUID (must own the token)

        Returns:
            True if token was deleted
        """
        result = await self.repository.delete_token_by_id(
            token_id=token_id,
            user_id=user_id,
        )

        if result:
            logger.info(
                "fcm_token_deleted",
                token_id=str(token_id),
                user_id=str(user_id),
            )

        return result

    # =========================================================================
    # Notification Sending
    # =========================================================================

    async def send_to_user(
        self,
        user_id: UUID,
        title: str,
        body: str,
        data: dict | None = None,
        image_url: str | None = None,
    ) -> FCMBatchResult:
        """
        Send notification to all user's active devices.

        Args:
            user_id: User UUID
            title: Notification title
            body: Notification body
            data: Optional data payload
            image_url: Optional image URL

        Returns:
            FCMBatchResult with success/failure counts
        """
        tokens = await self.get_active_tokens(user_id)

        if not tokens:
            logger.warning("no_active_tokens", user_id=str(user_id))
            return FCMBatchResult(
                success_count=0,
                failure_count=0,
                results=[],
            )

        results = []
        for token in tokens:
            result = await self._send_to_token(
                token=token.token,
                title=title,
                body=body,
                data=data,
                image_url=image_url,
            )
            results.append(result)

            # Update token status
            if result.success:
                await self.repository.update_last_used(token.id)
            elif result.error and "unregistered" in result.error.lower():
                await self.repository.deactivate_token(token.token, result.error)

        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count

        logger.info(
            "fcm_batch_sent",
            user_id=str(user_id),
            success=success_count,
            failed=failure_count,
        )

        return FCMBatchResult(
            success_count=success_count,
            failure_count=failure_count,
            results=results,
        )

    async def send_reminder_notification(
        self,
        user_id: UUID,
        title: str,
        body: str,
        reminder_id: str,
    ) -> FCMBatchResult:
        """
        Send a reminder notification.

        Args:
            user_id: User UUID
            title: Notification title
            body: Notification body (reminder content)
            reminder_id: Reminder UUID for tracking

        Returns:
            FCMBatchResult
        """
        return await self.send_to_user(
            user_id=user_id,
            title=title,
            body=body,
            data={
                "type": "reminder",
                "reminder_id": reminder_id,
                "click_action": "OPEN_CHAT",
            },
        )

    async def _send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict | None = None,
        image_url: str | None = None,
    ) -> FCMSendResult:
        """
        Send notification to a single FCM token.

        Args:
            token: FCM token
            title: Notification title
            body: Notification body
            data: Optional data payload
            image_url: Optional image URL

        Returns:
            FCMSendResult
        """
        app = self._get_firebase_app()

        if app is None:
            return FCMSendResult(
                success=False,
                error="Firebase not configured",
                token=token,
            )

        try:
            from firebase_admin import messaging

            # Build notification
            notification = messaging.Notification(
                title=title,
                body=body,
                image=image_url,
            )

            # Build message
            message = messaging.Message(
                notification=notification,
                data=data or {},
                token=token,
                # Android config
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        click_action="OPEN_CHAT",
                        channel_id="reminders",
                    ),
                ),
                # iOS (APNs) config
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body,
                            ),
                            sound="default",
                            badge=1,
                        ),
                    ),
                ),
                # Web config
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=title,
                        body=body,
                        icon="/icon-192x192.png",
                        require_interaction=True,
                    ),
                ),
            )

            # Send message
            response = messaging.send(message)

            logger.debug(
                "fcm_message_sent",
                message_id=response,
                token_prefix=token[:20],
            )

            return FCMSendResult(
                success=True,
                message_id=response,
                token=token,
            )

        except Exception as e:
            error_msg = str(e)

            logger.error(
                "fcm_send_failed",
                error=error_msg,
                token_prefix=token[:20],
            )

            return FCMSendResult(
                success=False,
                error=error_msg,
                token=token,
            )

    # =========================================================================
    # Token Cleanup
    # =========================================================================

    async def cleanup_inactive_tokens(self, older_than_days: int = 30) -> int:
        """
        Clean up old inactive tokens.

        Args:
            older_than_days: Remove inactive tokens older than this

        Returns:
            Number of tokens removed
        """
        count = await self.repository.cleanup_inactive_tokens(older_than_days)

        if count > 0:
            logger.info("fcm_tokens_cleaned", count=count)

        return count

    # =========================================================================
    # Multicast (Batch) Sending
    # =========================================================================

    def is_enabled(self) -> bool:
        """
        Check if FCM is enabled and configured.

        Returns:
            True if Firebase app is available
        """
        return self._get_firebase_app() is not None

    async def send_multicast(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> tuple[int, int]:
        """
        Send FCM notifications to multiple tokens in batch.

        Firebase limit: 500 tokens per multicast call.
        Uses asyncio.to_thread since send_multicast is synchronous.

        Args:
            tokens: List of FCM token strings
            title: Notification title
            body: Notification body
            data: Optional data payload (values must be strings)

        Returns:
            Tuple of (success_count, failure_count)
        """
        if not tokens:
            return 0, 0

        app = self._get_firebase_app()
        if app is None:
            logger.warning("fcm_multicast_disabled")
            return 0, len(tokens)

        # Use individual send() calls like _send_to_token (proven to work)
        # send_multicast/send_each_for_multicast have issues with some Firebase configs
        from firebase_admin import messaging

        total_sent = 0
        total_failed = 0

        for token in tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data or {},
                    token=token,
                )

                messaging.send(message)
                total_sent += 1

            except Exception as e:
                total_failed += 1
                error_msg = str(e).lower()

                # Log only if not a known "unregistered" error
                if "unregistered" not in error_msg:
                    logger.warning(
                        "fcm_send_failed",
                        token_prefix=token[:20] if token else "none",
                        error=str(e),
                    )

        logger.debug(
            "fcm_multicast_completed",
            total_tokens=len(tokens),
            success=total_sent,
            failed=total_failed,
        )

        return total_sent, total_failed
