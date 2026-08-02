"""Which addresses the 360° queries mail and calendar with.

Each address costs THREE mail searches (from / to / cc — no provider can
express an OR), so the cap is a real cost bound and every slot must buy a
DISTINCT mailbox.

Two defects this pins down:

1. the card's addresses were capped BEFORE anything was folded, so a card
   holding ``Jean@x.com`` and ``jean@x.com`` spent two of three slots — and six
   searches — on one mailbox, evicting a third address that would have found
   real correspondence;

2. the peer's own address was compared against that ALREADY CAPPED list, so the
   comparison could not tell "not on the card" from "on the card, past the
   cap". The peer address is the one address the user is CERTAIN about — they
   are connected through this very product and the peer opted in — yet it was
   the one being dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactEmail,
    ContextSection,
    ContextStatus,
)
from src.domains.relations.providers.service import RelationContextService

pytestmark = pytest.mark.unit


def _card(*addresses: str) -> ContextSection:
    return ContextSection(
        status=ContextStatus.OK,
        generated_at=datetime.now(UTC),
        contact=ContactCard(
            display_name="Marie Martin",
            emails=[ContactEmail(value=address) for address in addresses],
        ),
    )


async def _match(monkeypatch: pytest.MonkeyPatch, card: ContextSection, peer: str | None):
    service = RelationContextService(uuid4())

    async def _peer_address(_target_key: str) -> str | None:
        return peer

    monkeypatch.setattr(service, "_peer_address", _peer_address)
    return await service._match_addresses(card, "marie martin")


def _mailboxes(addresses: list[str]) -> set[str]:
    return {address.strip().lower() for address in addresses}


class TestEverySlotBuysADistinctMailbox:
    async def test_case_only_duplicates_are_folded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Six searches for one mailbox, and a real address evicted for it."""
        card = _card("Jean@x.com", "jean@x.com", "b@x.com", "c@x.com")

        addresses = await _match(monkeypatch, card, None)

        assert len(addresses) == len(_mailboxes(addresses))
        assert "c@x.com" in _mailboxes(addresses)

    async def test_the_cap_still_applies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        card = _card(*[f"a{i}@x.com" for i in range(10)])

        addresses = await _match(monkeypatch, card, None)

        assert len(addresses) == settings.relations_provider_max_addresses

    async def test_the_card_order_is_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The provider's order is the only ranking there is; folding must not
        reshuffle it."""
        card = _card("a@x.com", "b@x.com")

        assert await _match(monkeypatch, card, None) == ["a@x.com", "b@x.com"]

    async def test_the_stored_spelling_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Folding decides IDENTITY; the query keeps the address as stored."""
        card = _card("Jean.Dupont@X.com")

        assert await _match(monkeypatch, card, None) == ["Jean.Dupont@X.com"]


class TestThePeerAddressSurvives:
    async def test_it_is_queried_even_when_it_sits_past_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE case the dossier is about: the peer's address IS on the card,
        beyond the cap. It used to be silently dropped."""
        cap = settings.relations_provider_max_addresses
        card = _card(*[f"a{i}@x.com" for i in range(cap)], "marie@lia.com")

        addresses = await _match(monkeypatch, card, "marie@lia.com")

        assert "marie@lia.com" in _mailboxes(addresses)
        assert len(addresses) == cap

    async def test_it_is_added_when_absent_from_the_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap = settings.relations_provider_max_addresses
        card = _card(*[f"a{i}@x.com" for i in range(cap)])

        addresses = await _match(monkeypatch, card, "peer@lia.com")

        assert "peer@lia.com" in _mailboxes(addresses)
        assert len(addresses) == cap

    async def test_it_is_never_queried_twice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The arbitration: no duplicate between the peer address and the card."""
        card = _card("marie@lia.com", "b@x.com")

        addresses = await _match(monkeypatch, card, "MARIE@lia.com")

        assert len(addresses) == len(_mailboxes(addresses))
        assert len(addresses) == 2

    async def test_no_peer_leaves_the_card_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        card = _card("a@x.com", "b@x.com")

        assert await _match(monkeypatch, card, None) == ["a@x.com", "b@x.com"]

    async def test_a_peer_alone_is_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A connected user absent from the address book still has one address."""
        card = _card()

        assert await _match(monkeypatch, card, "peer@lia.com") == ["peer@lia.com"]


class TestNoCardAtAll:
    async def test_missing_contact_section_yields_the_peer_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blank = ContextSection(status=ContextStatus.EMPTY, generated_at=datetime.now(UTC))

        assert await _match(monkeypatch, blank, "peer@lia.com") == ["peer@lia.com"]

    async def test_missing_contact_and_no_peer_yields_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blank = ContextSection(status=ContextStatus.EMPTY, generated_at=datetime.now(UTC))

        assert await _match(monkeypatch, blank, None) == []
