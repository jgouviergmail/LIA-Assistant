"""RelationsService (N-09) — read-only personal-CRM aggregation.

Aggregates the DB-local signals that already carry a person's name — open
loops (``counterparty``), phone calls (``callee_display``), memories — plus the
messages relayed between assistants (peers bridge, ADR-185). No provider call,
no new table, no LangGraph.

Every source answers by AGGREGATE, not by page: a count the UI shows is a
claim, and deriving it from the length of a capped window was how the previous
implementation under-reported (ADR-185). The 360° view then queries each
source FOR ONE PERSON, by the exact spellings those aggregates reported —
so ``fold_name`` stays the only implementation of "same person" and SQL never
gets a second opinion — and states each section's exact total next to its page.

Identity resolution is best-effort and stated as such (``IdentityConfidence``):
names are grouped after accent/case folding; a group whose raw names are all
identical is ``EXACT``, otherwise ``NORMALIZED``. Birthday/contacts matching is
a documented phase 2 (it needs the contacts connector and a contact↔relation
identity surface) — see ADR-176.

Concurrency: a handful of indexed queries per request, run SEQUENTIALLY on one
session (the CLAUDE guidance for this case) — no ``asyncio.gather``, so no
shared-session hazard. The peers bridge is the exception: it opens its OWN
session outside that block, so a failure there degrades one section instead of
poisoning the transaction the rest of the CRM runs on (spec §11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.peers.repository import PeersRepository
from src.domains.peers.schemas import PeerConnectionProfile
from src.domains.relations.identity import NO_MERGES, IdentityResolver
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.peer_messages import (
    PeerMessageSignal,
    fetch_peer_message_activity,
    fetch_peer_messages_for,
)
from src.domains.relations.repository import (
    RelationAliasRepository,
    RelationFavoriteRepository,
)
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationMemory,
    RelationOpenLoop,
    RelationPeerLink,
    RelationPeerMessage,
    RelationShare,
    RelationsOverview,
    RelationSummary,
)
from src.domains.shared.aggregates import NameActivity
from src.domains.shared.text_normalization import fold_name
from src.domains.telephony.repository import TelephonyRepository
from src.domains.users.models import User
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


def _to_open_loop(loop: Any, now: datetime) -> RelationOpenLoop:
    """Map one open-loop row onto the API contract."""
    return RelationOpenLoop(
        id=str(loop.id),
        subject=loop.subject,
        direction=loop.direction,
        due_hint=loop.due_hint,
        days_open=_days_between(loop.created_at, now),
    )


def _to_call(call: Any) -> RelationCall:
    """Map one phone-call row onto the API contract (never the number — D-8)."""
    return RelationCall(
        id=str(call.id),
        objective=call.objective,
        outcome=call.outcome.value if call.outcome else None,
        summary=call.summary,
        created_at=call.created_at,
    )


@dataclass
class _Bucket:
    """Exact activity accumulated for one normalized relationship key."""

    raw_names: set[str] = field(default_factory=set)
    open_loops_count: int = 0
    calls_count: int = 0
    peer_messages_count: int = 0
    last_interaction_at: datetime | None = None

    def note_interaction(self, when: datetime | None) -> None:
        if when is None:
            return
        if self.last_interaction_at is None or when > self.last_interaction_at:
            self.last_interaction_at = when


def _touch(
    buckets: dict[str, _Bucket], item: NameActivity, resolver: IdentityResolver
) -> _Bucket | None:
    """Locate (or open) the bucket one aggregate row belongs to.

    Folding happens HERE and nowhere else: sources hand over raw spellings,
    and two spellings of the same person land in the same bucket — which is
    also how the confidence learns they disagreed.

    The resolver adds the merges the USER declared on top of the fold, so a
    merged relationship yields ONE bucket carrying both spellings.

    Args:
        buckets: Accumulator, keyed by identity.
        item: One source aggregate row.
        resolver: Folding + the user's merges.

    Returns:
        The bucket, or None when the name folds to nothing (never a phantom).
    """
    key = resolver.key(item.raw_name)
    if not key:
        return None
    bucket = buckets.setdefault(key, _Bucket())
    bucket.raw_names.add(item.raw_name.strip())
    bucket.note_interaction(item.last_at)
    return bucket


def _bucketize(
    loops: list[NameActivity],
    calls: list[NameActivity],
    messages: list[NameActivity],
    *,
    resolver: IdentityResolver = NO_MERGES,
) -> dict[str, _Bucket]:
    """Fold every source's exact aggregates into per-identity buckets.

    Args:
        loops: Open-commitment aggregates.
        calls: Call aggregates.
        messages: Relayed-message aggregates.
        resolver: Folding + the user's merges (defaults to no merge).

    Returns:
        One bucket per identity, keyed by canonical key.
    """
    buckets: dict[str, _Bucket] = {}
    for item in loops:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.open_loops_count += item.count
    for item in calls:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.calls_count += item.count
    for item in messages:
        if (bucket := _touch(buckets, item, resolver)) is not None:
            bucket.peer_messages_count += item.count
    return buckets


def _spellings_for(
    aggregates: list[NameActivity],
    target_key: str,
    *,
    resolver: IdentityResolver = NO_MERGES,
) -> list[str]:
    """The raw spellings of one identity, as the sources store them.

    This is what lets the 360° view query by EXACT string while keeping the
    resolver the only authority on who is the same person — SQL never gets a
    second opinion. After a merge, the merged-away side still stores its OWN
    spelling, so it must appear here or its rows are invisible on the card.

    Args:
        aggregates: Source aggregate rows.
        target_key: Canonical identity key.
        resolver: Folding + the user's merges.

    Returns:
        Every raw spelling belonging to that identity.
    """
    return [item.raw_name for item in aggregates if resolver.key(item.raw_name) == target_key]


def _total_for(
    aggregates: list[NameActivity],
    target_key: str,
    *,
    resolver: IdentityResolver = NO_MERGES,
) -> int:
    """Exact number of rows one identity holds across all its spellings.

    Args:
        aggregates: Source aggregate rows.
        target_key: Canonical identity key.
        resolver: Folding + the user's merges.

    Returns:
        The exact total, merged halves included.
    """
    return sum(item.count for item in aggregates if resolver.key(item.raw_name) == target_key)


def _to_peer_message(signal: PeerMessageSignal) -> RelationPeerMessage:
    """Map one bridge signal onto the API contract."""
    return RelationPeerMessage(
        id=signal.message_id,
        direction=signal.direction,
        content=signal.content,
        occurred_at=signal.occurred_at,
    )


class RelationsService:
    """Aggregator for the personal CRM. Created per request (holds only ids)."""

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def get_overview_scope(self) -> RelationOverviewScope:
        """What this user's 360° point is allowed to read.

        Returns:
            The stored scope, or the defaults when nothing was ever saved (or
            when the stored shape predates this version — see `from_stored`).
        """
        async with get_db_context() as db:
            user = await db.get(User, self.user_id)
            raw = user.relation_overview_scope if user is not None else None
        return RelationOverviewScope.from_stored(raw)

    async def set_overview_scope(self, scope: RelationOverviewScope) -> None:
        """Persist the scope BEFORE the chat link opens.

        That ordering is the whole design: the request carries prose, so the
        selection has to be readable server-side by the time the tool runs.
        Writing it here also makes it the pre-filled default next time.

        Args:
            scope: The validated selection.
        """
        async with get_db_context() as db:
            user = await db.get(User, self.user_id)
            if user is None:  # defensive — the session dependency resolved them
                return
            # A NEW dict, never an in-place mutation: SQLAlchemy skips the
            # UPDATE when a JSONB column is mutated in place (CLAUDE.md).
            user.relation_overview_scope = scope.model_dump(mode="json")
            await db.commit()
        logger.info(
            "relations_overview_scope_saved",
            user_id=str(self.user_id),
            sections=len(scope.sections),
            max_items=scope.max_items,
        )

    async def build_overview(self) -> RelationsOverview:
        """Rank relationships by most-recent interaction, with EXACT counts.

        Every source answers by aggregate, not by page: the counts a card
        shows are claims, and the previous implementation derived them from a
        capped window of rows — so a busy user's card silently under-reported
        and a person whose only activity fell outside the window had no card
        at all.
        """
        async with get_db_context() as db:
            loops = await OpenLoopRepository(db).aggregate_open_by_counterparty(self.user_id)
            calls = await TelephonyRepository(db).aggregate_calls_by_callee(self.user_id)
            resolver = await self._load_identity_resolver(db)
            favorites = self._canonical_favorites(await self._load_favorites(db), resolver=resolver)
            peer_keys = self._peer_keys(await self._load_peer_profiles(db), resolver=resolver)

        # Own session, own failure boundary (peers spec §11) — deliberately
        # OUTSIDE the block above, so a failed statement there could never
        # poison the transaction the rest of the CRM runs on.
        messages = await fetch_peer_message_activity(self.user_id)

        buckets = _bucketize(loops, calls, messages, resolver=resolver)

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
                open_loops_count=bucket.open_loops_count,
                calls_count=bucket.calls_count,
                peer_messages_count=bucket.peer_messages_count,
                last_interaction_at=bucket.last_interaction_at,
                is_favorite=key in favorites,
                is_peer=key in peer_keys,
            )
            for key, bucket in buckets.items()
        ]
        # Two stable passes rather than one reversed sort: names must read
        # A→Z inside a tie, and a single `reverse=True` would order them Z→A.
        # The tie is not hypothetical — every starred relationship with no live
        # signal ties on "no interaction ever".
        summaries.sort(key=lambda s: s.display_name.casefold())
        # Favorites first (they must also survive the cap), then most-recent
        # interaction, with "never" last.
        summaries.sort(
            key=lambda s: (
                s.is_favorite,
                s.last_interaction_at is not None,
                s.last_interaction_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        # The cap is STATED, not silently applied (ADR-185): the list is a page
        # like any section, and past it people would simply vanish.
        return RelationsOverview(
            relations=summaries[: settings.relations_max_items],
            relations_total=len(summaries),
        )

    async def build_detail(self, name: str) -> RelationDetail:
        """The 360° view of one relationship, resolved by normalized name.

        Every source is queried FOR THIS PERSON rather than paged and filtered
        in memory. Loops and calls are fetched by their exact stored spellings
        — resolved from the same aggregates the overview counts, so folding
        stays the sole business of ``fold_name`` and SQL never gets a second
        opinion on identity. Each section reports its exact total alongside
        the page, so a cap is stated rather than silently applied.
        """
        now = datetime.now(UTC)
        page = settings.relations_max_items_per_section

        async with get_db_context() as db:
            resolver = await self._load_identity_resolver(db)
            # Resolved AFTER the merges: opening the merged-away spelling must
            # land on the same card as the canonical one.
            target_key = resolver.key(name)
            loop_repo = OpenLoopRepository(db)
            call_repo = TelephonyRepository(db)
            loop_activity = await loop_repo.aggregate_open_by_counterparty(self.user_id)
            call_activity = await call_repo.aggregate_calls_by_callee(self.user_id)
            loop_names = _spellings_for(loop_activity, target_key, resolver=resolver)
            call_names = _spellings_for(call_activity, target_key, resolver=resolver)
            loops = await loop_repo.list_open_for_counterparties(self.user_id, loop_names, page)
            phone_calls = await call_repo.list_calls_for_callees(self.user_id, call_names, page)

            # Imported lazily: the tests of this service patch the repository
            # at its SOURCE module, which only a call-time import resolves.
            from src.domains.memories.repository import MemoryRepository

            memory_rows, memories_total = await MemoryRepository(db).list_mentioning_name(
                self.user_id, name, page
            )
            favorites = self._canonical_favorites(await self._load_favorites(db), resolver=resolver)
            merged_from = [
                row.alias_display_name
                for row in await RelationAliasRepository(db).list_for_user(self.user_id)
                if row.canonical_key == target_key
            ]
            peer_profiles = await self._load_peer_profiles(db)
            connected = self._profile_for(peer_profiles, target_key, resolver=resolver)
            peer_link = await self._load_peer_link(db, connected)

        # Own session, own failure boundary (peers spec §11) — see build_overview.
        # Page AND total from ONE read: asking twice would let a delivery land
        # between the calls and show a count the rows contradict.
        # Every spelling of the identity: the relayed-message rows of a
        # merged-away half are still stored under their own name.
        messages = await fetch_peer_messages_for(
            self.user_id,
            target_key=target_key,
            limit=page,
            merged_keys=resolver.keys_of(target_key),
        )

        # Every stored spelling is identity evidence — including the connected
        # peer's, which is the only one a brand-new connection has to offer.
        raw_names = set(loop_names) | set(call_names)
        raw_names |= {signal.peer_display_name for signal in messages.signals}
        if connected is not None:
            raw_names.add(connected.peer_display_name)

        return RelationDetail(
            display_name=self._display_name(raw_names) or name.strip(),
            identity_confidence=self._confidence(raw_names),
            open_loops=[_to_open_loop(loop, now) for loop in loops],
            open_loops_total=_total_for(loop_activity, target_key, resolver=resolver),
            recent_calls=[_to_call(call) for call in phone_calls],
            recent_calls_total=_total_for(call_activity, target_key, resolver=resolver),
            memories=[RelationMemory(id=str(row.id), content=row.content) for row in memory_rows],
            memories_total=memories_total,
            peer_messages=[_to_peer_message(signal) for signal in messages.signals],
            peer_messages_total=messages.total,
            peer_link=peer_link,
            is_favorite=target_key in favorites,
            is_peer=connected is not None,
            merged_from=merged_from,
        )

    async def _load_identity_resolver(self, db: AsyncSession) -> IdentityResolver:
        """Folding + the merges this user declared.

        One read per request, then passed down: a second place resolving
        aliases would make the list and the card disagree about who someone
        is, which is exactly what ADR-185 forbids.

        Args:
            db: Session owned by the caller.

        Returns:
            The resolver for this user (no merge = plain folding).
        """
        rows = await RelationAliasRepository(db).list_for_user(self.user_id)
        return IdentityResolver.from_pairs([(row.alias_key, row.canonical_key) for row in rows])

    @staticmethod
    def _canonical_favorites(
        favorites: dict[str, str], *, resolver: IdentityResolver
    ) -> dict[str, str]:
        """Re-key the stars onto canonical identities.

        A star set on either half must star the merged card. When BOTH halves
        were starred, the canonical spelling wins: it is what the card is
        called, so it is the spelling worth keeping.

        Args:
            favorites: Stored ``name_key -> display_name``.
            resolver: Folding + the user's merges.

        Returns:
            ``canonical_key -> display_name``.
        """
        canonical: dict[str, str] = {}
        for key, spelling in favorites.items():
            target = resolver.canonical(key)
            if target == key or target not in canonical:
                canonical[target] = spelling
        return canonical

    async def _load_favorites(self, db: AsyncSession) -> dict[str, str]:
        """The user's stars, as ``name_key -> starred spelling``."""
        rows = await RelationFavoriteRepository(db).list_for_user(self.user_id)
        return {row.name_key: row.display_name for row in rows}

    async def _load_peer_profiles(self, db: AsyncSession) -> list[PeerConnectionProfile]:
        """Accepted LIA connections (empty when the flag is off).

        ONE read serves both the badge and the connection block — reading the
        peers domain twice for the same page would invite the two answers to
        disagree.
        """
        if not settings.peers_enabled:
            return []
        return await PeersRepository(db).list_accepted_peer_profiles(self.user_id)

    @staticmethod
    def _peer_keys(
        profiles: list[PeerConnectionProfile], *, resolver: IdentityResolver = NO_MERGES
    ) -> set[str]:
        """Identity keys of connected peers, blanks dropped.

        Resolved through the merges so the badge follows the card: a peer
        merged with another spelling is still a peer. This is a DISPLAY
        resolution only — message routing never reads the alias table.

        Args:
            profiles: Accepted connections.
            resolver: Folding + the user's merges.

        Returns:
            Canonical keys of the connected peers.
        """
        return {key for profile in profiles if (key := resolver.key(profile.peer_display_name))}

    @staticmethod
    def _profile_for(
        profiles: list[PeerConnectionProfile],
        target_key: str,
        *,
        resolver: IdentityResolver = NO_MERGES,
    ) -> PeerConnectionProfile | None:
        """The accepted connection behind one relationship, if there is one.

        Args:
            profiles: Accepted connections.
            target_key: Canonical identity key of the relationship.
            resolver: Folding + the user's merges.

        Returns:
            The matching profile, or None.
        """
        return next((p for p in profiles if resolver.key(p.peer_display_name) == target_key), None)

    async def _load_peer_link(
        self, db: AsyncSession, profile: PeerConnectionProfile | None
    ) -> RelationPeerLink | None:
        """The connection block for one relationship, or None if not connected.

        Both share directions are read from the pair row, so the panel states
        the arrangement as it is rather than only the half the user set up.
        """
        if profile is None:
            return None
        shares = await PeersRepository(db).list_shares(profile.connection_id)
        return RelationPeerLink(
            connected_since=profile.connected_since,
            shared_by_me=[
                RelationShare(domain=s.domain, level=s.level)
                for s in shares
                if s.owner_user_id == self.user_id
            ],
            shared_with_me=[
                RelationShare(domain=s.domain, level=s.level)
                for s in shares
                if s.owner_user_id == profile.peer_id
            ],
        )

    async def merge_relations(self, *, source: str, target: str) -> str:
        """Declare that two relationships are the SAME person.

        ``fold_name`` decides who is literally the same spelling; it cannot
        know that a raw phone number and a name are one person. Only the user
        can say that, so this is manual and never proposed.

        Nothing is rewritten in the sources — the CRM is a view over them — so
        the merge is one row and undoing it is deleting that row.

        Two properties worth stating:

        - **idempotent**: merging twice writes nothing the second time, so a
          double-click cannot create a second identity;
        - **no cycle can be written**: the target is resolved to its canonical
          FIRST, so merging B into A when A already belongs to B ends on
          "source == target" and does nothing. That is why reads need no cycle
          detection.

        Args:
            source: Relationship being merged away, as displayed.
            target: Relationship it joins, as displayed.

        Returns:
            The canonical identity key both now share.

        Raises:
            ValueError: When either side is blank, or both fold to the same
                identity (there would be nothing to merge).
        """
        source_display = source.strip()
        source_key = _normalize_name(source_display)
        target_key = _normalize_name(target)
        if not source_key or not target_key:
            raise ValueError("both sides of a merge need a name")
        # ONE card picked twice — the UI should not offer it, and merging a
        # relationship with itself has no meaning.
        if source_key == target_key:
            raise ValueError("source and target are the same relationship")

        async with get_db_context() as db:
            repo = RelationAliasRepository(db)
            resolver = await self._load_identity_resolver(db)
            canonical = resolver.canonical(target_key)
            # Two DIFFERENT cards that already form one identity: nothing to
            # write. Not an error — the user is asking for a state that holds.
            # This is also what makes a cycle impossible: merging back the
            # other way lands here instead of writing B→A over A→B.
            if resolver.canonical(source_key) == canonical:
                return canonical
            await repo.merge(
                self.user_id,
                alias_key=source_key,
                canonical_key=canonical,
                alias_display_name=source_display,
            )
        # No PII at INFO: that a merge happened, never who with whom.
        logger.info("relation_merged", user_id=str(self.user_id))
        return canonical

    async def split_relation(self, name: str) -> bool:
        """Undo one merge — the merged-away side becomes its own card again.

        Args:
            name: Relationship to split back out, as displayed.

        Returns:
            True when a merge existed and was undone.

        Raises:
            ValueError: When the name is blank.
        """
        key = _normalize_name(name)
        if not key:
            raise ValueError("a name is required to split a merge")
        async with get_db_context() as db:
            undone = await RelationAliasRepository(db).split(self.user_id, alias_key=key)
        logger.info("relation_split", user_id=str(self.user_id), undone=undone)
        return undone

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
