"""Contact-card fetcher — the identity keystone of the provider sections.

What must hold:

- the provider search is a HINT, never a verdict: every candidate is verified
  by the SAME folding the CRM buckets on, so a fuzzy provider match can never
  put someone else's card (and someone else's addresses) under this name;
- the card carries EVERYTHING the address book holds about the person — a card
  showing two fields out of ten is a card the reader stops trusting — minus the
  photo, which is an identity decision rather than a data one;
- a date the address book stores without a year keeps that year missing;
- an absent connector and an empty address book are different answers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.providers.client import CategoryClient, ProviderNotConfigured
from src.domains.relations.providers.contacts import fetch_contact_card

pytestmark = pytest.mark.unit

USER_ID = uuid4()


def _person(
    *,
    name: str = "Gérard Dupont",
    emails: list[dict] | None = None,
    phones: list[dict] | None = None,
    org: str | None = None,
    **blocks: object,
) -> dict:
    """One normalized person record, in the shape all three providers emit."""
    person: dict = {"names": [{"displayName": name}]}
    if emails is not None:
        person["emailAddresses"] = emails
    if phones is not None:
        person["phoneNumbers"] = phones
    if org is not None:
        person["organizations"] = [{"name": org}]
    person.update(blocks)
    return {"person": person}


def _patched(results: list[dict] | Exception):
    """Patch the category client with a contacts client returning `results`."""
    import contextlib

    search = (
        AsyncMock(side_effect=results)
        if isinstance(results, Exception)
        else AsyncMock(return_value={"results": results})
    )
    client = SimpleNamespace(search_contacts=search)

    @contextlib.asynccontextmanager
    async def _open(category, user_id):
        yield CategoryClient(client=client, connector_type=None, session=None)

    return patch("src.domains.relations.providers.contacts.open_category_client", _open), client


class TestExactVerification:
    """The provider searches; the CRM decides who that is."""

    async def test_returns_the_card_whose_folded_name_matches(self) -> None:
        patcher, _ = _patched([_person(name="Gérard Dupont")])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert card.display_name == "Gérard Dupont"

    async def test_a_fuzzy_provider_match_is_refused(self) -> None:
        """Google's people:searchContacts matches prefixes and substrings.

        Trusting it would attach another person's addresses to this card — and
        every mail and event lookup downstream is built on those addresses.
        """
        patcher, _ = _patched([_person(name="Gérard Dupontel")])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is None

    async def test_accents_and_case_still_fold_into_one_person(self) -> None:
        patcher, _ = _patched([_person(name="gerard DUPONT")])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None

    async def test_the_matching_card_wins_over_the_first_result(self) -> None:
        patcher, _ = _patched(
            [_person(name="Gérard Dupontel"), _person(name="Gérard Dupont", org="ACME")]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None and card.organization == "ACME"


class TestPayload:
    """Only what a CRM card needs."""

    async def test_carries_addresses_phones_and_organization(self) -> None:
        patcher, _ = _patched(
            [
                _person(
                    emails=[
                        {"value": "gerard@example.com", "type": "home"},
                        {"value": "g.dupont@acme.com", "type": "work"},
                    ],
                    phones=[{"value": "+33600000000", "type": "mobile"}],
                    org="ACME",
                )
            ]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")

        assert card is not None
        assert [email.value for email in card.emails] == [
            "gerard@example.com",
            "g.dupont@acme.com",
        ]
        assert [email.label for email in card.emails] == ["home", "work"]
        assert [phone.value for phone in card.phones] == ["+33600000000"]
        assert card.organization == "ACME"

    async def test_a_card_with_nothing_but_a_name_is_still_a_card(self) -> None:
        patcher, _ = _patched([_person()])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert card.emails == [] and card.phones == [] and card.organization is None

    async def test_blank_values_never_reach_the_card(self) -> None:
        patcher, _ = _patched(
            [_person(emails=[{"value": "  "}, {"value": "ok@x.com"}], phones=[{"value": ""}])]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert [email.value for email in card.emails] == ["ok@x.com"]
        assert card.phones == []

    async def test_every_field_the_card_renders_is_requested(self) -> None:
        """A block absent from the readMask can never reach the card.

        This is the ONLY place the two lists are tied together: asking for less
        than the card renders shows an empty section for data the address book
        does hold — which reads as "nothing stored" (ADR-184's mistake, one
        layer down).
        """
        patcher, client = _patched([_person()])
        with patcher:
            await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="Gérard")
        requested = client.search_contacts.await_args.kwargs["fields"]
        assert set(requested) == {
            "names",
            "nicknames",
            "emailAddresses",
            "phoneNumbers",
            "addresses",
            "birthdays",
            "biographies",
            "organizations",
            "occupations",
            "relations",
            "urls",
            "events",
            "imClients",
        }
        assert client.search_contacts.await_args.args[0] == "Gérard"

    async def test_the_photo_is_never_requested(self) -> None:
        """Deliberate: a third party's likeness is an identity decision."""
        patcher, client = _patched([_person()])
        with patcher:
            await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert "photos" not in client.search_contacts.await_args.kwargs["fields"]


