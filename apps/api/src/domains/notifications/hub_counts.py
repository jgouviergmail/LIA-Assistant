"""The five totals the notifications hub badges, resolved in one pass.

The hub stacks five folded sections, and each badge answers the question the
reader actually asks before unfolding: *is there anything in there?* That total
used to come from the paginated read the fold gated, so the badge said `—`
until the section was opened — the one number that decides whether to open a
section could only be had by opening it.

**One request, not five and not zero.** Five separate counts at mount would be
the client-side scatter the capability map exists to remove (ADR-204), with
five chances for two answers to disagree about the same account. And "a folded
section costs no request" (ADR-202) was never about arithmetic: it was about
not paying for ROWS nobody is looking at. A count is an aggregate over an
indexed column; the page, with its rows and its joins, still waits for the
fold.

Same shape as ``domains/capabilities/service.py``: independent probes gathered
with ``asyncio.gather``, **each on its own session** (an ``AsyncSession`` is not
safe for concurrent use), and every probe failing SOFT — one unreachable table
silences one badge rather than taking the hub down.

Each count comes from the SAME filter as the page it describes, by calling the
same repository the page calls. A total assembled from a different filter is
worse than no total at all (ADR-185).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import settings
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only, breaks an import cycle
    from src.domains.users.models import User

logger = get_logger(__name__)


@dataclass(frozen=True)
class HubCounts:
    """One exact total per hub section.

    Attributes:
        peer_messages: Relayed messages delivered, both directions.
        proactive: Proactive notifications ever sent.
        interests: Interest notifications ever sent.
        reminders: Reminders still waiting — this one is the FUTURE, not a
            history: a reminder is deleted the instant it fires.
        scheduled: Scheduled routines the account owns.
    """

    peer_messages: int
    proactive: int
    interests: int
    reminders: int
    scheduled: int


async def _safe_count(section: str, probe: Coroutine[None, None, int]) -> int:
    """Await one probe, degrading to 0 rather than failing the hub.

    Args:
        section: Which badge this counts, for the log line only.
        probe: The counting coroutine. Awaited exactly once — a coroutine
            handed to this function is always consumed, never dropped.

    Returns:
        The count, or 0 when the read failed.
    """
    try:
        return await probe
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug("hub_count_probe_failed", section=section, error=str(exc))
        return 0


async def _peer_messages(user_id: UUID) -> int:
    """Relayed messages — 0 without a query when the instance disabled peers.

    Gate-keeper (ADR-061): the hub does not render that section at all, so
    counting it would be two SQL statements for a badge nobody can see.
    """
    if not settings.peers_enabled:
        return 0
    async with get_db_context() as db:
        from src.domains.peers.repository import PeersRepository

        return await PeersRepository(db).count_delivered_messages(user_id)


async def _proactive(user_id: UUID) -> int:
    """Proactive notifications — 0 without a query when heartbeat is off."""
    if not settings.heartbeat_enabled:
        return 0
    async with get_db_context() as db:
        from src.domains.heartbeat.repository import HeartbeatNotificationRepository

        return await HeartbeatNotificationRepository(db).count_history_for_user(user_id)


async def _interests(user_id: UUID) -> int:
    async with get_db_context() as db:
        from src.domains.interests.repository import InterestNotificationRepository

        return await InterestNotificationRepository(db).count_history_for_user(user_id)


async def _reminders(user_id: UUID) -> int:
    async with get_db_context() as db:
        from src.domains.reminders.repository import ReminderRepository

        return await ReminderRepository(db).count_pending_for_user(user_id)


async def _scheduled(user_id: UUID) -> int:
    async with get_db_context() as db:
        from src.domains.scheduled_actions.repository import ScheduledActionRepository

        return await ScheduledActionRepository(db).count_for_user(user_id)


async def resolve_hub_counts(user: User) -> HubCounts:
    """Every hub badge, in one pass.

    Args:
        user: The authenticated user row.

    Returns:
        One exact total per section; 0 for any section whose read failed.
    """
    user_id: UUID = user.id
    peer_messages, proactive, interests, reminders, scheduled = await asyncio.gather(
        _safe_count("peer_messages", _peer_messages(user_id)),
        _safe_count("proactive", _proactive(user_id)),
        _safe_count("interests", _interests(user_id)),
        _safe_count("reminders", _reminders(user_id)),
        _safe_count("scheduled", _scheduled(user_id)),
    )
    return HubCounts(
        peer_messages=peer_messages,
        proactive=proactive,
        interests=interests,
        reminders=reminders,
        scheduled=scheduled,
    )
