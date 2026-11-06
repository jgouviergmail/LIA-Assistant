"""A contact's given and family names, job title, website and birthday (ADR-369, lot 9.2).

One write contract on three providers: what is left out is kept, an empty text empties a field,
a birthday goes by a flag. A person's job and their company share one Google entry and one vCard
card, so writing either keeps the other.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import vobject

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.contact_details import NO_YEAR, ContactDetails
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    build_contact_body,
    build_contact_update_body,
    normalize_graph_contact,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

FULL = ContactDetails(
    given_name="Ana",
    family_name="Lima",
    job_title="Engineer",
    website="https://ana.example.org",
    birthday=date(1990, 5, 15),
)


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _google(*answers: Any) -> tuple[GooglePeopleClient, AsyncMock]:
    client = GooglePeopleClient(uuid4(), _credentials(), MagicMock())
    request = AsyncMock(side_effect=list(answers))
    client._make_request = request
    client._get_cache = AsyncMock(
        return_value=MagicMock(invalidate_user=AsyncMock(), set_details=AsyncMock())
    )
    return client, request


class TestGoogle:
    async def test_a_contact_is_read_with_all_a_change_must_keep(self) -> None:
        client, request = _google({"resourceName": "people/c1"})

        await client.get_person("people/c1", use_cache=False)

        asked = request.await_args.kwargs["params"]["personFields"].split(",")
        assert {"names", "organizations", "urls", "birthdays"} <= set(asked)

    async def test_a_new_contact_carries_them(self) -> None:
        client, request = _google({"resourceName": "people/c1"})

        await client.create_contact("Ana Lima", organization="Acme", details=FULL)

        body = request.await_args.kwargs["json_data"]
        assert body["names"] == [{"givenName": "Ana", "familyName": "Lima"}]
        assert body["organizations"] == [{"name": "Acme", "title": "Engineer"}]
        assert body["urls"] == [{"value": "https://ana.example.org"}]
        assert body["birthdays"] == [{"date": {"year": 1990, "month": 5, "day": 15}}]

    async def test_a_new_contact_with_none_writes_as_before(self) -> None:
        client, request = _google({"resourceName": "people/c1"})

        await client.create_contact("Ana Lima")

        body = request.await_args.kwargs["json_data"]
        assert body == {"names": [{"givenName": "Ana Lima"}]}

    async def _updated(
        self, current: dict[str, Any], details: ContactDetails, **kwargs: Any
    ) -> Any:
        client, request = _google({"resourceName": "people/c1"})
        with patch.object(client, "get_person", AsyncMock(return_value=current)):
            await client.update_contact("people/c1", details=details, **kwargs)
        return request.await_args

    async def test_a_job_title_keeps_the_company(self) -> None:
        call = await self._updated(
            {"etag": "e", "organizations": [{"name": "Acme", "title": "Old", "department": "R&D"}]},
            ContactDetails(job_title="New"),
        )

        assert call.kwargs["json_data"]["organizations"] == [
            {"name": "Acme", "title": "New", "department": "R&D"}
        ]
        assert call.kwargs["params"]["updatePersonFields"] == "organizations"

    async def test_a_company_keeps_the_job_title(self) -> None:
        client, request = _google({"resourceName": "people/c1"})
        current = {"etag": "e", "organizations": [{"name": "Old", "title": "Engineer"}]}

        with patch.object(client, "get_person", AsyncMock(return_value=current)):
            await client.update_contact("people/c1", organization="New")

        assert request.await_args.kwargs["json_data"]["organizations"] == [
            {"name": "New", "title": "Engineer"}
        ]

    async def test_a_job_keeps_a_second_organization(self) -> None:
        call = await self._updated(
            {"etag": "e", "organizations": [{"name": "Acme"}, {"name": "Side"}]},
            ContactDetails(job_title="CTO"),
        )

        assert call.kwargs["json_data"]["organizations"] == [
            {"name": "Acme", "title": "CTO"},
            {"name": "Side"},
        ]

    async def test_a_company_keeps_a_second_organization(self) -> None:
        client, request = _google({"resourceName": "people/c1"})
        current = {"etag": "e", "organizations": [{"name": "Old"}, {"name": "Side"}]}

        with patch.object(client, "get_person", AsyncMock(return_value=current)):
            await client.update_contact("people/c1", organization="New")

        assert request.await_args.kwargs["json_data"]["organizations"] == [
            {"name": "New"},
            {"name": "Side"},
        ]

    async def test_a_website_replaces_the_first_and_keeps_the_others(self) -> None:
        call = await self._updated(
            {"etag": "e", "urls": [{"value": "https://a"}, {"value": "https://b"}]},
            ContactDetails(website="https://c"),
        )

        assert call.kwargs["json_data"]["urls"] == [{"value": "https://c"}, {"value": "https://b"}]

    async def test_an_empty_website_takes_the_first_away(self) -> None:
        call = await self._updated(
            {"etag": "e", "urls": [{"value": "https://a"}]}, ContactDetails(website="")
        )

        assert call.kwargs["json_data"]["urls"] == []

    async def test_a_name_keeps_the_part_it_did_not_name(self) -> None:
        call = await self._updated(
            {"etag": "e", "names": [{"givenName": "Ana", "familyName": "Lima"}]},
            ContactDetails(family_name="Silva"),
        )

        assert call.kwargs["json_data"]["names"] == [{"givenName": "Ana", "familyName": "Silva"}]

    async def test_a_name_part_keeps_what_the_person_named_and_nothing_google_derives(self) -> None:
        call = await self._updated(
            {
                "etag": "e",
                "names": [
                    {
                        "displayName": "Dr Ana Lima",
                        "unstructuredName": "Dr Ana Lima",
                        "honorificPrefix": "Dr",
                        "givenName": "Ana",
                        "familyName": "Lima",
                        "metadata": {"primary": True},
                    }
                ],
            },
            ContactDetails(family_name="Silva"),
        )

        assert call.kwargs["json_data"]["names"] == [
            {"honorificPrefix": "Dr", "givenName": "Ana", "familyName": "Silva"}
        ]

    async def test_a_whole_name_gives_way_to_the_parts_sent_with_it(self) -> None:
        call = await self._updated(
            {"etag": "e", "names": [{"givenName": "Ana", "familyName": "Lima"}]},
            ContactDetails(given_name="Ana Maria"),
            name="Ana Maria Lima",
        )

        assert call.kwargs["json_data"]["names"] == [
            {"givenName": "Ana Maria", "familyName": "Lima"}
        ]
        assert call.kwargs["params"]["updatePersonFields"] == "names"

    async def test_parts_emptied_leave_the_whole_name_when_it_came_with_them(self) -> None:
        call = await self._updated(
            {"etag": "e", "names": [{"givenName": "Ana", "familyName": "Lima"}]},
            ContactDetails(given_name="", family_name=""),
            name="Acme",
        )

        assert call.kwargs["json_data"]["names"] == [{"givenName": "Acme"}]

    async def test_a_website_keeps_the_kind_of_the_one_it_replaces(self) -> None:
        call = await self._updated(
            {"etag": "e", "urls": [{"value": "https://a", "type": "blog"}]},
            ContactDetails(website="https://c"),
        )

        assert call.kwargs["json_data"]["urls"] == [{"value": "https://c", "type": "blog"}]

    async def test_a_birthday_with_no_year_is_written_with_none(self) -> None:
        call = await self._updated({"etag": "e"}, ContactDetails(birthday=date(NO_YEAR, 2, 29)))

        assert call.kwargs["json_data"]["birthdays"] == [{"date": {"month": 2, "day": 29}}]

    async def test_a_birthday_is_written_and_taken_off(self) -> None:
        written = await self._updated({"etag": "e"}, ContactDetails(birthday=date(1990, 5, 15)))
        cleared = await self._updated({"etag": "e"}, ContactDetails(clear_birthday=True))

        assert written.kwargs["json_data"]["birthdays"] == [
            {"date": {"year": 1990, "month": 5, "day": 15}}
        ]
        assert cleared.kwargs["json_data"]["birthdays"] == []
        assert cleared.kwargs["params"]["updatePersonFields"] == "birthdays"


class TestSavingAnOtherContact:
    async def test_it_is_copied_with_what_google_holds_of_it(self) -> None:
        client, request = _google({"resourceName": "people/c1"})

        made = await client.save_other_contact("otherContacts/c9")

        assert made == {"resourceName": "people/c1"}
        assert request.await_args.args == (
            "POST",
            "/otherContacts/c9:copyOtherContactToMyContactsGroup",
        )
        assert request.await_args.kwargs["json_data"] == {
            "copyMask": "names,emailAddresses,phoneNumbers"
        }

    @pytest.mark.parametrize(
        "name", ["people/c1", "otherContacts/c9:batch", "otherContacts/../people/c1", ""]
    )
    async def test_a_name_of_another_shape_reaches_no_one(self, name: str) -> None:
        client, request = _google({})

        with pytest.raises(ConnectorAPIError):
            await client.save_other_contact(name)

        request.assert_not_awaited()


class TestGraph:
    async def test_a_contact_is_read_with_all_it_can_write(self) -> None:
        client = MicrosoftContactsClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(return_value={"id": "c1"})
        client._make_request = request

        await client.get_person("people/c1")

        asked = request.await_args.args[2]["$select"].split(",")
        assert {"givenName", "surname", "jobTitle", "businessHomePage", "birthday"} <= set(asked)

    async def test_a_change_needs_no_read_first(self) -> None:
        client = MicrosoftContactsClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(return_value={"id": "c1"})
        client._make_request = request

        with patch(
            "src.domains.connectors.clients.microsoft_contacts_client.invalidate_contacts_cache",
            AsyncMock(),
        ):
            await client.update_contact("people/c1", details=ContactDetails(job_title="CTO"))

        assert [call.args[0] for call in request.await_args_list] == ["PATCH"]
        assert request.await_args.kwargs["json_data"] == {"jobTitle": "CTO"}

    def test_a_new_contact_carries_them(self) -> None:
        body = build_contact_body("Ana Lima", organization="Acme", details=FULL)

        assert body["givenName"] == "Ana"
        assert body["surname"] == "Lima"
        assert body["jobTitle"] == "Engineer"
        assert body["businessHomePage"] == "https://ana.example.org"
        assert body["birthday"] == "1990-05-15T00:00:00Z"

    def test_the_parts_win_over_a_split_of_the_name(self) -> None:
        body = build_contact_body(
            "Ana Maria Lima", details=ContactDetails(given_name="Ana Maria", family_name="Lima")
        )

        assert body["givenName"] == "Ana Maria"
        assert body["surname"] == "Lima"

    def test_a_change_writes_what_it_names_and_nothing_else(self) -> None:
        assert build_contact_update_body(details=ContactDetails(job_title="New")) == {
            "jobTitle": "New"
        }

    def test_a_birthday_goes_by_its_flag(self) -> None:
        assert build_contact_update_body(details=ContactDetails(clear_birthday=True)) == {
            "birthday": None
        }

    def test_an_empty_website_empties_it(self) -> None:
        assert build_contact_update_body(details=ContactDetails(website="")) == {
            "businessHomePage": ""
        }

    def test_what_is_read_speaks_the_shared_vocabulary(self) -> None:
        person = normalize_graph_contact(
            {
                "id": "c1",
                "displayName": "Ana Lima",
                "jobTitle": "Engineer",
                "businessHomePage": "https://ana.example.org",
                "birthday": "1990-05-15T11:59:00Z",
            }
        )

        assert person["organizations"][0]["title"] == "Engineer"
        assert person["urls"] == [{"value": "https://ana.example.org"}]
        assert person["birthdays"] == [{"date": {"year": 1990, "month": 5, "day": 15}}]


class TestVcard:
    def test_a_new_card_carries_them(self) -> None:
        card = vobject.readOne(build_vcard("Ana Lima", organization="Acme", details=FULL))

        assert card.n.value.given == "Ana"
        assert card.n.value.family == "Lima"
        assert card.title.value == "Engineer"
        assert card.url.value == "https://ana.example.org"
        assert card.bday.value == "1990-05-15"

    def test_it_reads_back_in_the_shared_vocabulary(self) -> None:
        person = normalize_vcard(build_vcard("Ana Lima", organization="Acme", details=FULL))

        assert person["names"][0]["givenName"] == "Ana"
        assert person["organizations"][0]["title"] == "Engineer"
        assert person["urls"] == [{"value": "https://ana.example.org"}]
        assert person["birthdays"][0]["date"] == {"year": 1990, "month": 5, "day": 15}

    def test_a_change_keeps_every_other_line(self) -> None:
        kept = build_vcard("Ana Lima", email="ana@example.org", organization="Acme")

        updated = vobject.readOne(merge_vcard_fields(kept, details=ContactDetails(job_title="CTO")))

        assert updated.title.value == "CTO"
        assert updated.email.value == "ana@example.org"
        assert updated.org.value == ["Acme"]

    def test_a_name_keeps_the_part_it_did_not_name(self) -> None:
        kept = build_vcard("Ana Lima", details=FULL)

        card = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(family_name="Silva"))
        )

        assert card.n.value.given == "Ana"
        assert card.n.value.family == "Silva"

    def test_the_whole_name_follows_the_parts_it_was_made_of(self) -> None:
        kept = build_vcard("Ana Lima", details=FULL)

        card = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(family_name="Silva"))
        )

        assert card.fn.value == "Ana Silva"

    def test_a_name_of_the_person_s_own_stays_when_the_parts_change(self) -> None:
        kept = build_vcard("Dr Ana Lima", details=FULL)

        card = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(family_name="Silva"))
        )

        assert card.fn.value == "Dr Ana Lima"

    def test_a_birthday_is_taken_off(self) -> None:
        kept = build_vcard("Ana Lima", details=FULL)

        card = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(clear_birthday=True))
        )

        assert not hasattr(card, "bday")

    def test_an_empty_website_takes_it_off(self) -> None:
        kept = build_vcard("Ana Lima", details=FULL)

        card = vobject.readOne(merge_vcard_fields(kept, details=ContactDetails(website="")))

        assert not hasattr(card, "url")

    def test_a_card_s_other_websites_stay(self) -> None:
        kept = _card("URL:https://a", "URL:https://b")

        changed = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(website="https://c"))
        )
        emptied = vobject.readOne(merge_vcard_fields(kept, details=ContactDetails(website="")))

        assert [line.value for line in changed.contents["url"]] == ["https://c", "https://b"]
        assert [line.value for line in emptied.contents["url"]] == ["https://b"]

    def test_a_card_holding_no_name_lines_takes_the_parts(self) -> None:
        card = vobject.readOne(
            merge_vcard_fields(_card(with_name=False), details=ContactDetails(family_name="Lima"))
        )

        assert card.n.value.family == "Lima"

    def test_apple_s_year_of_no_year_reads_as_none(self) -> None:
        person = normalize_vcard(_card("BDAY;X-APPLE-OMIT-YEAR=1604:1604-05-15"))

        assert person["birthdays"] == [{"date": {"month": 5, "day": 15}}]


def _card(*lines: str, with_name: bool = True) -> str:
    """A card as a provider wrote it."""
    name = ["N:Lima;Ana;;;"] if with_name else []
    return "\r\n".join(
        ["BEGIN:VCARD", "VERSION:3.0", "FN:Ana Lima", *name, *lines, "END:VCARD", ""]
    )