class TestEverythingTheAddressBookHolds:
    """Every block the provider stored, not the four easy ones."""

    async def test_each_block_reaches_the_card_with_its_label(self) -> None:
        patcher, _ = _patched(
            [
                _person(
                    nicknames=[{"value": "Gégé"}],
                    occupations=[{"value": "Architecte"}],
                    biographies=[{"value": "Rencontré au forum."}],
                    addresses=[
                        {"formattedValue": "12 rue des Lilas, Lyon", "type": "home"},
                        {"formattedValue": "1 av. de l'Europe, Paris", "type": "work"},
                    ],
                    relations=[{"person": "Claire Lefèvre", "type": "spouse"}],
                    urls=[{"value": "https://example.com", "type": "blog"}],
                    imClients=[{"username": "gerard.d", "protocol": "skype", "type": "home"}],
                )
            ]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")

        assert card is not None
        assert card.nickname == "Gégé"
        assert card.occupation == "Architecte"
        assert card.biography == "Rencontré au forum."
        assert [(a.value, a.label) for a in card.addresses] == [
            ("12 rue des Lilas, Lyon", "home"),
            ("1 av. de l'Europe, Paris", "work"),
        ]
        assert [(r.value, r.label) for r in card.relations] == [("Claire Lefèvre", "spouse")]
        assert [(link.value, link.label) for link in card.links] == [
            ("https://example.com", "blog")
        ]
        # The protocol says more than home/work about a chat handle.
        assert [(m.value, m.label) for m in card.messaging] == [("gerard.d", "skype")]

    async def test_a_job_title_reaches_the_card_without_googles_field(self) -> None:
        """Apple and Graph carry the title INSIDE the organization.

        Reading only ``occupations`` would leave every non-Google contact
        titleless while the address book holds the title.
        """
        patcher, _ = _patched(
            [_person(organizations=[{"name": "ACME", "title": "Directrice technique"}])]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert card.organization == "ACME"
        assert card.occupation == "Directrice technique"

    async def test_a_birthday_without_a_year_keeps_the_year_missing(self) -> None:
        """RFC 6350's own notation. Inventing a year would age the person."""
        patcher, _ = _patched([_person(birthdays=[{"date": {"month": 4, "day": 7}}])])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None and card.birthday == "--04-07"

    async def test_a_full_birthday_is_an_iso_date(self) -> None:
        patcher, _ = _patched([_person(birthdays=[{"date": {"year": 1978, "month": 4, "day": 7}}])])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None and card.birthday == "1978-04-07"

    async def test_the_date_parts_win_over_the_free_text(self) -> None:
        """Google stores both; only the parts can be localized downstream."""
        patcher, _ = _patched(
            [_person(birthdays=[{"text": "7 avril", "date": {"month": 4, "day": 7}}])]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None and card.birthday == "--04-07"

    async def test_free_text_survives_when_it_is_all_there_is(self) -> None:
        patcher, _ = _patched([_person(birthdays=[{"text": "au printemps"}])])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None and card.birthday == "au printemps"

    async def test_an_important_date_is_a_date_not_a_dict(self) -> None:
        """Google's ``events`` carry parts, not a string.

        Stringifying the entry would print ``{'year': 2011, ...}`` on the card.
        """
        patcher, _ = _patched(
            [
                _person(
                    events=[{"date": {"year": 2011, "month": 9, "day": 3}, "type": "anniversary"}]
                )
            ]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert [(d.value, d.label) for d in card.important_dates] == [("2011-09-03", "anniversary")]

    async def test_an_unusable_date_is_dropped_rather_than_half_shown(self) -> None:
        patcher, _ = _patched(
            [
                _person(
                    birthdays=[{"date": {"year": 1978}}],
                    events=[{"date": {}, "type": "anniversary"}],
                )
            ]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert card.birthday is None and card.important_dates == []

    async def test_a_provider_that_stores_none_of_a_block_yields_an_empty_one(self) -> None:
        """Apple and Graph have no relations/links/dates/messaging at all.

        Empty is the honest answer: the card omits the block rather than
        showing a placeholder for something nobody wrote down.
        """
        patcher, _ = _patched([_person(addresses=[{"formattedValue": "Lyon"}])])
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert [a.value for a in card.addresses] == ["Lyon"]
        assert card.relations == [] and card.links == []
        assert card.important_dates == [] and card.messaging == []
        assert card.nickname is None and card.biography is None

    async def test_malformed_entries_never_break_the_card(self) -> None:
        """A provider list holding a string, a None or a blank value."""
        patcher, _ = _patched(
            [
                _person(
                    addresses=["oops", None, {"formattedValue": "  "}, {"formattedValue": "Lyon"}],
                    relations=[{"person": ""}],
                    nicknames=["nope"],
                    birthdays=["nope"],
                    events=["nope"],
                )
            ]
        )
        with patcher:
            card = await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
        assert card is not None
        assert [a.value for a in card.addresses] == ["Lyon"]
        assert card.relations == [] and card.nickname is None and card.birthday is None


class TestBoundaries:
    async def test_an_empty_address_book_answers_none(self) -> None:
        patcher, _ = _patched([])
        with patcher:
            assert (
                await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")
                is None
            )

    async def test_a_missing_connector_propagates_as_such(self) -> None:
        """NOT None: "no address book" and "nobody by that name" are different
        answers, and only the caller can turn them into the right status."""
        import contextlib

        @contextlib.asynccontextmanager
        async def _open(category, user_id):
            raise ProviderNotConfigured(category)
            yield  # pragma: no cover — unreachable, keeps the generator shape

        with (
            patch("src.domains.relations.providers.contacts.open_category_client", _open),
            pytest.raises(ProviderNotConfigured),
        ):
            await fetch_contact_card(USER_ID, target_key="gerard dupont", search_name="x")

    async def test_a_blank_target_key_never_asks_anything(self) -> None:
        patcher, client = _patched([_person()])
        with patcher:
            assert await fetch_contact_card(USER_ID, target_key="", search_name="x") is None
        client.search_contacts.assert_not_awaited()
