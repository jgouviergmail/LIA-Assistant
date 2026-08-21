"""Push channel service: notification handling + watch lifecycle (lot H).

Security contract of the notification path: unknown channels and bad tokens
are silently ignored (the router answers 200 regardless — never reveal what
the registry knows), a ``sync`` handshake is acknowledged without side
effects, and accepted notifications are debounced per channel before the
per-provider cache invalidation runs.

Watch lifecycle: ``sync_channels`` (leader-elected job) ensures a channel per
active Google connector and renews those close to expiry. Polling remains
the fallback — a failed watch never breaks anything, it only means staleness
stays bounded by cache TTLs instead of push.
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import REDIS_KEY_PUSH_DEBOUNCE_PREFIX
from src.domains.push_channels.cache_invalidation import invalidate_for_provider
from src.domains.push_channels.models import PushChannelProvider, WebhookChannel
from src.domains.push_channels.notifications import ChannelNotification, GmailPushEvent
from src.domains.push_channels.repository import PushChannelRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_push_channels import (
    push_notifications_total,
)

logger = structlog.get_logger(__name__)

# Drive watches target the whole changes feed — one logical target.
DRIVE_WATCH_TARGET = "changes"


class NotificationOutcome(str, Enum):
    """Result of authenticating and processing one push notification."""

    IGNORED_UNKNOWN = "ignored_unknown"
    IGNORED_BAD_TOKEN = "ignored_bad_token"
    IGNORED_STALE = "ignored_stale"
    SYNC_ACK = "sync_ack"
    DEBOUNCED = "debounced"
    PROCESSED = "processed"


class PushChannelService:
    """Notification handling + watch lifecycle over the channel registry."""

    def __init__(self, db: AsyncSession, repository: PushChannelRepository | None = None) -> None:
        """Bind the service to a session.

        Args:
            db: Async database session.
            repository: Optional repository override (tests).
        """
        self.db = db
        self.repo = repository or PushChannelRepository(db)

    # ========================================================================
    # Notification handling (webhook path)
    # ========================================================================

    async def handle_channel_notification(self, notif: ChannelNotification) -> NotificationOutcome:
        """Authenticate and process one X-Goog-* channel notification.

        Args:
            notif: The parsed notification.

        Returns:
            The processing outcome (the router answers 200 regardless).
        """
        channel = await self.repo.get_by_channel_id(notif.channel_id)
        if channel is None:
            return self._observed("unknown", NotificationOutcome.IGNORED_UNKNOWN)
        if not hmac.compare_digest(channel.token, notif.token):
            logger.warning(
                "push_notification_bad_token",
                channel_id=notif.channel_id,
            )
            return self._observed(channel.provider, NotificationOutcome.IGNORED_BAD_TOKEN)
        if notif.resource_state == "sync":
            return self._observed(channel.provider, NotificationOutcome.SYNC_ACK)
        if not await self._try_acquire_debounce(notif.channel_id):
            return self._observed(channel.provider, NotificationOutcome.DEBOUNCED)

        channel.last_notification_at = datetime.now(UTC)
        await self.db.commit()
        await invalidate_for_provider(channel.provider, channel.user_id)
        logger.info(
            "push_notification_processed",
            provider=channel.provider,
            channel_id=notif.channel_id,
            resource_state=notif.resource_state,
        )
        return self._observed(channel.provider, NotificationOutcome.PROCESSED)

    async def handle_gmail_push(
        self, event: GmailPushEvent, provided_token: str
    ) -> NotificationOutcome:
        """Authenticate and process one Gmail Pub/Sub push event (phase 2).

        Args:
            event: The parsed Gmail push event.
            provided_token: The ?token= value from the push subscription URL.

        Returns:
            The processing outcome (the router answers 200 regardless).
        """
        gmail = PushChannelProvider.GOOGLE_GMAIL.value
        expected = settings.gmail_pubsub_push_token or ""
        if not expected or not hmac.compare_digest(expected, provided_token):
            logger.warning("gmail_push_bad_token")
            return self._observed(gmail, NotificationOutcome.IGNORED_BAD_TOKEN)

        channel = await self.repo.get_by_provider_target(gmail, event.email_address)
        if channel is None:
            return self._observed(gmail, NotificationOutcome.IGNORED_UNKNOWN)

        # Pub/Sub deliveries are at-least-once and unordered: the historyId
        # ledger makes processing idempotent.
        if channel.last_history_id is not None and event.history_id <= channel.last_history_id:
            return self._observed(gmail, NotificationOutcome.IGNORED_STALE)
        if not await self._try_acquire_debounce(channel.channel_id):
            return self._observed(gmail, NotificationOutcome.DEBOUNCED)

        channel.last_history_id = event.history_id
        channel.last_notification_at = datetime.now(UTC)
        await self.db.commit()
        await invalidate_for_provider(channel.provider, channel.user_id)
        logger.info(
            "gmail_push_processed",
            channel_id=channel.channel_id,
            history_id=event.history_id,
        )
        return self._observed(gmail, NotificationOutcome.PROCESSED)

    @staticmethod
    def _observed(provider: str, outcome: NotificationOutcome) -> NotificationOutcome:
        """Count the outcome (bounded label sets) and pass it through."""
        push_notifications_total.labels(provider=provider, outcome=outcome.value).inc()
        return outcome

    async def _try_acquire_debounce(self, channel_id: str) -> bool:
        """One invalidation per channel per debounce window (best-effort).

        A Redis failure returns True (process the notification): missing a
        debounce costs one redundant invalidation, missing a notification
        costs freshness.
        """
        try:
            redis = await get_redis_cache()
            acquired = await redis.set(
                f"{REDIS_KEY_PUSH_DEBOUNCE_PREFIX}{channel_id}",
                "1",
                nx=True,
                ex=settings.push_notification_debounce_seconds,
            )
            return bool(acquired)
        except Exception:  # noqa: BLE001 — best-effort gate, never blocks the path
            return True

    # ========================================================================
    # Watch lifecycle (leader-elected sync job)
    # ========================================================================

    async def ensure_calendar_watch(self, user_id: UUID, client: Any) -> WebhookChannel | None:
        """Ensure a live events.watch channel on the user's primary calendar.

        Args:
            user_id: Channel owner.
            client: A GoogleCalendarClient bound to the user.

        Returns:
            The live channel, or None when push is not configured/needed.
        """
        return await self._ensure_channel(
            user_id,
            PushChannelProvider.GOOGLE_CALENDAR.value,
            watch_target="primary",
            opener=lambda channel_id, token, address, ttl: client.watch_events(
                channel_id=channel_id, token=token, address=address, ttl_seconds=ttl
            ),
            stopper=client.stop_channel,
        )

    async def ensure_drive_watch(self, user_id: UUID, client: Any) -> WebhookChannel | None:
        """Ensure a live changes.watch channel on the user's Drive.

        Args:
            user_id: Channel owner.
            client: A GoogleDriveClient bound to the user.

        Returns:
            The live channel, or None when push is not configured/needed.
        """

        async def _open(channel_id: str, token: str, address: str, ttl: int) -> dict[str, Any]:
            page_token = await client.get_changes_start_page_token()
            response: dict[str, Any] = await client.watch_changes(
                channel_id=channel_id,
                token=token,
                address=address,
                ttl_seconds=ttl,
                page_token=page_token,
            )
            response["_page_token"] = page_token
            return response

        return await self._ensure_channel(
            user_id,
            PushChannelProvider.GOOGLE_DRIVE.value,
            watch_target=DRIVE_WATCH_TARGET,
            opener=_open,
            stopper=client.stop_channel,
        )

    async def ensure_gmail_watch(
        self, user_id: UUID, client: Any, email_address: str
    ) -> WebhookChannel | None:
        """Ensure a live Gmail users.watch subscription (phase 2).

        Gmail has no channel/stop pair: re-issuing users.watch replaces the
        previous subscription, and expiry is fixed at 7 days by Google.

        Args:
            user_id: Channel owner.
            client: A GoogleGmailSettingsClient bound to the user.
            email_address: The mailbox address (Pub/Sub events resolve by it).

        Returns:
            The live channel row, or None when phase 2 is not configured.
        """
        topic = settings.gmail_pubsub_topic
        if not topic:
            return None
        provider = PushChannelProvider.GOOGLE_GMAIL.value
        existing = await self.repo.get_for_user(user_id, provider, email_address)
        if existing is not None and not self._needs_renewal(existing):
            return existing

        response = await client.watch_mailbox(topic)
        expiration = self._parse_expiration_ms(response.get("expiration"))
        history_id = self._parse_int(response.get("historyId"))
        if existing is None:
            existing = WebhookChannel(
                user_id=user_id,
                provider=provider,
                watch_target=email_address,
                channel_id=uuid.uuid4().hex,
                token=secrets.token_urlsafe(32),
                expiration=expiration,
                last_history_id=history_id,
            )
            self.db.add(existing)
        else:
            existing.expiration = expiration
            if history_id is not None and (
                existing.last_history_id is None or history_id > existing.last_history_id
            ):
                existing.last_history_id = history_id
        await self.db.commit()
        logger.info(
            "gmail_watch_ensured",
            user_id=str(user_id),
            expiration=expiration.isoformat(),
        )
        return existing

    async def _ensure_channel(
        self,
        user_id: UUID,
        provider: str,
        watch_target: str,
        opener: Any,
        stopper: Any,
    ) -> WebhookChannel | None:
        """Create or renew one X-Goog channel (calendar/drive shared path)."""
        address = settings.push_webhook_url
        if not address:
            logger.warning("push_webhook_url_not_configured", provider=provider)
            return None

        existing = await self.repo.get_for_user(user_id, provider, watch_target)
        if existing is not None and not self._needs_renewal(existing):
            return existing

        channel_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        response = await opener(channel_id, token, address, settings.push_watch_ttl_seconds)
        expiration = self._parse_expiration_ms(response.get("expiration"))
        resource_id = response.get("resourceId")

        if existing is not None:
            # Best-effort stop of the superseded channel — it would expire on
            # its own; a failed stop only means a few duplicate notifications.
            if existing.resource_id:
                try:
                    await stopper(existing.channel_id, existing.resource_id)
                except Exception as exc:  # noqa: BLE001 — superseded channel
                    logger.debug(
                        "push_channel_stop_failed",
                        provider=provider,
                        error=str(exc),
                    )
            existing.channel_id = channel_id
            existing.token = token
            existing.resource_id = resource_id
            existing.expiration = expiration
            existing.page_token = response.get("_page_token", existing.page_token)
        else:
            existing = WebhookChannel(
                user_id=user_id,
                provider=provider,
                watch_target=watch_target,
                channel_id=channel_id,
                token=token,
                resource_id=resource_id,
                expiration=expiration,
                page_token=response.get("_page_token"),
            )
            self.db.add(existing)
        await self.db.commit()
        logger.info(
            "push_channel_ensured",
            provider=provider,
            user_id=str(user_id),
            expiration=expiration.isoformat(),
        )
        return existing

    def _needs_renewal(self, channel: WebhookChannel) -> bool:
        """A channel expiring within the renewal margin must be recreated."""
        margin = timedelta(seconds=settings.push_renewal_margin_seconds)
        return channel.expiration <= datetime.now(UTC) + margin

    @staticmethod
    def _parse_expiration_ms(raw: Any) -> datetime:
        """Google returns expiration as epoch milliseconds (string)."""
        try:
            return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
        except TypeError, ValueError:
            # Defensive: an unparseable expiration means "renew at next sync".
            return datetime.now(UTC)

    @staticmethod
    def _parse_int(raw: Any) -> int | None:
        try:
            return int(raw)
        except TypeError, ValueError:
            return None
