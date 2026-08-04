"""What LIA can actually do for this account, in one read.

The starter checklist detects seven capabilities CLIENT-side, through seven
hooks. That is fine for seven items on a card the reader dismisses once. It is
not fine for a living map of everything the assistant can do: a dozen requests
fired at mount, a dozen loading states, and a dozen chances for one of them to
disagree with another about whether voice is on.

So this reads them server-side, in one pass, following the briefing doctrine:
independent probes gathered with ``asyncio.gather``, **each on its own
session** (an ``AsyncSession`` is not safe for concurrent use), and every probe
failing SOFT — a capability whose probe raised is reported as not-ready rather
than taking the page down. A map that refuses to draw because one node could
not be counted is worse than a map with one dim node.

Three states, and the difference between the last two is the whole point:

- **unavailable** — the instance disabled the subsystem. It is not offered at
  all (gate-keeper, ADR-061): a control the product cannot honour is worse
  than an absent one;
- **dormant** — available, nothing set up. It carries the ONE next step;
- **live** — genuinely usable, with what makes it so (a count, a name).

No level, no experience points, no comparison with anyone. "Three connectors
linked" is a fact about this account; "you are 62 % complete" is a score, and
a score invites a competition nobody asked to enter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select

from src.core.config import settings
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only, breaks an import cycle
    from src.domains.users.models import User

logger = get_logger(__name__)


@dataclass(frozen=True)
class CapabilityProbe:
    """One node of the map, as the service resolved it.

    Attributes:
        key: Stable identifier — the client resolves its label from it, so a
            new capability never surfaces as a raw i18n key.
        available: Whether this instance offers the subsystem at all.
        active: Whether the account can actually use it right now.
        detail: A COUNT the reader can verify, when there is one. Never a
            score: "3 connectors" is a fact, "62 %" is a competition.
    """

    key: str
    available: bool
    active: bool
    detail: int | None = None


async def _count(model: Any, user_id: UUID, **filters: Any) -> int:
    """Count rows of one user-scoped table, on its OWN session.

    ``model`` is deliberately untyped: the helper accepts any mapped class
    carrying ``user_id``, and SQLAlchemy exposes those columns as ``Mapped[…]``
    descriptors that a ``Protocol`` cannot describe without making
    ``model.user_id == user_id`` un-typeable. The alternative — one counting
    function per table — would be ten copies of this query.

    Args:
        model: The mapped class. Must carry a ``user_id`` column.
        user_id: Owner.
        **filters: Extra equality filters.

    Returns:
        The count, or 0 when the read failed — a probe never raises, so one
        unreachable table cannot blank the whole map.
    """
    try:
        async with get_db_context() as db:
            stmt = select(func.count()).select_from(model).where(model.user_id == user_id)
            for column, value in filters.items():
                stmt = stmt.where(getattr(model, column) == value)
            return int((await db.execute(stmt)).scalar() or 0)
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug(
            "capability_probe_failed", model=getattr(model, "__name__", "?"), error=str(exc)
        )
        return 0


async def _connectors(user_id: UUID) -> CapabilityProbe:
    from src.domains.connectors.models import Connector

    total = await _count(Connector, user_id)
    return CapabilityProbe("connectors", available=True, active=total > 0, detail=total)


async def _memory(user_id: UUID) -> CapabilityProbe:
    from src.domains.memories.models import Memory

    total = await _count(Memory, user_id)
    return CapabilityProbe("memory", available=True, active=total > 0, detail=total)


async def _interests(user_id: UUID) -> CapabilityProbe:
    from src.domains.interests.models import InterestStatus, UserInterest

    total = await _count(UserInterest, user_id, status=InterestStatus.ACTIVE.value)
    return CapabilityProbe("interests", available=True, active=total > 0, detail=total)


async def _routines(user_id: UUID) -> CapabilityProbe:
    from src.domains.scheduled_actions.models import ScheduledAction

    total = await _count(ScheduledAction, user_id)
    return CapabilityProbe("routines", available=True, active=total > 0, detail=total)


async def _relations(user_id: UUID) -> CapabilityProbe:
    from src.domains.open_loops.models import OpenLoop

    total = await _count(OpenLoop, user_id)
    return CapabilityProbe("relations", available=True, active=total > 0, detail=total)


async def _journals(user_id: UUID) -> CapabilityProbe:
    from src.domains.journals.models import JournalEntry

    available = settings.journals_enabled
    total = await _count(JournalEntry, user_id) if available else 0
    return CapabilityProbe("journals", available=available, active=total > 0, detail=total)


async def _spaces(user_id: UUID) -> CapabilityProbe:
    available = settings.rag_spaces_enabled
    if not available:
        return CapabilityProbe("spaces", available=False, active=False)
    from src.domains.rag_spaces.models import RAGSpace

    total = await _count(RAGSpace, user_id)
    return CapabilityProbe("spaces", available=True, active=total > 0, detail=total)


async def _channels(user_id: UUID) -> CapabilityProbe:
    available = settings.channels_enabled
    if not available:
        return CapabilityProbe("channels", available=False, active=False)
    from src.domains.channels.models import UserChannelBinding

    total = await _count(UserChannelBinding, user_id)
    return CapabilityProbe("channels", available=True, active=total > 0, detail=total)


async def _peers(user_id: UUID) -> CapabilityProbe:
    available = settings.peers_enabled
    if not available:
        return CapabilityProbe("peers", available=False, active=False)
    try:
        async with get_db_context() as db:
            from src.domains.peers.repository import PeersRepository

            connections = await PeersRepository(db).list_accepted_for_user(user_id)
        total = len(connections)
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug("capability_probe_failed", model="peers", error=str(exc))
        total = 0
    return CapabilityProbe("peers", available=True, active=total > 0, detail=total)


async def _skills(user_id: UUID) -> CapabilityProbe:
    available = settings.skills_enabled
    if not available:
        return CapabilityProbe("skills", available=False, active=False)
    from src.domains.skills.models import UserSkillState

    total = await _count(UserSkillState, user_id)
    return CapabilityProbe("skills", available=True, active=total > 0, detail=total)


def _from_user(user: User) -> list[CapabilityProbe]:
    """Capabilities the USER row already answers — no query needed.

    Reading them from the authenticated row rather than re-querying keeps the
    map's answer identical to the one every other surface gives.
    """
    return [
        CapabilityProbe(
            "voice",
            available=True,
            active=user.voice_enabled or user.voice_mode_enabled,
        ),
        CapabilityProbe(
            "proactivity",
            available=settings.heartbeat_enabled,
            active=settings.heartbeat_enabled and user.heartbeat_enabled,
        ),
        CapabilityProbe(
            "personality",
            available=True,
            active=user.personality_id is not None,
        ),
    ]


async def resolve_capabilities(user: User) -> list[CapabilityProbe]:
    """Every capability of the map, resolved in one pass.

    Args:
        user: The authenticated user row.

    Returns:
        One probe per capability, in a STABLE order — the map's layout is
        deterministic, so the same account draws the same picture twice.
    """
    user_id: UUID = user.id
    probes = await asyncio.gather(
        _connectors(user_id),
        _memory(user_id),
        _interests(user_id),
        _routines(user_id),
        _relations(user_id),
        _journals(user_id),
        _spaces(user_id),
        _channels(user_id),
        _peers(user_id),
        _skills(user_id),
        return_exceptions=False,
    )
    return [*probes, *_from_user(user)]
