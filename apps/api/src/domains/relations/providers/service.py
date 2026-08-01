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


def _now() -> datetime:
    return datetime.now(UTC)


def _off(status: ContextStatus) -> ContextSection:
    """A section that carries no payload, only why."""
    return ContextSection(status=status, generated_at=_now())


class RelationContextService:
    """Builds the provider-backed half of one relationship's 360° view."""

    def __init__(self, user_id: UUID) -> None:
        """Bind the owner (the service holds no session — fetchers own theirs)."""
        self.user_id = user_id

    async def build(self, name: str, *, refresh: frozenset[str] | None = None) -> RelationContext:
        """The three sections for one relationship.

        Args:
            name: The relationship as the CRM displays it.
            refresh: Sections whose cache must be bypassed. The contact card
                lives up to six hours, so a correction made in the address book
                would otherwise stay invisible for half a day — the reader gets
                a way to say "look again", per section or for all three.

        Returns:
            One section each for the contact card, the mail exchanged and the
            meetings shared, plus the scope those answers rest on.
        """
        target_key = fold_name(name)
        forced = refresh or frozenset()
        if not settings.relations_provider_sections_enabled or not target_key:
            # The flag off is not a failure and not an empty result: the
            # question is never asked, so no section may claim an answer.
            blank = _off(ContextStatus.NOT_CONFIGURED)
            return RelationContext(contact=blank, emails=blank, events=blank)

        contact = await self._section(
            _SECTION_CONTACT,
            target_key,
            RELATIONS_PROVIDER_CONTACT_TTL_SECONDS,
            lambda: self._fetch_contact(target_key, name),
            forced=_SECTION_CONTACT in forced,
        )
        addresses = await self._match_addresses(contact, target_key)
        if not addresses:
            # NOT "nothing found": mail and calendar are queried by address, so
            # without one the question was never asked (ADR-184 doctrine — a
            # negative you did not verify is not a result).
            no_address = _off(ContextStatus.NO_ADDRESS)
            return RelationContext(
                contact=contact,
                emails=no_address,
                events=no_address,
                window_days=settings.relations_provider_window_days,
                email_window_days=settings.relations_provider_email_window_days,
            )

        emails, events = await asyncio.gather(
            self._section(
                _SECTION_EMAILS,
                target_key,
                RELATIONS_PROVIDER_EMAILS_TTL_SECONDS,
                lambda: self._fetch_emails(addresses),
                forced=_SECTION_EMAILS in forced,
                inputs=addresses,
            ),
            self._section(
                _SECTION_EVENTS,
                target_key,
                RELATIONS_PROVIDER_EVENTS_TTL_SECONDS,
                lambda: self._fetch_events(addresses),
                forced=_SECTION_EVENTS in forced,
                inputs=addresses,
            ),
        )
        return RelationContext(
            contact=contact,
            emails=emails,
            events=events,
            addresses_used=len(addresses),
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
        """The addresses the mail and event lookups may use, capped."""
        if contact.contact is None:
            return []
        cap = settings.relations_provider_max_addresses
        return [email.value for email in contact.contact.emails][:cap]

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

        APPENDED, never prepended. The cap is a COST bound — each address costs
        three mail searches, since no provider expresses an OR — so a card
        already at the cap loses the addition. Putting the peer's address first
        would instead evict a card address that relationships already query by
        today: strictly additive beats marginally better ranking.

        Args:
            contact: The contact-card section, however it came back.
            target_key: Folded relationship name — the identity key.

        Returns:
            Addresses to query by, deduplicated on the mailbox fold and capped.
        """
        addresses = self._addresses_of(contact)
        peer_address = await self._peer_address(target_key)
        if not peer_address:
            return addresses
        seen = {fold_email(address) for address in addresses}
        if fold_email(peer_address) in seen:
            return addresses
        cap = settings.relations_provider_max_addresses
        return [*addresses, peer_address][:cap]

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
        from src.domains.peers.repository import PeersRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                profiles = await PeersRepository(db).list_accepted_peer_profiles(self.user_id)
        except Exception as exc:
            # Own failure boundary, like the peers bridge in RelationsService:
            # the CRM answers without the peer address rather than not at all.
            logger.warning("relations_peer_address_lookup_failed", error=str(exc))
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
