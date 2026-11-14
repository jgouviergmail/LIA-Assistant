"""What a routine tells its owner: its result, its proposal, and why it did not run.

The executor decides WHAT happened to a tick; this module says it. Four things
leave from here, each best-effort — a message that fails never undoes the tick
it reports on:

- the RESULT of a run (push and toast; the archive is ``stream_chat_response``'s);
- the PROPOSAL of a propose-first routine (a ``?intent=`` link, ADR-173);
- a FAILURE, said at the first failure of a series and when the series pauses
  the routine — a routine used to fail five times and be switched off without
  one word to anybody;
- the USAGE CEILING standing a routine aside, claimed once per ACCOUNT per
  window: the ceiling blocks every routine of the account at once, and one
  notice per routine would be a burst.

A notice is a status report about something the person configured, not an act
LIA took on its own initiative: it goes through the dispatcher directly, like
the proposal, and files no register row (owner decision 2026-10-30).
"""

from __future__ import annotations

import json
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_QUOTA_NOTIFIED_KEY_PREFIX,
    SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH,
)
from src.core.i18n_drafts import label_separator
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.cache.user_channel import user_notifications_channel
from src.infrastructure.proactive.notification import plain_text_for_notification

if TYPE_CHECKING:
    from src.domains.scheduled_actions.models import ScheduledAction
    from src.domains.users.schemas import UserProfile

logger = structlog.get_logger(__name__)

#: The task type every routine notification is filed and titled under.
_TASK_TYPE = "scheduled_action"
#: The settings section the routines live in (``lib/settings-sections.ts``).
_ROUTINES_SECTION = "scheduled-actions"


class RoutineNotice(str, Enum):
    """Why a routine did not run as planned — the notices its owner may get.

    The values key ``ProactiveMessages._ROUTINE_NOTICE_BODIES`` and travel in
    the notification's metadata (``routine_notice``).
    """

    FAILED = "failed"  # A run failed: the first of a series, or one the person started.
    DISABLED = "disabled"  # The failures in a row paused the routine.
    QUOTA = "quota"  # The account's usage ceiling stood the routine aside.


def failure_notice(
    *, consecutive_failures: int, disabled: bool, manual: bool
) -> RoutineNotice | None:
    """Which notice a failed run owes the routine's owner, if any.

    A series is announced once, at its first failure, and once more when it
    pauses the routine; the failures in between are silent — the person
    already knows. A run the person started is waited for, so it always says
    it failed.

    Args:
        consecutive_failures: The routine's count AFTER this failure.
        disabled: Whether this failure paused the routine.
        manual: Whether the person started the run.

    Returns:
        The notice to send, or None for a failure already announced.
    """
    if disabled:
        return RoutineNotice.DISABLED
    if manual or consecutive_failures == 1:
        return RoutineNotice.FAILED
    return None


