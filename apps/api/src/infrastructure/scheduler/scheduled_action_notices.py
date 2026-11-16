"""What a routine tells its owner: its result, its proposal, and why it did not run.

The executor decides WHAT happened to a tick; this module says it. Four things
leave from here, each best-effort — a message that fails never undoes the tick
it reports on:

- the RESULT of a run (push, toast and the external channels, whole; the archive
  is ``stream_chat_response``'s);
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
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    CHAT_DISCUSSION_LINK_TEMPLATE,
    SCHEDULED_ACTIONS_MAX_CONSECUTIVE_FAILURES,
    SCHEDULED_ACTIONS_QUOTA_NOTIFIED_KEY_PREFIX,
    SCHEDULED_ACTIONS_SSE_PREVIEW_MAX_LENGTH,
)
from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_drafts import label_separator
from src.core.i18n_proactive import ProactiveMessages
from src.infrastructure.cache.user_channel import user_notifications_channel
from src.infrastructure.proactive.notification import (
    plain_text_for_notification,
    send_notification_to_channels,
    with_discussion,
)

if TYPE_CHECKING:
    from src.core.conversation_target import ConversationOrigin
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
    origin: ConversationOrigin | None = None,
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
        origin: The discussion a run asked in the chat was asked in, else None.
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
            origin=origin,
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
    origin: ConversationOrigin | None = None,
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
        origin: The discussion a run asked in the chat was asked in: the
            notice returns there while it lives. None for a scheduled tick.
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
        origin=origin,
    )


@dataclass(frozen=True, slots=True)
class TickEnd:
    """What a tick leaves for the routine's owner once its outcome is durable."""

    text: str = ""
    """The answer to push; empty when the routine did not answer."""
    notice: RoutineNotice | None = None
    """Why it did not run as planned, when the owner is owed a word about it."""
    manual: bool = False
    """Whether the person started the run: such a run is always told its end."""
    silent: bool = False
    """The answer stays in the chat and is not pushed: its owner asked to be
    told only of something new, and the run declared it had nothing new."""


async def owed_notice(ended: TickEnd, user_id: uuid.UUID) -> RoutineNotice | None:
    """The notice to send once the tick is durable, if its owner is owed one.

    The ceiling's notice is the ACCOUNT's, claimed once per window whichever
    routine met the ceiling first; a run the person started is waited for, and
    is told whatever the claim says. Claimed after the commit: nothing is held
    while the cache answers (ADR-304).

    Args:
        ended: How the tick ended.
        user_id: The routine's owner.

    Returns:
        The notice, or None when there is nothing to say or it was said already.
    """
    if ended.notice is not RoutineNotice.QUOTA:
        return ended.notice
    claimed = await claim_quota_notice(user_id)
    return ended.notice if claimed or ended.manual else None


async def tell_tick_end(
    db: AsyncSession,
    ended: TickEnd,
    *,
    user: UserProfile,
    user_id: uuid.UUID,
    action: ScheduledAction,
    user_language: str,
    discussion: uuid.UUID | None,
    origin: ConversationOrigin | None,
) -> None:
    """Tell a routine's owner how a durable tick ended; each message best-effort.

    Called once the outcome is committed: a crash during a push must not re-run
    a routine that already answered. The answer is pushed unless the run had
    nothing new to say; the notice the tick owes follows.

    Args:
        db: The tick's session.
        ended: How the tick ended.
        user: The routine's owner.
        user_id: Their id.
        action: The routine.
        user_language: The owner's backend-canonical language.
        discussion: The annex the run answered in (a run asked there): the
            push opens it and the toast names it. None: Main.
        origin: The discussion a run asked in the chat was asked in: its
            notice returns there while that generation lives.
    """
    if ended.text and not ended.silent:
        await notify_result(
            db,
            user_id=user_id,
            action=action,
            content=ended.text,
            user_language=user_language,
            discussion=discussion,
        )
    notice = await owed_notice(ended, user_id)
    if notice is not None:
        await send_routine_notice(
            db, user=user, action=action, kind=notice, user_language=user_language, origin=origin
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
    discussion: uuid.UUID | None = None,
) -> None:
    """Send the result to the external channels, push it (FCM) and toast it (SSE).

    Each best-effort; the archive is ``stream_chat_response``'s. A channel
    reads the result whole, as the chat shows it, and draws it itself
    (Telegram lot 1). For the push and the toast the content is flattened ONCE,
    before any truncation: the agent response is rich content (HTML in
    ``html`` display mode, data cards in ``cards`` mode, Markdown otherwise)
    while a push body and a toast description both render their text verbatim.

    The channels go FIRST: the push reads and writes its device rows on the
    tick's session and leaves them for the caller's commit, so a channel
    reached after it would hold those row locks across Telegram (ADR-304).

    Args:
        db: The tick's session, committed when the result is told.
        user_id: The routine's owner.
        action: The routine that answered.
        content: The canonical, post-processed answer.
        user_language: The owner's backend-canonical language.
        discussion: The annex the run answered in (a run asked there): the
            push opens it and the toast names it. None: Main.
    """
    from src.domains.notifications.service import FCMNotificationService
    from src.infrastructure.cache.redis import get_redis_cache

    # The reader's punctuation joins the label to the routine's title (ADR-323).
    title = (
        f"{ProactiveMessages.notification_title(_TASK_TYPE, user_language)}"
        f"{label_separator(user_language)}{action.title}"
    )
    if settings.channels_enabled:
        try:
            await send_notification_to_channels(
                user_id=user_id,
                title=title,
                body=content,
                task_type=_TASK_TYPE,
                target_id=str(action.id),
                language=user_language,
            )
        except Exception as channel_err:  # noqa: BLE001 — a channel never undoes the tick
            logger.warning(
                "scheduled_action_channels_failed",
                action_id=str(action.id),
                error_type=type(channel_err).__name__,
            )

    notification_text = plain_text_for_notification(content)
    try:
        await FCMNotificationService(db).send_to_user(
            user_id=user_id,
            title=title,
            body=_truncate(notification_text),
            data={
                "type": _TASK_TYPE,
                "action_id": str(action.id),
                # The push names the annex as the live event does, and opens it.
                **(
                    {
                        FIELD_CONVERSATION_ID: str(discussion),
                        "url": CHAT_DISCUSSION_LINK_TEMPLATE.format(conversation_id=discussion),
                    }
                    if discussion is not None
                    else {}
                ),
            },
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
                        "metadata": with_discussion({}, discussion),
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
