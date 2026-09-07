"""Orchestration of the three provider-backed sections (Bloc C).

Shape borrowed from ``briefing``, the domain that already solved this problem:
one fetcher per source, each with its own session and its own failure boundary,
a per-section Redis cache whose TTL matches the source's natural change rate,
and an exception taxonomy lifted into a per-section status. Reasons to imitate
rather than extend it: briefing answers "what does today look like?" for one
user, this answers "what do I have with this person?" — different cache keys,
different lifetimes, and no LLM anywhere.

Two things are NOT copied, deliberately:

- **no stale-while-error.** A dated payload next to an error is honest for a
  daily briefing you skim; on a relationship card it would show mail that may
  no longer exist under a person's name, which is worse than a stated gap.
- **no counts.** Everything here comes from a provider page, and ADR-185
  forbids a count that is not exact.

Order matters: the contact card resolves the ADDRESSES the other two sections
query, so it is fetched first and the other two then run concurrently — each on
its own session (``open_category_client`` opens one), which is what makes the
concurrency safe.

The card is not the ONLY address source (ADR-191): a CONNECTED peer who is
absent from the address book contributes their own, and only when they opted
into sharing it. Without that, someone the user talks to through this very
product had no address at all, so mail and meetings came back unreadable. See
:meth:`RelationContextService._match_addresses`.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    RELATIONS_PROVIDER_CACHE_PREFIX,
    RELATIONS_PROVIDER_CONTACT_TTL_SECONDS,
    RELATIONS_PROVIDER_EMAILS_TTL_SECONDS,
    RELATIONS_PROVIDER_EVENTS_TTL_SECONDS,
)
from src.domains.relations.providers.client import ProviderNotConfigured
from src.domains.relations.providers.contacts import fetch_contact_card
from src.domains.relations.providers.emails import fetch_exchanged_emails
from src.domains.relations.providers.events import fetch_shared_events
from src.domains.relations.providers.schemas import (
    ContextSection,
    ContextStatus,
    RelationContext,
)
from src.domains.shared.text_normalization import fold_email, fold_name
from src.infrastructure.cache.redis import get_redis_cache

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

_SECTION_CONTACT = "contact"
_SECTION_EMAILS = "emails"
_SECTION_EVENTS = "events"

#: What ``build`` fetches when the caller names no subset — the HTTP route's
#: case, and the historical behaviour.
_ALL_SECTIONS = frozenset({_SECTION_CONTACT, _SECTION_EMAILS, _SECTION_EVENTS})

#: The two sections queried BY ADDRESS. They share every step the contact card
#: does not: the address resolution, the no-address answer, and the concurrency.
_EXCHANGE_SECTIONS = frozenset({_SECTION_EMAILS, _SECTION_EVENTS})


def _now() -> datetime:
    return datetime.now(UTC)


def _off(status: ContextStatus) -> ContextSection:
    """A section that carries no payload, only why."""
    return ContextSection(status=status, generated_at=_now())


def _uniform(status: ContextStatus) -> RelationContext:
    """A context whose three sections share one outcome, with no payload."""
    section = _off(status)
    return RelationContext(contact=section, emails=section, events=section)


async def _ready(section: ContextSection) -> ContextSection:
    """Keep the ``gather`` shape for a section nobody asked for.

    An already-built value rather than a fetch: a section the caller excluded
    must cost no call.
    """
    return section


class RelationContextService:
    """Builds the provider-backed half of one relationship's 360° view."""

    def __init__(self, user_id: UUID) -> None:
        """Bind the owner (the service holds no session — fetchers own theirs)."""
        self.user_id = user_id

    async def build(
        self,
        name: str,
        *,
        refresh: frozenset[str] | None = None,
        sections: frozenset[str] | None = None,
    ) -> RelationContext:
        """The three sections for one relationship.

        Args:
            name: The relationship as the CRM displays it.
            refresh: Sections whose cache must be bypassed. The contact card
                lives up to six hours, so a correction made in the address book
                would otherwise stay invisible for half a day — the reader gets
                a way to say "look again", per section or for all three.
            sections: Sections to actually fetch; None means all three (what
                the HTTP route asks for). A section left out comes back
                ``NOT_REQUESTED`` and costs NOTHING — one mail section is three
                searches per address, so fetching what the caller already
                decided to drop is quota spent against the reader's own
                selection (ADR-184, pointing at cost).

                The contact card is the one exception, and only as an INPUT:
                it is read whenever mail or meetings are wanted, because it is
                what resolves the addresses they are queried by. It is still
                only REPORTED when the caller asked for it.

        Returns:
            One section each for the contact card, the mail exchanged and the
            meetings shared, plus the scope those answers rest on.
        """
        wanted = sections if sections is not None else _ALL_SECTIONS
        target_key = fold_name(name)
        if not settings.relations_provider_sections_enabled or not target_key:
            # The flag off is not a failure and not an empty result: the
            # question is never asked, so no section may claim an answer.
            return _uniform(ContextStatus.NOT_CONFIGURED)
        if not wanted:
            return _uniform(ContextStatus.NOT_REQUESTED)
        return await self._build_wanted(name, target_key, refresh or frozenset(), wanted)

    async def _build_wanted(
        self, name: str, target_key: str, forced: frozenset[str], wanted: frozenset[str]
    ) -> RelationContext:
        """The sections the caller asked for, in the order their inputs allow.

        The contact card comes first because it RESOLVES the addresses mail and
        meetings are queried by — so it is read whenever either of them is
        wanted, and only REPORTED when it was asked for.

        Args:
            name: The relationship as the CRM displays it.
            target_key: Its folded identity.
            forced: Sections whose cache must be bypassed.
            wanted: Sections to fetch (non-empty).

        Returns:
            The assembled context.
        """
        contact = await self._section(
            _SECTION_CONTACT,
            target_key,
            RELATIONS_PROVIDER_CONTACT_TTL_SECONDS,
            lambda: self._fetch_contact(target_key, name),
            forced=_SECTION_CONTACT in forced,
        )
        reported = contact if _SECTION_CONTACT in wanted else _off(ContextStatus.NOT_REQUESTED)
        if not wanted & _EXCHANGE_SECTIONS:
            return self._assembled(reported, ContextStatus.NOT_REQUESTED, wanted)

        addresses = await self._match_addresses(contact, target_key)
        if not addresses:
            # NOT "nothing found": mail and calendar are queried by address, so
            # without one the question was never asked (ADR-184 doctrine — a
            # negative you did not verify is not a result).
            return self._assembled(reported, ContextStatus.NO_ADDRESS, wanted)

        emails, events = await self._fetch_exchanges(target_key, forced, wanted, addresses)
        return RelationContext(
            contact=reported,
            emails=emails,
            events=events,
            addresses_used=len(addresses),
            window_days=settings.relations_provider_window_days,
            email_window_days=settings.relations_provider_email_window_days,
        )

    async def _fetch_exchanges(
        self,
        target_key: str,
        forced: frozenset[str],
        wanted: frozenset[str],
        addresses: list[str],
    ) -> tuple[ContextSection, ContextSection]:
        """Mail and meetings, concurrently — and only the ones asked for.

        The excluded one resolves to an already-built section rather than a
        second code path: the concurrency is what makes the two paid sections
        overlap, and reshaping it per subset would be two ways to do one thing.

        Args:
            target_key: Folded identity, part of the cache key.
            forced: Sections whose cache must be bypassed.
            wanted: Sections to fetch.
            addresses: Mailboxes to query by — also part of the cache key.

        Returns:
            The mail section and the meetings section.
        """
        skipped = _off(ContextStatus.NOT_REQUESTED)
        emails, events = await asyncio.gather(
            (
                self._section(
                    _SECTION_EMAILS,
                    target_key,
                    RELATIONS_PROVIDER_EMAILS_TTL_SECONDS,
                    lambda: self._fetch_emails(addresses),
                    forced=_SECTION_EMAILS in forced,
                    inputs=addresses,
                )
                if _SECTION_EMAILS in wanted
                else _ready(skipped)
            ),
            (
                self._section(
                    _SECTION_EVENTS,
                    target_key,
                    RELATIONS_PROVIDER_EVENTS_TTL_SECONDS,
                    lambda: self._fetch_events(addresses),
                    forced=_SECTION_EVENTS in forced,
                    inputs=addresses,
                )
                if _SECTION_EVENTS in wanted
                else _ready(skipped)
            ),
        )
        return emails, events

    @staticmethod
    def _assembled(
        contact: ContextSection, exchange_status: ContextStatus, wanted: frozenset[str]
    ) -> RelationContext:
        """A context whose two exchange sections share one outcome.

        Args:
            contact: The contact section, already decided.
            exchange_status: What mail and meetings both answer.
            wanted: Sections the caller asked for — an excluded one stays
                ``NOT_REQUESTED`` whatever the others report.

        Returns:
            The assembled context.
        """
        outcome = _off(exchange_status)
        skipped = _off(ContextStatus.NOT_REQUESTED)
        return RelationContext(
            contact=contact,
            emails=outcome if _SECTION_EMAILS in wanted else skipped,
            events=outcome if _SECTION_EVENTS in wanted else skipped,
            window_days=settings.relations_provider_window_days,
            email_window_days=settings.relations_provider_email_window_days,
        )

    # ------------------------------------------------------------------
    # Fetchers — each maps its source onto a section payload
    # ------------------------------------------------------------------

    async def _fetch_contact(self, target_key: str, name: str) -> ContextSection:
        card = await fetch_contact_card(self.user_id, target_key=target_key, search_name=name)
        if card is None:
            return _off(ContextStatus.EMPTY)
        return ContextSection(status=ContextStatus.OK, generated_at=_now(), contact=card)

    async def _fetch_emails(self, addresses: list[str]) -> ContextSection:
        found = await fetch_exchanged_emails(
            self.user_id,
            addresses=addresses,
            limit=settings.relations_provider_max_items,
            window_days=settings.relations_provider_email_window_days,
            now=_now(),
        )
        if not found:
            return _off(ContextStatus.EMPTY)
        return ContextSection(status=ContextStatus.OK, generated_at=_now(), emails=found)

    async def _fetch_events(self, addresses: list[str]) -> ContextSection:
        found = await fetch_shared_events(
            self.user_id,
            addresses=addresses,
            limit=settings.relations_provider_max_items,
            window_days=settings.relations_provider_window_days,
            now=_now(),
        )
        if not found:
            return _off(ContextStatus.EMPTY)
        return ContextSection(status=ContextStatus.OK, generated_at=_now(), events=found)

    # ------------------------------------------------------------------
    # Cache + status mapping
    # ------------------------------------------------------------------

    def _addresses_of(self, contact: ContextSection) -> list[str]:
        """The card's addresses, folded and deduplicated — NOT yet capped.

        Folding before capping is what makes each slot buy a DISTINCT mailbox.
        Capping first spent two of three slots on ``Jean@x.com`` +
        ``jean@x.com`` — six mail searches for one mailbox — and evicted a
        third address that might have held real correspondence.

        The stored spelling is what goes to the provider: folding decides
        IDENTITY, it never rewrites the query.

        Args:
            contact: The contact-card section, however it came back.

        Returns:
            Addresses in card order, one per mailbox.
        """
        if contact.contact is None:
            return []
        seen: set[str] = set()
        unique: list[str] = []
        for email in contact.contact.emails:
            key = fold_email(email.value)
            if key and key not in seen:
                seen.add(key)
                unique.append(email.value)
        return unique

    async def _match_addresses(self, contact: ContextSection, target_key: str) -> list[str]:
        """Address-book addresses, plus a connected peer's own when they shared it.

        A connected user who is NOT in the address book had no address at all,
        so mail and meetings were reported unreadable for someone the user
        talks to through this very product (measured 2026-08-01: a peer's 360°
        came back with ``events`` unavailable while the two shared a calendar).

        The peer's address is used ONLY when they opted into
        ``peer_email_visible`` — their consent, carried by
        ``PeerConnectionProfile.peer_email``, is what makes it available. It
        then serves to match attendees and correspondents in the USER'S OWN
        mail and calendar, which they can already read: no third-party data is
        reached, and the address is never echoed back into the payload.

        This deliberately revises ADR-189's clause "the opt-in does not feed
        the CRM's provider sections" (ADR-191): that clause protected against
        the address becoming a source by SIDE EFFECT, bypassing the setting.
        Here the setting is read, and it alone decides.

        The peer's address is GUARANTEED a slot, because it is the one address
        the user is certain about: the two are connected through this very
        product and the peer opted in. Two ways it used to be lost, both from
        comparing against an already-capped list:

        - absent from the card and the card full → the append was truncated
          away;
        - present on the card but PAST the cap → the fold could not even see
          it, so it was dropped like any overflow address.

        It is now reserved a slot when absent, and promoted when present. This
        revises ADR-191's "APPENDED, never prepended": that clause protected a
        card address from being evicted by an OUTSIDE address, which still
        holds — nothing is added that was not going to be queried. When the
        address is already the card's own, promoting it evicts nothing the cap
        was not evicting anyway; it only changes WHICH address loses the seat,
        in favour of the one identity the user confirmed.

        Args:
            contact: The contact-card section, however it came back.
            target_key: Folded relationship name — the identity key.

        Returns:
            Addresses to query by, one per mailbox, capped.
        """
        addresses = self._addresses_of(contact)
        cap = settings.relations_provider_max_addresses
        peer_address = await self._peer_address(target_key)
        if not peer_address:
            return addresses[:cap]

        peer_key = fold_email(peer_address)
        if peer_key in {fold_email(address) for address in addresses}:
            promoted = [a for a in addresses if fold_email(a) == peer_key]
            others = [a for a in addresses if fold_email(a) != peer_key]
            return [*promoted, *others][:cap]
        return [*addresses[: cap - 1], peer_address]

    async def _peer_address(self, target_key: str) -> str | None:
        """The connected peer's address for this relationship, if they shared it.

        Own session, like every other fetcher here — the service holds none.
        Resolution goes through the SAME fold as the rest of the CRM
        (``fold_name``): a second notion of "who is this person" is how two
        answers about one relationship start to disagree.

        Args:
            target_key: Folded relationship name.

        Returns:
            The address, or None when there is no connection, the peer did not
            opt in, or the peers feature is off.
        """
        if not settings.peers_enabled:
            return None
        # Imported lazily: the tests patch these at their SOURCE modules.
        from src.domains.peers.repository import PeersRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                profiles = await PeersRepository(db).list_accepted_peer_profiles(self.user_id)
        except Exception as exc:
            # Own failure boundary, like the peers bridge in RelationsService:
            # the CRM answers without the peer address rather than not at all.
            # The TYPE, never the message: a SQLAlchemy error stringifies its
            # statement and bound parameters, which here are names and email
            # addresses. Same form as every other handler in this domain.
            logger.warning("relations_peer_address_lookup_failed", error_type=type(exc).__name__)
            return None
        match = next(
            (p for p in profiles if fold_name(p.peer_display_name) == target_key),
            None,
        )
        return match.peer_email if match else None

    def _cache_key(self, section: str, target_key: str, inputs: list[str] | None = None) -> str:
        """Key one section of one relationship, by everything it was built FROM.

        The relationship key is hashed: it is a display name, so it carries
        spaces, colons and whatever else a person is called — none of which
        belongs raw in a Redis key.

        For mail and meetings the ADDRESSES join the key, and that is not
        decoration: the contact card is the identity those two are queried
        with, so a corrected address book would otherwise keep serving mail
        computed from the OLD identity under the NEW card — stale in the one
        way the reader cannot see. Keying on the inputs makes a changed
        identity a cache MISS by construction, rather than a cascade every
        caller must remember to trigger; an UNCHANGED card still hits.
        """
        material = target_key if inputs is None else "\n".join([target_key, *inputs])
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return f"{RELATIONS_PROVIDER_CACHE_PREFIX}:{self.user_id}:{digest}:{section}"

    async def _section(
        self,
        name: str,
        target_key: str,
        ttl: int,
        fetcher: Callable[[], Awaitable[ContextSection]],
        *,
        forced: bool = False,
        inputs: list[str] | None = None,
    ) -> ContextSection:
        """Serve one section from cache or live. **Never raises.**"""
        key = self._cache_key(name, target_key, inputs)
        if not forced and (cached := await self._read_cache(key)) is not None:
            return cached.model_copy(update={"from_cache": True})

        try:
            section = await fetcher()
        except ProviderNotConfigured:
            # Nothing broken: the user has not plugged that provider in.
            section = _off(ContextStatus.NOT_CONFIGURED)
        except Exception as exc:  # noqa: BLE001 — one section never sinks the page
            logger.info(
                "relations_context_section_failed",
                user_id=str(self.user_id),
                section=name,
                error_type=type(exc).__name__,
            )
            return _off(ContextStatus.ERROR)  # errors retry next request, never cached

        await self._write_cache(key, section, ttl)
        return section

    async def _read_cache(self, key: str) -> ContextSection | None:
        """Read a cached section; any cache trouble degrades to a live fetch."""
        try:
            raw = await (await get_redis_cache()).get(key)
            if not raw:
                return None
            return ContextSection.model_validate_json(raw)
        except Exception as exc:  # noqa: BLE001 — a stale shape must not 500
            logger.debug("relations_context_cache_read_failed", error_type=type(exc).__name__)
            return None

    async def _write_cache(self, key: str, section: ContextSection, ttl: int) -> None:
        """Persist a section; a cache write never fails a served answer."""
        try:
            await (await get_redis_cache()).set(key, section.model_dump_json(), ex=ttl)
        except Exception as exc:  # noqa: BLE001 — best-effort by contract
            logger.debug("relations_context_cache_write_failed", error_type=type(exc).__name__)
