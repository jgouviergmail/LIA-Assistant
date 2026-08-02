"""Relayed peer messages, seen from the personal CRM (peers spec §11, D2).

The additional read-only fetchers the peers design reserved for ``relations``:
own session, own failure boundary (briefing doctrine). Two entry points, two
questions:

- :func:`fetch_peer_message_activity` — "how many, how recently, with
  everyone?", for the overview;
- :func:`fetch_peer_messages_for` — "what did I exchange with THIS person?",
  for the one card a user actually opened. Page and total in one read, so a
  section never announces a count its own rows contradict.

Both read ONE store. Since ADR-186 the ledger keeps the words as well as the
fact — on a retention TTL, the contract phone calls already use — so the CRM
no longer has to hunt through the conversation archive for a text the relay
had erased. That removed a JSONB lookup, a provable-floor argument and a
clock-skew margin from this module: the durable answer was also the simpler
one.

Each side reads its OWN words: the sender's directive, the recipient's
assistant's rendering. A message whose text expired keeps its date and says
so — the fact of the exchange outlives the words, and no count ever promises
text that cannot be shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.domains.peers.repository import PeersRepository
from src.domains.shared.aggregates import NameActivity
from src.domains.shared.text_normalization import fold_name
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PeerMessageSignal:
    """One relayed message, already attached to a CRM identity key.

    Attributes:
        message_id: Ledger id, as a string — the stable key of the item.
        name_key: Folded peer name, the key the CRM buckets on.
        peer_display_name: The peer's live name, as stored.
        direction: ``received`` | ``sent`` (relative to the CRM's owner).
        content: The caller's own side of the exchange, or None once the
            retention horizon cleared it (and for anything delivered before
            ADR-186, which was erased for good).
        occurred_at: UTC instant of the delivery.
    """

    message_id: str
    name_key: str
    peer_display_name: str
    direction: str
    content: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class PeerMessagePage:
    """One relationship's relayed messages: the page AND its exact total.

    Returned together, from one read, so a section can never announce a count
    the rows below it contradict.
    """

    signals: list[PeerMessageSignal]
    total: int


#: The answer when the feature is off, the name is blank, or the read failed.
_EMPTY_PAGE = PeerMessagePage(signals=[], total=0)


def _bridge_unavailable(user_id: UUID, exc: Exception, event: str) -> None:
    """Log a degraded read of the peers bridge (ids only — never names)."""
    logger.warning(event, user_id=str(user_id), error_type=type(exc).__name__)


async def _read_page_for(
    db: AsyncSession,
    user_id: UUID,
    target_key: str,
    limit: int,
    identity_keys: frozenset[str],
) -> PeerMessagePage:
    """Gather one relationship's page and total, on one session.

    Split from the public entry point so the failure boundary and the feature
    gate stay one glance apart from the work itself.

    Args:
        db: Session owned by the caller's guarded block.
        user_id: Owner of the CRM.
        target_key: Folded name of the relationship being opened.
        limit: Cap on returned entries.
        identity_keys: Every folded key belonging to this identity (the
            canonical one plus anything merged into it).

    Returns:
        The page and the exact total, both derived from the same read.
    """
    repo = PeersRepository(db)
    aggregates = await repo.aggregate_delivered_messages_by_peer(user_id)
    mine = [item for item in aggregates if fold_name(item.raw_name) in identity_keys]
    activity = await repo.list_delivered_message_activity(
        user_id, limit=limit, peer_names=[item.raw_name for item in mine]
    )
    return PeerMessagePage(
        signals=[
            PeerMessageSignal(
                message_id=str(item.message_id),
                name_key=target_key,
                peer_display_name=item.peer_display_name,
                direction=item.direction,
                content=item.text,
                occurred_at=item.occurred_at,
            )
            for item in activity
        ],
        total=sum(item.count for item in mine),
    )


async def fetch_peer_message_activity(user_id: UUID) -> list[NameActivity]:
    """Exact per-peer message counts, for the CRM overview.

    Counts only — the overview needs how many and how recently, never the
    words.

    Args:
        user_id: Owner of the CRM.

    Returns:
        One entry per peer display name; empty when the feature is off or the
        read failed (same soft failure as the timeline — spec §11).
    """
    if not settings.peers_enabled:
        return []
    try:
        async with get_db_context() as db:
            return await PeersRepository(db).aggregate_delivered_messages_by_peer(user_id)
    except SQLAlchemyError as exc:
        _bridge_unavailable(user_id, exc, "relations_peer_activity_unavailable")
        return []


async def fetch_peer_messages_for(
    user_id: UUID,
    *,
    target_key: str,
    limit: int,
    merged_keys: frozenset[str] = frozenset(),
) -> PeerMessagePage:
    """The relayed-message page AND its exact total, for ONE relationship.

    Both halves come from ONE session and ONE instant. Asking twice would let
    a delivery land between the calls and show a total the page contradicts —
    the very inconsistency the exact-count work exists to remove.

    The page is narrowed in SQL to this person's stored spellings (resolved
    from the aggregate, folded in Python) rather than sliced out of a global
    page: otherwise a total of 12 could face an empty section as soon as those
    messages fell outside the newest ``limit`` of the whole timeline.

    Fails soft on purpose: this bridge enriches a CRM that stood on its own
    long before it existed, so a database hiccup degrades one section instead
    of returning a 500 for the whole page (spec §11, "own failure boundary").
    The failure is logged, never swallowed silently.

    Args:
        user_id: Owner of the CRM.
        target_key: Folded name of the relationship being opened.
        limit: Cap on returned entries, newest delivery first.
        merged_keys: Every folded key of this identity when relationships were
            merged. The merged-away half still stores messages under its OWN
            spelling, so matching the canonical key alone would drop them —
            and the total would then contradict a page it no longer covers.
            Defaults to "no merge", i.e. the pre-merge behaviour.

    Returns:
        The page and the exact total; both empty/zero when the peers feature
        is off or the read failed.
    """
    if not settings.peers_enabled or not target_key:
        return _EMPTY_PAGE
    try:
        async with get_db_context() as db:
            return await _read_page_for(
                db, user_id, target_key, limit, merged_keys or frozenset({target_key})
            )
    except SQLAlchemyError as exc:
        _bridge_unavailable(user_id, exc, "relations_peer_messages_unavailable")
        return _EMPTY_PAGE
