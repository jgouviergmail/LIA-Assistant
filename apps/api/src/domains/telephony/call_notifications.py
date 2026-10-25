"""The one door a phone call's notification leaves through (ADR-290 amendment 2026-10-24).

A call spends under ONE run id (``spend.phone_call_run_id``): its live
lookups, its synthesis and its relayed turn. The chat meter reads that bill
through the archived message's ``run_id`` (the history joins
``message_token_summary`` on it), so a notification archived WITHOUT it
shows no cost although the call has one — measured on production on
2026-10-24: a call whose relay ended ``empty`` had its synthesis on record
and a bubble showing nothing. Three paths archived a call's words that way
(the owner call's fallback, the third-party call's debrief, the reaper's
re-dispatch). Every dispatch of the phone-call task type now leaves through
here, so the run id travels by construction; a guard refuses any other
(``tests/unit/domains/telephony/test_call_notification_door_guard.py``).

The caller still builds the dispatcher: which channels a notification takes
(a push alone, or the archive too) is the caller's decision, never this
door's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from src.domains.telephony.spend import phone_call_run_id

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.users.models import User
    from src.infrastructure.proactive.notification import (
        NotificationDispatcher,
        NotificationResult,
    )

#: The task type of every notification a call sends.
CALL_TASK_TYPE: Final = "phone_call"


async def dispatch_call_notification(
    dispatcher: NotificationDispatcher,
    *,
    user: User,
    call_id: UUID,
    content: str,
    title: str | None,
    metadata: dict[str, Any],
    db: AsyncSession,
    require_durable: bool = False,
    push_enabled: bool = True,
) -> NotificationResult:
    """Dispatch a call's notification under the call's own run id.

    Args:
        dispatcher: The dispatcher the caller configured (its channels).
        user: The account the call belongs to.
        call_id: The ``phone_calls`` row — the target and the run.
        content: What the notification says.
        title: Its title (None: the dispatcher's localized default).
        metadata: The call's own metadata (status, relay outcome, debrief).
        db: The caller's session.
        require_durable: Raise unless a durable channel took it (AC-003).
        push_enabled: Whether the push channels run.

    Returns:
        What the dispatch reached.
    """
    return await dispatcher.dispatch(
        user=user,
        content=content,
        task_type=CALL_TASK_TYPE,
        target_id=str(call_id),
        metadata=metadata,
        db=db,
        title=title,
        run_id=phone_call_run_id(call_id),
        push_enabled=push_enabled,
        require_durable=require_durable,
    )


__all__ = ["CALL_TASK_TYPE", "dispatch_call_notification"]
