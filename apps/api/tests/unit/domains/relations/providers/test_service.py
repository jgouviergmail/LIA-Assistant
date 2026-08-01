"""Orchestration of the provider sections — order, honesty, isolation.

What must hold:

- the contact card comes FIRST, because it resolves the addresses the other
  two sections are queried with;
- "I could not look" is never rendered as "I looked and found nothing": no
  connector, no address and an empty result are three distinct statuses;
- one failing section never sinks the page, and an error is never cached;
- the flag off asks nothing at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.relations.providers.client import ProviderNotConfigured
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactEmail,
    ContextStatus,
    ExchangedEmail,
    SharedEvent,
)
from src.domains.relations.providers.service import RelationContextService

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NAME = "Gérard Dupont"


def _card(*addresses: str) -> ContactCard:
    return ContactCard(
        display_name=NAME,
        emails=[ContactEmail(value=address) for address in addresses],
    )


def _email(email_id: str = "m1") -> ExchangedEmail:
    return ExchangedEmail(
        id=email_id,
        direction="received",
        subject="Sujet",
        occurred_at=datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
    )


def _event(event_id: str = "e1") -> SharedEvent:
    return SharedEvent(id=event_id, summary="Point", starts_at=None, is_past=False)


class _Cache:
    """A Redis stand-in that records what the service stored."""

    def __init__(self, seeded: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(seeded or {})
        self.writes: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.writes.append(key)
        self.store[key] = value


def _patched(
    *,
    card=None,
    emails=None,
    events=None,
    card_error: Exception | None = None,
    email_error: Exception | None = None,
    event_error: Exception | None = None,
    cache: _Cache | None = None,
):
    """Patch the three fetchers and the cache in one place."""
    cache = cache or _Cache()
    return (
        patch(
            "src.domains.relations.providers.service.fetch_contact_card",
            new=AsyncMock(return_value=card, side_effect=card_error),
        ),
        patch(
            "src.domains.relations.providers.service.fetch_exchanged_emails",
            new=AsyncMock(return_value=emails or [], side_effect=email_error),
        ),
        patch(
            "src.domains.relations.providers.service.fetch_shared_events",
            new=AsyncMock(return_value=events or [], side_effect=event_error),
        ),
        patch(
            "src.domains.relations.providers.service.get_redis_cache",
            new=AsyncMock(return_value=cache),
        ),
        cache,
    )


@pytest.fixture(autouse=True)
def _no_peer_lookup():
    """Keep the peers bridge OUT of the tests that are not about it.

    `_peer_address` opens its own session; with no database under a unit test
    it fails, is swallowed by its failure boundary, and costs twenty seconds of
    connection attempts. The class that IS about it turns the flag back on.
    """
    with patch.object(settings, "peers_enabled", False):
        yield


class _NullSession:
    """Async context manager standing in for `get_db_context()`."""

    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *exc):
        return False


class TestIdentityChain:
    """The card resolves the addresses; the addresses resolve everything else."""

    async def test_mail_and_events_are_queried_with_the_cards_addresses(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("home@x.com", "work@acme.com"), emails=[_email()], events=[_event()]
        )
        with p_card, p_mail, p_event, p_cache as _redis:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.contact.status is ContextStatus.OK
        assert context.emails.status is ContextStatus.OK
        assert context.events.status is ContextStatus.OK
        assert context.addresses_used == 2

    async def test_the_address_cap_is_honored(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com", "b@x.com", "c@x.com", "d@x.com"), emails=[_email()]
        )
        with (
            p_card,
            p_mail as mail,
            p_event,
            p_cache,
            patch("src.domains.relations.providers.service.settings") as cfg,
        ):
            cfg.relations_provider_sections_enabled = True
            cfg.relations_provider_max_addresses = 2
            cfg.relations_provider_max_items = 10
            cfg.relations_provider_window_days = 90
            context = await RelationContextService(USER_ID).build(NAME)

        assert mail.await_args.kwargs["addresses"] == ["a@x.com", "b@x.com"]
        assert context.addresses_used == 2

    async def test_a_card_without_an_address_never_pretends_to_have_looked(self) -> None:
        """NO_ADDRESS, not EMPTY: the question was never asked."""
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card())
        with p_card, p_mail as mail, p_event as event, p_cache:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.contact.status is ContextStatus.OK
        assert context.emails.status is ContextStatus.NO_ADDRESS
        assert context.events.status is ContextStatus.NO_ADDRESS
        assert context.addresses_used == 0
        mail.assert_not_awaited()
        event.assert_not_awaited()

    async def test_no_card_at_all_leaves_the_other_two_unasked(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None)
        with p_card, p_mail, p_event, p_cache:
            context = await RelationContextService(USER_ID).build(NAME)
        assert context.contact.status is ContextStatus.EMPTY
        assert context.emails.status is ContextStatus.NO_ADDRESS


class TestStatuses:
    """Three ways of having nothing, and they are not the same sentence."""

    async def test_a_missing_connector_reads_not_configured(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(card_error=ProviderNotConfigured("contacts"))
        with p_card, p_mail, p_event, p_cache:
            context = await RelationContextService(USER_ID).build(NAME)
        assert context.contact.status is ContextStatus.NOT_CONFIGURED

    async def test_an_empty_result_reads_empty(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card("a@x.com"), emails=[])
        with p_card, p_mail, p_event, p_cache:
            context = await RelationContextService(USER_ID).build(NAME)
        assert context.emails.status is ContextStatus.EMPTY

    async def test_one_failing_section_never_sinks_the_others(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com"),
            email_error=TimeoutError("mail provider down"),
            events=[_event()],
        )
        with p_card, p_mail, p_event, p_cache:
            context = await RelationContextService(USER_ID).build(NAME)
        assert context.emails.status is ContextStatus.ERROR
        assert context.events.status is ContextStatus.OK

    async def test_the_flag_off_asks_nothing_and_claims_nothing(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card("a@x.com"))
        with (
            p_card as contact,
            p_mail,
            p_event,
            p_cache,
            patch("src.domains.relations.providers.service.settings") as cfg,
        ):
            cfg.relations_provider_sections_enabled = False
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.contact.status is ContextStatus.NOT_CONFIGURED
        assert context.window_days == 0
        contact.assert_not_awaited()

    async def test_a_blank_name_asks_nothing(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card("a@x.com"))
        with p_card as contact, p_mail, p_event, p_cache:
            context = await RelationContextService(USER_ID).build("   ")
        assert context.contact.status is ContextStatus.NOT_CONFIGURED
        contact.assert_not_awaited()


class TestCache:
    async def test_a_second_read_is_served_from_the_cache_and_says_so(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com"), emails=[_email()], cache=cache
        )
        with p_card as contact, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)
            again = await RelationContextService(USER_ID).build(NAME)

        assert again.contact.from_cache is True
        assert again.contact.contact is not None  # the payload survived the round trip
        assert contact.await_count == 1  # the provider was asked exactly once

    async def test_an_error_is_never_cached(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com"), email_error=TimeoutError("down"), cache=cache
        )
        with p_card, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)

        assert not any(key.endswith(":emails") for key in cache.writes)

    async def test_the_key_never_carries_a_raw_display_name(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None, cache=cache)
        with p_card, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build("Gérard Dupont: le voisin")

        assert cache.writes
        assert all("Gérard" not in key and " " not in key for key in cache.writes)

    async def test_two_people_never_share_a_cache_entry(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None, cache=cache)
        with p_card, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build("Gérard Dupont")
            await RelationContextService(USER_ID).build("Marie Leroy")
        assert len(set(cache.writes)) == 2

    async def test_a_forced_section_ignores_its_cache_and_the_others_keep_theirs(self) -> None:
        """The contact card lives up to six hours: without a way to say "look
        again", a correction in the address book stays invisible half a day.
        Forcing one section must not spend the other sections' quota."""
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com"), emails=[_email()], cache=cache
        )
        with p_card as contact, p_mail as mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)
            again = await RelationContextService(USER_ID).build(
                NAME, refresh=frozenset({"contact"})
            )

        assert contact.await_count == 2  # asked again
        assert mail.await_count == 1  # not asked again
        assert again.contact.from_cache is False
        assert again.emails.from_cache is True

    async def test_forcing_everything_re_reads_the_three(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("a@x.com"), emails=[_email()], events=[_event()], cache=cache
        )
        forced = frozenset({"contact", "emails", "events"})
        with p_card as contact, p_mail as mail, p_event as events, p_cache:
            await RelationContextService(USER_ID).build(NAME)
            again = await RelationContextService(USER_ID).build(NAME, refresh=forced)

        assert (contact.await_count, mail.await_count, events.await_count) == (2, 2, 2)
        assert not any(
            section.from_cache for section in (again.contact, again.emails, again.events)
        )

    async def test_an_unknown_section_name_forces_nothing(self) -> None:
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card("a@x.com"), cache=cache)
        with p_card as contact, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)
            await RelationContextService(USER_ID).build(NAME, refresh=frozenset({"inconnue"}))
        assert contact.await_count == 1

    async def test_a_card_that_gains_an_address_invalidates_the_mail_it_fed(self) -> None:
        """The card IS the identity the other two are queried with.

        Keyed on the person alone, a corrected address book would keep serving
        mail computed from the OLD identity under the NEW card — stale in the
        one way the reader cannot see. The addresses belong in the key, so a
        changed identity is a cache MISS by construction rather than a cascade
        the caller must remember to trigger.
        """
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("home@x.com"), emails=[_email()], cache=cache
        )
        with p_card, p_mail as mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)
        assert mail.await_count == 1

        # The address book gains a second address for the same person.
        p_card2, p_mail2, p_event2, p_cache2, _ = _patched(
            card=_card("home@x.com", "work@acme.com"), emails=[_email()], cache=cache
        )
        with p_card2, p_mail2 as mail_again, p_event2, p_cache2:
            again = await RelationContextService(USER_ID).build(
                NAME, refresh=frozenset({"contact"})
            )

        assert mail_again.await_count == 1  # recomputed, not served stale
        assert again.emails.from_cache is False
        assert again.addresses_used == 2

    async def test_an_unchanged_card_still_serves_mail_from_the_cache(self) -> None:
        """The key must not churn on its own: same identity, same entry."""
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("home@x.com"), emails=[_email()], cache=cache
        )
        with p_card, p_mail as mail, p_event, p_cache:
            await RelationContextService(USER_ID).build(NAME)
            again = await RelationContextService(USER_ID).build(
                NAME, refresh=frozenset({"contact"})
            )

        assert mail.await_count == 1
        assert again.emails.from_cache is True

    async def test_two_spellings_of_one_person_share_it(self) -> None:
        """The key folds like the CRM does — otherwise the cache would split a
        person the rest of the product treats as one."""
        cache = _Cache()
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None, cache=cache)
        with p_card, p_mail, p_event, p_cache:
            await RelationContextService(USER_ID).build("Gérard Dupont")
            await RelationContextService(USER_ID).build("gerard dupont")
        assert len(set(cache.writes)) == 1


