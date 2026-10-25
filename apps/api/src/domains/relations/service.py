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

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.peers.repository import PeersRepository
from src.domains.peers.schemas import PeerConnectionProfile
from src.domains.relations.activity import _Bucket
from src.domains.relations.activity import _bucketize as _bucketize
from src.domains.relations.identity import NO_MERGES, IdentityResolver, RelationIdentity
from src.domains.relations.identity_scope import RelationScope, relation_scope
from src.domains.relations.mappers import to_call, to_open_loop, to_peer_message
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.peer_messages import (
    fetch_peer_message_activity,
    fetch_peer_messages_for,
)
from src.domains.relations.preference_commands import (
    RelationPreferencePatch,
    lock_relation_owner,
    update_relation_preferences,
)
from src.domains.relations.repository import (
    RelationAliasRepository,
    RelationFavoriteRepository,
)
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationDetail,
    RelationMemory,
    RelationPeerLink,
    RelationShare,
    RelationsOverview,
    RelationSummary,
)
from src.domains.shared.relation_sms import RelationSmsPage, read_relation_sms
from src.domains.shared.text_normalization import fold_name
from src.domains.telephony.repository import TelephonyRepository
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.relations.models import RelationAlias

logger = structlog.get_logger(__name__)


def _normalize_name(name: str) -> str:
    """Accent- and case-fold a display name into a grouping key.

    Delegates to the shared folding chokepoint (``shared/text_normalization``,
    hoisted for the peers discovery search) — behavior unchanged: empty or
    whitespace-only names fold to '' and are dropped by the caller.
    """
    return fold_name(name)


@dataclass(frozen=True)
class _Identities:
    """What the relationship list is built from, read once.

    Attributes:
        buckets: Canonical key -> the aggregated signals and raw spellings.
        favorites: Canonical key -> starred spelling.
        peer_keys: Canonical keys of the connected users.
        sms_available: Whether the SMS archive answered.
        merged_spellings: Canonical key -> the spellings merged into it, as
            the person declared them (a declaration outlives its records).
    """

    buckets: dict[str, _Bucket]
    favorites: dict[str, str]
    peer_keys: set[str]
    sms_available: bool
    merged_spellings: dict[str, set[str]]


