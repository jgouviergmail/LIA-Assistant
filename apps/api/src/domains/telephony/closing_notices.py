"""What a call a sweep closed owes its owner — never a silent close (2026-11-14).

Two sweeps close a call nobody will report on: the stale-call reaper, when no
terminal webhook ever came (``stale_no_webhook``), and the return reaper,
giving up on a synthesis that kept failing (``return_synthesis_gave_up``, its
transcript purged). Both closed the row and said nothing: the person who asked
for the call never heard of it again (production, 2026-07-17). Each sweep now
arms the call's return outbox in its own transaction — ``PENDING`` and the
words — and the notification reaper delivers it like any return, to the
discussion the call was placed from while it lives (ADR-378 amendment).

A failure is said, never guessed: with no report, nobody knows whether the
call connected, and the words say exactly that.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import normalize_language
from src.core.i18n_telephony import get_return_phrases
from src.domains.telephony.models import CallKind
from src.domains.telephony.repository import ClosedCall, TelephonyRepository
from src.domains.users.models import User


class ClosingReason(StrEnum):
    """Why a sweep closed a call without its return."""

    NO_REPORT = "no_report"
    """No terminal webhook ever came: how the call ended is unknown."""
    SYNTHESIS_GAVE_UP = "synthesis_gave_up"
    """The report came, but its return could not be written."""


#: The sentence and the title each kind of call is told, by reason. A
#: verification call reads a code to its own owner: it owes no return.
_PHRASE_KEYS: Final[dict[tuple[CallKind, ClosingReason], tuple[str, str]]] = {
    (CallKind.THIRD_PARTY, ClosingReason.NO_REPORT): ("no_report", "title"),
    (CallKind.THIRD_PARTY, ClosingReason.SYNTHESIS_GAVE_UP): ("fallback", "title"),
    (CallKind.SELF, ClosingReason.NO_REPORT): ("relay_no_report", "self_call_title"),
    (CallKind.SELF, ClosingReason.SYNTHESIS_GAVE_UP): ("relay_failed", "self_call_title"),
}

#: A Live owner call brought every request to the chat while the person was on
#: the line: nothing is left to deliver (``mark_completed`` arms nothing either).
_LIVE_MODE: Final = "delegated"


def closing_notice(
    call: ClosedCall, reason: ClosingReason, *, language: str
) -> tuple[str, str] | None:
    """The words and the title a closed call owes its owner, or None.

    Args:
        call: The call a sweep closed.
        reason: Why it was closed.
        language: The owner's backend-canonical language.

    Returns:
        ``(content, title)``, or None when the call owes no return.
    """
    keys = _PHRASE_KEYS.get((call.call_kind, reason))
    if keys is None or (call.call_kind is CallKind.SELF and call.call_mode == _LIVE_MODE):
        return None
    content_key, title_key = keys
    phrases = get_return_phrases(language)
    return phrases[content_key].format(callee=call.callee_display), phrases[title_key]


async def _languages_of(db: AsyncSession, owners: set[UUID]) -> dict[UUID, str | None]:
    rows = await db.execute(select(User.id, User.language).where(User.id.in_(owners)))
    return dict(rows.tuples().all())


async def arm_closing_notices(
    db: AsyncSession,
    repo: TelephonyRepository,
    closed: Sequence[ClosedCall],
    reason: ClosingReason,
) -> int:
    """Arm the return of every call a sweep just closed, in its transaction.

    Args:
        db: The sweep's session (the caller commits the close and the notices
            together).
        repo: The sweep's repository.
        closed: The calls it closed.
        reason: Why.

    Returns:
        How many notices were armed.
    """
    if not closed:
        return 0
    languages = await _languages_of(db, {call.user_id for call in closed})
    armed = 0
    for call in closed:
        notice = closing_notice(
            call, reason, language=normalize_language(languages.get(call.user_id))
        )
        if notice is None:
            continue
        content, title = notice
        armed += int(await repo.arm_closing_notice(call.id, content=content, title=title))
    return armed


__all__ = ["ClosingReason", "arm_closing_notices", "closing_notice"]