class TestAConnectedPeerBringsTheirOwnAddress:
    """A peer absent from the address book still has a knowable address.

    Measured on the dev API, 2026-08-01: a 360° on a connected peer came back
    with `events` UNAVAILABLE and mail matched only by name — the person had no
    address-book entry, so `_addresses_of` returned nothing and neither the
    mail nor the calendar could match a correspondent or an attendee. Yet the
    two are connected THROUGH THIS PRODUCT, and the peer had made their address
    visible.

    The address is used ONLY when its owner opted in (`peer_email_visible`,
    ADR-189), and only to match inside the user's OWN mail and calendar, which
    they can already read. This deliberately revises ADR-189's clause "the
    opt-in does not feed the CRM's provider sections" (ADR-191): that clause
    guarded against the address becoming a source by SIDE EFFECT, bypassing the
    setting. Here the setting is read, and it alone decides.

    Same seam for the page and the assistant — `RelationContextService` is
    what both call, so they cannot answer differently.
    """

    @staticmethod
    def _peers(email: str | None, name: str = NAME):
        """Patch the accepted-connections read with one profile."""
        from src.domains.peers.schemas import PeerConnectionProfile

        profile = PeerConnectionProfile(
            connection_id=uuid4(),
            peer_id=uuid4(),
            peer_display_name=name,
            connected_since=None,
            peer_email=email,
        )
        repo = MagicMock()
        repo.list_accepted_peer_profiles = AsyncMock(return_value=[profile])
        return (
            patch("src.domains.peers.repository.PeersRepository", MagicMock(return_value=repo)),
            patch(
                "src.infrastructure.database.session.get_db_context",
                new=lambda: _NullSession(),
            ),
            patch.object(settings, "peers_enabled", True),
        )

    async def test_the_shared_address_makes_mail_and_meetings_answerable(self) -> None:
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=None, emails=[_email()], events=[_event()]
        )
        p_repo, p_db, p_flag = self._peers("peer@lia.app")
        with p_card, p_mail, p_event, p_cache, p_repo, p_db, p_flag:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.addresses_used == 1
        assert context.emails.status is ContextStatus.OK
        assert context.events.status is ContextStatus.OK

    async def test_without_the_opt_in_nothing_changes(self) -> None:
        """No consent, no address — the honest NO_ADDRESS stands."""
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None)
        p_repo, p_db, p_flag = self._peers(None)
        with p_card, p_mail, p_event, p_cache, p_repo, p_db, p_flag:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.emails.status is ContextStatus.NO_ADDRESS
        assert context.events.status is ContextStatus.NO_ADDRESS

    async def test_a_stranger_is_untouched(self) -> None:
        """Not a connection: the peers read yields nothing to add."""
        p_card, p_mail, p_event, p_cache, _ = _patched(card=None)
        p_repo, p_db, p_flag = self._peers("someone@else.com", name="Quelqu'un d'autre")
        with p_card, p_mail, p_event, p_cache, p_repo, p_db, p_flag:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.emails.status is ContextStatus.NO_ADDRESS

    async def test_the_card_address_is_never_duplicated(self) -> None:
        """Same mailbox on both sides counts once — folded, not compared raw."""
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card("Peer@LIA.app"), emails=[_email()], events=[_event()]
        )
        p_repo, p_db, p_flag = self._peers("peer@lia.app")
        with p_card, p_mail, p_event, p_cache, p_repo, p_db, p_flag:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.addresses_used == 1

    async def test_a_full_card_keeps_its_own_addresses(self) -> None:
        """The cap is a COST bound; the addition never evicts an existing one.

        Each address costs three mail searches, so the cap binds. Prepending
        the peer's address would drop a card address that this relationship
        already queries by today — a regression traded for a ranking guess.
        """
        cap = settings.relations_provider_max_addresses
        card_addresses = [f"a{index}@x.com" for index in range(cap)]
        p_card, p_mail, p_event, p_cache, _ = _patched(
            card=_card(*card_addresses), emails=[_email()], events=[_event()]
        )
        p_repo, p_db, p_flag = self._peers("peer@lia.app")
        with p_card, p_mail, p_event, p_cache, p_repo, p_db, p_flag:
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.addresses_used == cap

    async def test_a_failing_peers_read_never_costs_the_card(self) -> None:
        """Own failure boundary: the CRM answers without it, not at all."""
        p_card, p_mail, p_event, p_cache, _ = _patched(card=_card("home@x.com"), emails=[_email()])
        repo = MagicMock()
        repo.list_accepted_peer_profiles = AsyncMock(side_effect=RuntimeError("peers down"))
        with (
            p_card,
            p_mail,
            p_event,
            p_cache,
            patch("src.domains.peers.repository.PeersRepository", MagicMock(return_value=repo)),
            patch("src.infrastructure.database.session.get_db_context", new=lambda: _NullSession()),
            patch.object(settings, "peers_enabled", True),
        ):
            context = await RelationContextService(USER_ID).build(NAME)

        assert context.contact.status is ContextStatus.OK
        assert context.addresses_used == 1