async def _detail_sms(
    owner_id: UUID, name: str, limit: int, *, include_sms: bool, assistant: bool
) -> RelationSmsPage:
    if not include_sms:
        return RelationSmsPage()
    return await read_relation_sms(
        owner_id, person=name, limit=min(limit, 3) if assistant else limit, assistant=assistant
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
            await update_relation_preferences(
                db, self.user_id, RelationPreferencePatch(relation_overview_scope=scope)
            )
        logger.info(
            "relations_overview_scope_saved",
            user_id=str(self.user_id),
            sections=len(scope.sections),
            max_items=scope.max_items,
        )

    async def set_debrief_enabled(self, enabled: bool) -> bool:
        """Turn the daily debrief on or off for this account.

        Args:
            enabled: What the reader asked for.

        Returns:
            The acknowledged stored value. An inactive or vanished account refuses.
        """
        async with get_db_context() as db:
            await update_relation_preferences(
                db, self.user_id, RelationPreferencePatch(relation_debrief_enabled=enabled)
            )
        logger.info("relation_debrief_preference_set", user_id=str(self.user_id), enabled=enabled)
        return enabled

    async def build_overview(self) -> RelationsOverview:
        """Rank relationships by most-recent interaction, with EXACT counts.

        Every source answers by aggregate, not by page: the counts a card
        shows are claims, and the previous implementation derived them from a
        capped window of rows — so a busy user's card silently under-reported
        and a person whose only activity fell outside the window had no card
        at all.
        """
        identities = await self._identities(sms_assistant=False)
        buckets, favorites, peer_keys = (
            identities.buckets,
            identities.favorites,
            identities.peer_keys,
        )
        summaries = [
            RelationSummary(
                display_name=self._display_name(bucket.raw_names),
                identity_confidence=self._confidence(bucket.raw_names),
                open_loops_count=bucket.open_loops_count,
                calls_count=bucket.calls_count,
                peer_messages_count=bucket.peer_messages_count,
                sms_count=bucket.sms_count,
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
        # `debrief_enabled` is filled by the router, which already holds the
        # authenticated user: reading the row again here would add a query to a
        # pure aggregation for a value its caller has in hand.
        return RelationsOverview(
            relations=summaries[: settings.relations_max_items],
            sms_available=identities.sms_available,
            relations_total=len(summaries),
        )

    async def directory(self) -> list[RelationIdentity]:
        """Everyone the relationship list knows, with every spelling naming them.

        Built from the very identities the list is (``_identities``), so a name
        resolved in the chat and a card on the page can never disagree about
        who someone is (ADR-185). No count is computed: a resolver needs who,
        not how much. Its readers are the assistant's tools, whose candidates
        reach the model: an SMS sender joins it only where the person let the
        assistant read their SMS.

        Returns:
            One entry per identity, connected or not.
        """
        identities = await self._identities(sms_assistant=True)
        return [
            RelationIdentity(
                key=key,
                display_name=self._display_name(bucket.raw_names),
                spellings=tuple(
                    sorted(bucket.raw_names | identities.merged_spellings.get(key, set()))
                ),
                is_peer=key in identities.peer_keys,
            )
            for key, bucket in identities.buckets.items()
            if bucket.raw_names
        ]

    async def _identities(self, *, sms_assistant: bool) -> _Identities:
        """Every identity the sources name, the starred ones included.

        Args:
            sms_assistant: Whether the reader is the assistant, whose SMS reads
                require the person's consent — no default: the page and the
                assistant are two different readers of the same archive.

        Returns:
            The buckets, the stars, the connected identities and whether SMS
            are available — one read serving the list and the directory.
        """
        async with get_db_context() as db:
            loops = await OpenLoopRepository(db).aggregate_open_by_counterparty(self.user_id)
            calls = await TelephonyRepository(db).aggregate_calls_by_callee(self.user_id)
            aliases = await RelationAliasRepository(db).list_for_user(self.user_id)
            resolver = self._resolver_from(aliases)
            favorites = self._canonical_favorites(await self._load_favorites(db), resolver=resolver)
            peer_keys = self._peer_keys(await self._load_peer_profiles(db), resolver=resolver)
        merged_spellings: dict[str, set[str]] = {}
        for row in aliases:
            merged_spellings.setdefault(row.canonical_key, set()).add(row.alias_display_name)

        # Own session, own failure boundary (peers spec §11) — deliberately
        # OUTSIDE the block above, so a failed statement there could never
        # poison the transaction the rest of the CRM runs on.
        messages = await fetch_peer_message_activity(self.user_id)

        sms = await read_relation_sms(self.user_id, assistant=sms_assistant)
        buckets = _bucketize(loops, calls, messages, resolver=resolver, sms=sms.activities)

        # A starred name without any live signal still deserves its card:
        # inject an empty bucket carrying the spelling the user starred.
        for key, spelling in favorites.items():
            if key not in buckets:
                empty = buckets.setdefault(key, _Bucket())
                empty.raw_names.add(spelling)
        return _Identities(buckets, favorites, peer_keys, sms.available, merged_spellings)

    async def build_detail(
        self, name: str, *, include_sms: bool = True, sms_assistant: bool = False
    ) -> RelationDetail:
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
            scope, resolver = await self.scope(db, name)
            target_key, loop_names, call_names = (
                scope.target_key,
                scope.loop_names,
                scope.call_names,
            )
            loops = await OpenLoopRepository(db).list_open_for_counterparties(
                self.user_id, loop_names, page
            )
            phone_calls = await TelephonyRepository(db).list_calls_for_callees(
                self.user_id, call_names, page
            )

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
            self.user_id, target_key=target_key, limit=page, merged_keys=scope.identity_keys
        )

        # Every stored spelling is identity evidence — including the connected
        # peer's, which is the only one a brand-new connection has to offer.
        raw_names = set(loop_names) | set(call_names)
        raw_names |= {signal.peer_display_name for signal in messages.signals}
        if connected is not None:
            raw_names.add(connected.peer_display_name)

        sms = await _detail_sms(
            self.user_id, name, page, include_sms=include_sms, assistant=sms_assistant
        )
        raw_names |= {
            item.raw_name for item in sms.activities if resolver.key(item.raw_name) == target_key
        }
        return RelationDetail(
            display_name=self._display_name(raw_names) or name.strip(),
            identity_confidence=self._confidence(raw_names),
            open_loops=[to_open_loop(loop, now) for loop in loops],
            open_loops_total=scope.loops_total,
            recent_calls=[to_call(call) for call in phone_calls],
            recent_calls_total=scope.calls_total,
            memories=[
                RelationMemory(id=str(row.id), content=row.content, created_at=row.created_at)
                for row in memory_rows
            ],
            memories_total=memories_total,
            peer_messages=[to_peer_message(signal) for signal in messages.signals],
            peer_messages_total=messages.total,
            sms=sms.messages,
            sms_total=sms.total,
            sms_available=sms.available,
            sms_proof=sms.proof,
            peer_link=peer_link,
            is_favorite=target_key in favorites,
            is_peer=connected is not None,
            merged_from=merged_from,
        )

    async def scope(self, db: AsyncSession, name: str) -> tuple[RelationScope, IdentityResolver]:
        """Who ``name`` designates, as each source stores them — the card's and the timeline's.

        Resolved AFTER the merges: opening the merged-away spelling lands on the
        same card as the canonical one (``identity_scope``).

        Args:
            db: Session owned by the caller.
            name: The name the card was opened with.

        Returns:
            The scope, and the resolver it was built with.
        """
        resolver = await self._load_identity_resolver(db)
        loop_activity = await OpenLoopRepository(db).aggregate_open_by_counterparty(self.user_id)
        call_activity = await TelephonyRepository(db).aggregate_calls_by_callee(self.user_id)
        return relation_scope(resolver, name, loop_activity, call_activity), resolver

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
        return self._resolver_from(await RelationAliasRepository(db).list_for_user(self.user_id))

    @staticmethod
    def _resolver_from(rows: Sequence[RelationAlias]) -> IdentityResolver:
        """The resolver the stored merges describe — one construction for every read."""
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
        async with get_db_context() as db:
            canonical = await self.merge_in_session(db, source=source, target=target)
        logger.info("relation_merged", user_id=str(self.user_id))
        return canonical

    async def merge_in_session(self, db: AsyncSession, *, source: str, target: str) -> str:
        """Apply the source merge within the caller-owned transaction; do not commit."""
        source_display = source.strip()
        source_key = _normalize_name(source_display)
        target_key = _normalize_name(target)
        if not source_key or not target_key:
            raise ValueError("both sides of a merge need a name")
        # ONE card picked twice — the UI should not offer it, and merging a
        # relationship with itself has no meaning.
        if source_key == target_key:
            raise ValueError("source and target are the same relationship")

        repo = RelationAliasRepository(db)
        await lock_relation_owner(db, self.user_id)
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
        # Both halves' debriefs describe an identity that no longer exists
        # as such. Deleting is the only honest repair — the next card open
        # writes one for the identity that DOES exist. Same transaction as
        # the merge: a debrief surviving a committed merge would describe
        # the wrong person until somebody noticed.
        await self._forget_debriefs(
            db, list(dict.fromkeys([source_key, resolver.canonical(source_key), canonical]))
        )
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
        async with get_db_context() as db:
            undone = await self.split_in_session(db, name)
        logger.info("relation_split", user_id=str(self.user_id), undone=undone)
        return undone

    async def split_in_session(self, db: AsyncSession, name: str) -> bool:
        """Apply the source split within the caller-owned transaction; do not commit."""
        key = _normalize_name(name)
        if not key:
            raise ValueError("a name is required to split a merge")
        await lock_relation_owner(db, self.user_id)
        resolver = await self._load_identity_resolver(db)
        # Read BEFORE the split: afterwards the alias resolves to itself
        # and the canonical card's debrief would keep the merged content.
        canonical = resolver.canonical(key)
        undone = await RelationAliasRepository(db).split(self.user_id, alias_key=key)
        if undone:
            await self._forget_debriefs(db, [key, canonical])
        return undone

    async def _forget_debriefs(self, db: AsyncSession, keys: list[str]) -> None:
        """Drop the debriefs of identities a merge or a split just rewrote.

        Imported at call time: ``relations.debrief`` reads this very service to
        assemble its evidence, so a module-level import would close a cycle
        inside the domain. The edge is one function deep and named here.

        Args:
            db: The session the merge/split runs in — same transaction.
            keys: Canonical keys whose stored debrief is now about nobody.
        """
        from src.domains.relations.debrief.repository import RelationDebriefRepository

        await RelationDebriefRepository(db).delete_for_keys(self.user_id, keys)

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
            await lock_relation_owner(db, self.user_id)
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
            await lock_relation_owner(db, self.user_id)
            resolver = await self._load_identity_resolver(db)
            removed = await RelationFavoriteRepository(db).remove_identity(
                self.user_id, canonical_key=resolver.canonical(key)
            )
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
