"""How a fired reminder reaches the person: push, channels, real time.

Split from ``reminder_notification``, which keeps the claim, the message and the
settlement, when the snooze (ADR-268 amendment 2026-11-16) gave every surface
something to offer:

- the push data names the occurrence and the two « later » a notification can
  show (a browser draws two actions at most), with the address a press posts to;
- the Telegram message carries the buttons (``reminder_keyboard``);
- the real-time event names the occurrence, for the open page's toast.

A reminder whose occurrence could not be recorded (no offer) is delivered as
before, with nothing to press: the record is never a gate.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.i18n_proactive import ProactiveMessages
from src.core.i18n_reminder_snooze import snooze_delay_label
from src.infrastructure.cache.user_channel import user_notifications_channel

if TYPE_CHECKING:
    from src.domains.reminders.firings import FiringOffer
    from src.domains.reminders.models import Reminder

logger = structlog.get_logger(__name__)


def get_localized_title(language: str) -> str:
    """Localized push/channel title for a fired reminder.

    Delegates to the central proactive table. The inline dict that used to live
    in the scheduler was keyed ``"zh"`` while ``User.language`` is
    backend-canonical ``"zh-CN"``, so every Chinese user received the English
    title — the exact defect [ADR-131] centralized this table to eliminate.

    Args:
        language: Any locale spelling; normalized by the accessor.

    Returns:
        The localized title, English fallback.
    """
    return ProactiveMessages.notification_title("reminder", language)


def truncate_for_notification(text: str, max_length: int | None = None) -> str:
    """Truncate text for a push notification body.

    Args:
        text: The message.
        max_length: Character budget. Defaults to
            ``settings.proactive_notification_max_length``, the setting the
            proactive dispatcher and the routine executor honour too.

    Returns:
        The text, ellipsized when it exceeds the budget.
    """
    if max_length is None:
        max_length = settings.proactive_notification_max_length
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def snooze_push_data(offer: FiringOffer | None, language: str) -> dict[str, str]:
    """The fields a web push needs to offer the postponement of its occurrence.

    A service worker has no translation of its own, so the two labels travel
    with the push; the address is the API's public one, the same base the OAuth
    callbacks use, which a browser reaches.

    Args:
        offer: The recorded occurrence, or None when it could not be recorded.
        language: The reader's language.

    Returns:
        The fields to add to the push data — none without an offer.
    """
    if offer is None:
        return {}
    base = f"{settings.api_url.rstrip('/')}{settings.api_prefix}"
    return {
        "firing_id": str(offer.firing_id),
        "snooze_url": f"{base}/reminders/firings/{offer.firing_id}/snooze",
        "snooze_short_label": snooze_delay_label(settings.reminder_snooze_short_minutes, language),
        "snooze_long_label": snooze_delay_label(settings.reminder_snooze_long_minutes, language),
    }


async def deliver_reminder(
    reminder: Reminder,
    *,
    title: str,
    message: str,
    language: str,
    offer: FiringOffer | None,
) -> Any:
    """Push the reminder to the person's devices and external channels.

    Args:
        reminder: The claimed reminder.
        title: The localized title.
        message: The full message, as the chat shows it.
        language: The reader's language.
        offer: The recorded occurrence, or None (delivered with nothing to press).

    Returns:
        The push batch result (raised failures are the caller's to settle).
    """
    from src.domains.notifications.service import FCMNotificationService
    from src.infrastructure.channels.telegram.reminder_keyboard import build_reminder_keyboard
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        fcm_result = await FCMNotificationService(db).send_reminder_notification(
            user_id=reminder.user_id,
            title=title,
            body=truncate_for_notification(message),
            reminder_id=str(reminder.id),
            snooze=snooze_push_data(offer, language),
        )
    if getattr(settings, "channels_enabled", False):
        keyboard = (
            build_reminder_keyboard(
                offer.firing_id,
                stoppable=offer.stoppable,
                short_minutes=settings.reminder_snooze_short_minutes,
                long_minutes=settings.reminder_snooze_long_minutes,
                language=language,
            )
            if offer is not None
            else None
        )
        try:
            from src.infrastructure.proactive.notification import send_notification_to_channels

            await send_notification_to_channels(
                user_id=reminder.user_id,
                title=title,
                body=message,
                task_type="reminder",
                target_id=str(reminder.id),
                language=language,
                reply_markup=keyboard,
            )
        except Exception as ch_error:
            logger.warning(
                "reminder_channels_failed",
                reminder_id=str(reminder.id),
                error_type=type(ch_error).__name__,
            )
    return fcm_result


async def publish_reminder(
    reminder: Reminder, *, title: str, message: str, offer: FiringOffer | None
) -> None:
    """Publish the reminder on the person's SSE channel (real time).

    Args:
        reminder: The claimed reminder.
        title: The localized title.
        message: The full message.
        offer: The recorded occurrence, which the toast offers to postpone.
    """
    from src.infrastructure.cache.redis import get_redis_cache

    event: dict[str, Any] = {
        "type": "reminder",
        "content": message,
        "reminder_id": str(reminder.id),
        "title": title,
    }
    if offer is not None:
        event["firing_id"] = str(offer.firing_id)
        event["snooze_short_minutes"] = settings.reminder_snooze_short_minutes
    try:
        redis = await get_redis_cache()
        if redis:
            await redis.publish(
                user_notifications_channel(reminder.user_id),
                json.dumps(event, ensure_ascii=False),
            )
    except Exception as redis_error:
        logger.warning(
            "reminder_redis_publish_failed",
            reminder_id=str(reminder.id),
            error_type=type(redis_error).__name__,
        )