async def claim_quota_notice(user_id: uuid.UUID) -> bool:
    """Claim the account's usage-ceiling notice for the configured window.

    Atomic (``SET NX EX``): routines due the same minute run concurrently, and
    only one of them may tell the person. Fails CLOSED: without a cache, or on
    a cache failure, nobody is told — a missing convenience, where failing
    open would send the notice at every tick of every routine.

    Args:
        user_id: The account whose routines the ceiling stood aside.

    Returns:
        True when the caller holds the claim and must send the notice.
    """
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        if not redis:
            return False
        return bool(
            await redis.set(
                f"{SCHEDULED_ACTIONS_QUOTA_NOTIFIED_KEY_PREFIX}:{user_id}",
                "1",
                nx=True,
                ex=settings.scheduled_actions_quota_notice_cooldown_hours * 3600,
            )
        )
    except Exception as exc:  # noqa: BLE001 — a notice never costs the tick
        logger.warning(
            "scheduled_action_quota_notice_claim_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return False


async def _dispatch(
    db: AsyncSession,
    *,
    user: UserProfile,
    action: ScheduledAction,
    body: str,
    kind: str,
    metadata: dict[str, Any],
    user_language: str,
) -> None:
    """Send one message about a routine through the dispatcher; never raises.

    Args:
        db: The tick's session; the archived chat row is written on it.
        user: The routine's owner.
        action: The routine the message is about.
        body: The Markdown body, already in the owner's language.
        kind: Which message this is — a bounded word, for the log lines.
        metadata: Bounded payload the archived message carries.
        user_language: The owner's backend-canonical language.
    """
    from src.infrastructure.proactive.notification import NotificationDispatcher

    try:
        result = await NotificationDispatcher().dispatch(
            user=user,
            content=body,
            task_type=_TASK_TYPE,
            target_id=str(action.id),
            metadata=metadata,
            db=db,
            title=ProactiveMessages.notification_title(_TASK_TYPE, user_language),
        )
    except Exception as exc:  # noqa: BLE001 — a message never undoes the tick
        logger.warning(
            "scheduled_action_message_dispatch_failed",
            action_id=str(action.id),
            kind=kind,
            error_type=type(exc).__name__,
        )
        return
    # The verdict is read, never assumed (audit AC-003): a message that reached
    # no durable channel is one nobody will find later.
    logger.info(
        "scheduled_action_message_dispatched",
        action_id=str(action.id),
        kind=kind,
        durably_delivered=result.durably_delivered,
    )


async def send_approval_notification(
    db: AsyncSession,
    *,
    user: UserProfile,
    action: ScheduledAction,
    user_language: str,
) -> None:
    """Propose-first notification (N-07): a markdown [Run it now](?intent=) link.

    The absolute URL omits the locale segment on purpose (the connectors
    router precedent): the frontend middleware resolves the user's locale.
    Best-effort — a dispatch failure must not break the tick, the routine
    simply proposes again at its next one.

    Args:
        db: The tick's session.
        user: The routine's owner.
        action: The routine waiting for its owner's click.
        user_language: The owner's backend-canonical language.
    """
    intent_url = f"{settings.frontend_url}/dashboard/chat?intent={quote(action.action_prompt)}"
    await _dispatch(
        db,
        user=user,
        action=action,
        body=ProactiveMessages.routine_approval_body(action.title, intent_url, user_language),
        kind="proposal",
        metadata={"approval_proposal": True},
        user_language=user_language,
    )


async def send_routine_notice(
    db: AsyncSession,
    *,
    user: UserProfile,
    action: ScheduledAction,
    kind: RoutineNotice,
    user_language: str,
) -> None:
    """Tell the owner their routine did not run as planned; never raises.

    Sent AFTER the tick's outcome is committed: the notice reports a durable
    fact, and a crash while it leaves must not undo the marking.

    Args:
        db: The tick's session.
        user: The routine's owner.
        action: The routine.
        kind: Why it did not run.
        user_language: The owner's backend-canonical language.
    """
    routines_url = (
        f"{settings.frontend_url.rstrip('/')}/dashboard/settings?section={_ROUTINES_SECTION}"
    )
    await _dispatch(
        db,
        user=user,
        action=action,
        body=ProactiveMessages.routine_notice_body(
            kind.value,
            action.title,
            user_language,
            routines_url=routines_url,
            max_failures=SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
        ),
        kind=kind.value,
        metadata={"routine_notice": kind.value},
        user_language=user_language,
    )


def _truncate(text: str, max_length: int | None = None) -> str:
    """Truncate already-flattened text for a notification body.

    Args:
        text: Plain text — run it through ``plain_text_for_notification`` first;
            truncating raw HTML cuts mid-tag.
        max_length: Character budget. Defaults to
            ``settings.proactive_notification_max_length``, the same
            user-facing setting the proactive dispatcher honors.

    Returns:
        The text, ellipsized when it exceeds the budget.
    """
    if max_length is None:
        max_length = settings.proactive_notification_max_length
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


async def notify_result(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    action: ScheduledAction,
    content: str,
    user_language: str,
) -> None:
    """Push the result (FCM) and toast it (SSE); each best-effort.

    The archive is ``stream_chat_response``'s. The content is flattened ONCE
    for both surfaces, before any truncation: the agent response is rich
    content (HTML in ``html`` display mode, data cards in ``cards`` mode,
    Markdown otherwise) while a push body and a toast description both render
    their text verbatim.

    Args:
        db: The tick's session.
        user_id: The routine's owner.
        action: The routine that answered.
        content: The canonical, post-processed answer.
        user_language: The owner's backend-canonical language.
    """
    from src.domains.notifications.service import FCMNotificationService
    from src.infrastructure.cache.redis import get_redis_cache

    notification_text = plain_text_for_notification(content)
    try:
        await FCMNotificationService(db).send_to_user(
            user_id=user_id,
            # The reader's punctuation joins the label to the routine's title (ADR-323).
            title=f"{ProactiveMessages.notification_title(_TASK_TYPE, user_language)}"
            f"{label_separator(user_language)}{action.title}",
            body=_truncate(notification_text),
            data={"type": _TASK_TYPE, "action_id": str(action.id)},
        )
    except Exception as fcm_err:
        logger.warning(
            "scheduled_action_fcm_failed",
            action_id=str(action.id),
            error_type=type(fcm_err).__name__,
        )

    try:
        redis = await get_redis_cache()
        if redis:
            await redis.publish(
                user_notifications_channel(user_id),
                json.dumps(
                    {
                        "type": _TASK_TYPE,
                        "content": _truncate(
                            notification_text, SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH
                        ),
                        "action_id": str(action.id),
                        "title": action.title,
                    },
                    ensure_ascii=False,
                ),
            )
    except Exception as sse_err:
        logger.warning(
            "scheduled_action_sse_failed",
            action_id=str(action.id),
            error_type=type(sse_err).__name__,
        )
