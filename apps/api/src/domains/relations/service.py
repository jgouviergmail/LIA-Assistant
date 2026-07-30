"""RelationsService (N-09) — read-only personal-CRM aggregation.

Aggregates the DB-local signals that already carry a person's name — open
loops (``counterparty``), phone calls (``callee_display``), memories — around
each relationship. No provider call, no new table, no LangGraph.

Identity resolution is best-effort and stated as such (``IdentityConfidence``):
names are grouped after accent/case folding; a group whose raw names are all
identical is ``EXACT``, otherwise ``NORMALIZED``. Birthday/contacts matching is
a documented phase 2 (it needs the contacts connector and a contact↔relation
identity surface) — see ADR-176.

Concurrency: a handful of indexed queries per request, run SEQUENTIALLY on one
session (the CLAUDE guidance for this case) — no ``asyncio.gather``, so no
shared-session hazard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.peers.repository import PeersRepository
from src.domains.relations.repository import RelationFavoriteRepository
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationMemory,
    RelationOpenLoop,
    RelationsOverview,
    RelationSummary,
)
from src.domains.shared.text_normalization import fold_name
from src.domains.telephony.repository import TelephonyRepository
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _normalize_name(name: str) -> str:
    """Accent- and case-fold a display name into a grouping key.

    Delegates to the shared folding chokepoint (``shared/text_normalization``,
    hoisted for the peers discovery search) — behavior unchanged: empty or
    whitespace-only names fold to '' and are dropped by the caller.
    """
    return fold_name(name)


def _days_between(then: datetime, now: datetime) -> int:
    return max(0, (now - then).days)


def _match_open_loops(
    loops: list, target_key: str, now: datetime
) -> tuple[list[RelationOpenLoop], set[str]]:
    """Open loops of one relationship + the raw counterparty spellings seen."""
    matched: list[RelationOpenLoop] = []
    names: set[str] = set()
    for loop in loops:
        if _normalize_name(loop.counterparty or "") != target_key:
            continue
        names.add((loop.counterparty or "").strip())
        matched.append(
            RelationOpenLoop(
                id=str(loop.id),
                subject=loop.subject,
                direction=loop.direction,
                due_hint=loop.due_hint,
                days_open=_days_between(loop.created_at, now),
            )
        )
    return matched, names


def _match_calls(calls: list, target_key: str) -> tuple[list[RelationCall], set[str]]:
    """Calls of one relationship + the raw callee spellings seen."""
    matched: list[RelationCall] = []
    names: set[str] = set()
    for call in calls:
        if _normalize_name(call.callee_display or "") != target_key:
            continue
        names.add((call.callee_display or "").strip())
        matched.append(
            RelationCall(
                id=str(call.id),
                objective=call.objective,
                outcome=call.outcome.value if call.outcome else None,
                summary=call.summary,
                created_at=call.created_at,
            )
        )
    return matched, names


def _match_memories(memories: list, target_key: str) -> list[RelationMemory]:
    """Memories whose text contains the person's name (best-effort substring).

    A common first name over-matches — surfaced, never authoritative (the
    detail panel states the best-effort nature on a normalized match).
    """
    if not target_key:
        return []
    return [
        RelationMemory(id=str(memory.id), content=memory.content)
        for memory in memories
        if target_key in _normalize_name(memory.content)
    ]


@dataclass
class _Bucket:
    """Accumulator for one normalized relationship key."""

    raw_names: set[str] = field(default_factory=set)
    open_loops: list[RelationOpenLoop] = field(default_factory=list)
    calls: list[RelationCall] = field(default_factory=list)
    last_interaction_at: datetime | None = None

    def note_interaction(self, when: datetime | None) -> None:
        if when is None:
            return
        if self.last_interaction_at is None or when > self.last_interaction_at:
            self.last_interaction_at = when


def _bucketize(loops: list, calls: list, now: datetime) -> dict[str, _Bucket]:
    """Fold loops + calls into per-identity buckets (blank names dropped)."""
    buckets: dict[str, _Bucket] = {}
    for loop in loops:
        key = _normalize_name(loop.counterparty or "")
        if not key:
            continue
        bucket = buckets.setdefault(key, _Bucket())
        bucket.raw_names.add((loop.counterparty or "").strip())
        bucket.open_loops.append(
            RelationOpenLoop(
                id=str(loop.id),
                subject=loop.subject,
                direction=loop.direction,
                due_hint=loop.due_hint,
                days_open=_days_between(loop.created_at, now),
            )
        )
        bucket.note_interaction(loop.created_at)

    for call in calls:
        key = _normalize_name(call.callee_display or "")
        if not key:
            continue
        bucket = buckets.setdefault(key, _Bucket())
        bucket.raw_names.add((call.callee_display or "").strip())
        bucket.calls.append(
            RelationCall(
                id=str(call.id),
                objective=call.objective,
                outcome=call.outcome.value if call.outcome else None,
                summary=call.summary,
                created_at=call.created_at,
            )
        )
        bucket.note_interaction(call.created_at)
    return buckets


class RelationsService:
    """Aggregator for the personal CRM. Created per request (holds only ids)."""

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def build_overview(self) -> RelationsOverview:
        """Rank relationships by most-recent interaction (loops + calls)."""
        now = datetime.now(UTC)

        async with get_db_context() as db:
            loops = await OpenLoopRepository(db).list_open_for_user(
                self.user_id, limit=settings.relations_max_items * 4
            )
            calls = await TelephonyRepository(db).list_recent_for_user(
                self.user_id, limit=settings.relations_max_items * 4
            )
            favorites = await self._load_favorites(db)
            peer_keys = await self._load_peer_keys(db)

        buckets = _bucketize(loops, calls, now)

        # A starred name without any live signal still deserves its card:
        # inject an empty bucket carrying the spelling the user starred.
        for key, spelling in favorites.items():
            if key not in buckets:
                empty = buckets.setdefault(key, _Bucket())
                empty.raw_names.add(spelling)

        summaries = [
            RelationSummary(
                display_name=self._display_name(bucket.raw_names),
                identity_confidence=self._confidence(bucket.raw_names),
                open_loops_count=len(bucket.open_loops),
                calls_count=len(bucket.calls),
                last_interaction_at=bucket.last_interaction_at,
                is_favorite=key in favorites,
                is_peer=key in peer_keys,
            )
            for key, bucket in buckets.items()
        ]
        # Favorites first (they must also survive the cap), then most-recent
        # interaction (None last), then name for stability.
        summaries.sort(
            key=lambda s: (
                s.is_favorite,
                s.last_interaction_at is not None,
                s.last_interaction_at or datetime.min.replace(tzinfo=UTC),
                s.display_name,
            ),
            reverse=True,
        )
        return RelationsOverview(relations=summaries[: settings.relations_max_items])

    async def build_detail(self, name: str) -> RelationDetail:
        """The 360° view of one relationship, resolved by normalized name.

        Kept flat (CC discipline): each source is filtered + mapped by a
        module helper, and the raw names seen across sources drive the
        display name + confidence.
        """
        target_key = _normalize_name(name)
        now = datetime.now(UTC)
        per_section = settings.relations_max_items_per_section

        async with get_db_context() as db:
            loops = await OpenLoopRepository(db).list_open_for_user(self.user_id, limit=200)
            phone_calls = await TelephonyRepository(db).list_recent_for_user(
                self.user_id, limit=200
            )
            # Imported lazily to keep the domain import surface flat.
            from src.domains.memories.repository import MemoryRepository

            all_memories = await MemoryRepository(db).get_all_for_user(self.user_id, limit=500)
            favorites = await self._load_favorites(db)
            peer_keys = await self._load_peer_keys(db)

        open_loops, loop_names = _match_open_loops(loops, target_key, now)
        calls, call_names = _match_calls(phone_calls, target_key)
        memories = _match_memories(all_memories, target_key)
        raw_names = loop_names | call_names

        return RelationDetail(
            display_name=self._display_name(raw_names) or name.strip(),
            identity_confidence=self._confidence(raw_names),
            open_loops=open_loops[:per_section],
            recent_calls=calls[:per_section],
            memories=memories[:per_section],
            is_favorite=target_key in favorites,
            is_peer=target_key in peer_keys,
        )

    async def _load_favorites(self, db: AsyncSession) -> dict[str, str]:
        """The user's stars, as ``name_key -> starred spelling``."""
        rows = await RelationFavoriteRepository(db).list_for_user(self.user_id)
        return {row.name_key: row.display_name for row in rows}

    async def _load_peer_keys(self, db: AsyncSession) -> set[str]:
        """Folded names of connected LIA peers (empty when the flag is off)."""
        if not getattr(settings, "peers_enabled", False):
            return set()
        return set(await PeersRepository(db).list_accepted_peer_names(self.user_id))

    async def add_favorite(self, name: str) -> None:
        """Star a relationship name (idempotent).

        Args:
            name: Display name as typed/shown — folded for identity, stored
                verbatim (trimmed) for rendering.
        """
        display = name.strip()
        key = _normalize_name(display)
        if not key:
            return
        async with get_db_context() as db:
            await RelationFavoriteRepository(db).add(
                self.user_id, name_key=key, display_name=display
            )
        logger.info("relation_favorite_added", user_id=str(self.user_id))

    async def remove_favorite(self, name: str) -> bool:
        """Unstar a relationship name.

        Args:
            name: Display name (folded to the identity key).

        Returns:
            True when a star existed.
        """
        key = _normalize_name(name)
        if not key:
            return False
        async with get_db_context() as db:
            removed = await RelationFavoriteRepository(db).remove(self.user_id, name_key=key)
        logger.info("relation_favorite_removed", user_id=str(self.user_id), removed=removed)
        return removed

    @staticmethod
    def _display_name(raw_names: set[str]) -> str:
        """Pick the "properest" spelling, deterministically.

        Score = capitals + accented letters (the proper-noun spelling beats an
        all-lowercase echo of the same name); ties break on length then the
        string itself, so the result never depends on set iteration order.
        """
        if not raw_names:
            return ""

        def _score(name: str) -> tuple[int, int, str]:
            richness = sum(1 for c in name if c.isupper() or not c.isascii())
            return (richness, len(name), name)

        return max(raw_names, key=_score)

    @staticmethod
    def _confidence(raw_names: set[str]) -> IdentityConfidence:
        """EXACT when every source spelled the name identically."""
        return IdentityConfidence.EXACT if len(raw_names) <= 1 else IdentityConfidence.NORMALIZED
