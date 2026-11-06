"""Contact groups on the three providers, one vocabulary (ADR-369, lot 9).

Google has groups. Graph has none a contact can sit in several of: a category is one, written on
the contact (measured: a free category is taken, ``categories/any(...)`` filters answer), and a
contact folder is not, since deleting one deletes its contacts. iCloud keeps a group as a card of
its own, naming its members by the UID of theirs, and that card is no contact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import vobject

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.microsoft_contact_groups_mixin import category_group_id
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.normalizers.contact_group_cards import (
    card_with_members,
    group_card,
    renamed_group_card,
)
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    normalize_vcard,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class TestGoogle:
    def _client(self, *answers: Any) -> tuple[GooglePeopleClient, AsyncMock]:
        client = GooglePeopleClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(side_effect=list(answers))
        client._make_request = request
        client._get_cache = AsyncMock(
            return_value=MagicMock(invalidate_user=AsyncMock(), set_details=AsyncMock())
        )
        return client, request

    async def test_its_people_are_read_with_the_group_s_own_count(self) -> None:
        client, request = self._client(
            {"memberResourceNames": ["people/c1"], "memberCount": 3},
            {"responses": [{"person": {"resourceName": "people/c1"}}]},
        )

        found = await client.group_people("contactGroups/f", 200, fields=["names"])

        assert found == {"people": [{"resourceName": "people/c1"}], "cut": True}
        assert request.await_args_list[1].kwargs["params"]["personFields"] == "names"

    async def test_a_group_of_nobody_reads_nobody(self) -> None:
        client, request = self._client({"memberCount": 0})

        assert await client.group_people("contactGroups/f", 200) == {"people": [], "cut": False}
        assert request.await_count == 1

    async def test_the_groups_of_a_contact_are_its_memberships(self) -> None:
        memberships = [
            {"contactGroupMembership": {"contactGroupResourceName": "contactGroups/f"}},
            {"domainMembership": {"inViewerDomain": True}},
        ]
        family = {"resourceName": "contactGroups/f", "formattedName": "Family"}
        other = {"resourceName": "contactGroups/o", "formattedName": "Other"}
        client, _ = self._client({"memberships": memberships}, {"contactGroups": [family, other]})

        assert await client.groups_of_contact("people/c1") == [family]

    async def test_a_group_is_made(self) -> None:
        client, request = self._client({"resourceName": "contactGroups/n", "name": "Family"})

        made = await client.create_contact_group("Family")

        assert made["resourceName"] == "contactGroups/n"
        assert request.await_args.args == ("POST", "/contactGroups")
        assert request.await_args.kwargs["json_data"] == {"contactGroup": {"name": "Family"}}

    async def test_a_group_is_renamed(self) -> None:
        client, request = self._client({})

        await client.rename_contact_group("contactGroups/f", "Friends")

        assert request.await_args.args == ("PUT", "/contactGroups/f")
        assert request.await_args.kwargs["json_data"] == {"contactGroup": {"name": "Friends"}}

    async def test_a_group_goes_and_its_contacts_stay(self) -> None:
        client, request = self._client({})

        await client.delete_contact_group("contactGroups/f")

        assert request.await_args.args == ("DELETE", "/contactGroups/f")
        assert request.await_args.kwargs["params"] == {"deleteContacts": "false"}

    async def test_members_come_and_go_in_one_request(self) -> None:
        client, request = self._client({})

        await client.change_group_members(
            "contactGroups/f", add=["people/c1"], remove=["people/c2"]
        )

        assert request.await_args.args == ("POST", "/contactGroups/f/members:modify")
        assert request.await_args.kwargs["json_data"] == {
            "resourceNamesToAdd": ["people/c1"],
            "resourceNamesToRemove": ["people/c2"],
        }

    @pytest.mark.parametrize("name", ["people/c1", "contactGroups/f:batch", "../x"])
    async def test_a_name_of_another_shape_reaches_no_one(self, name: str) -> None:
        client, request = self._client({})

        with pytest.raises(ConnectorAPIError):
            await client.delete_contact_group(name)

        request.assert_not_awaited()


class TestGraph:
    family = category_group_id("Family")

    def _client(self, *answers: Any) -> tuple[MicrosoftContactsClient, AsyncMock]:
        client = MicrosoftContactsClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(side_effect=list(answers))
        client._make_request = request
        return client, request

    async def test_the_groups_are_the_categories_contacts_carry_counted(self) -> None:
        client, request = self._client(
            {
                "value": [{"categories": ["Family"]}, {"categories": ["Family", "Work"]}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/contacts?$skip=2",
            },
            {"value": [{"categories": ["Work"]}]},
        )

        answer = await client.list_contact_groups()

        groups = {item["formattedName"]: item for item in answer["contactGroups"]}
        assert groups["Family"]["memberCount"] == 2
        assert groups["Work"]["memberCount"] == 2
        assert groups["Family"]["groupType"] == "USER_CONTACT_GROUP"
        assert request.await_args_list[0].kwargs["params"]["$filter"] == "categories/any()"

    async def test_a_scan_cut_by_its_bound_claims_no_count(self) -> None:
        pages = [
            {"value": [{"categories": ["Family"]}], "@odata.nextLink": "https://g/?$skip=1"}
            for _ in range(200)
        ]
        client, _ = self._client(*pages)

        answer = await client.list_contact_groups()

        assert answer["contactGroups"][0]["memberCount"] is None

    async def test_its_people_are_read_by_the_category_quoted(self) -> None:
        client, request = self._client({"value": [{"id": "c1", "displayName": "Ana"}]})

        found = await client.group_people(category_group_id("Bob's"), 200)

        assert request.await_args.kwargs["params"]["$filter"] == ("categories/any(a:a eq 'Bob''s')")
        assert found["people"][0]["resourceName"] == "people/c1"
        assert found["cut"] is False

    async def test_a_group_past_the_bound_says_so(self) -> None:
        client, _ = self._client(
            {"value": [{"id": "c1"}], "@odata.nextLink": "https://g/?$skip=1"},
        )

        found = await client.group_people(self.family, 1)

        assert found["cut"] is True

    async def test_the_groups_of_a_contact_are_its_categories(self) -> None:
        client, request = self._client({"categories": ["Family"]})

        found = await client.groups_of_contact("people/c1")

        assert [(item["resourceName"], item["formattedName"]) for item in found] == [
            (self.family, "Family")
        ]
        assert request.await_count == 1, "opening a contact never scans the address book"

    async def test_a_group_exists_once_someone_is_in_it(self) -> None:
        client, request = self._client()

        made = await client.create_contact_group("Family")

        assert made["resourceName"] == self.family
        request.assert_not_awaited()

    async def test_a_member_keeps_the_categories_it_had(self) -> None:
        client, request = self._client({"categories": ["Work"]}, {})

        await client.change_group_members(self.family, add=["people/c1"], remove=[])

        assert request.await_args.args == ("PATCH", "/me/contacts/c1")
        assert request.await_args.kwargs["json_data"] == {"categories": ["Work", "Family"]}

    async def test_a_member_already_in_is_not_written_again(self) -> None:
        client, request = self._client({"categories": ["Family"]})

        await client.change_group_members(self.family, add=["people/c1"], remove=[])

        assert request.await_count == 1

    async def test_a_member_leaves_and_keeps_the_others(self) -> None:
        client, request = self._client({"categories": ["Work", "Family"]}, {})

        await client.change_group_members(self.family, add=[], remove=["people/c1"])

        assert request.await_args.kwargs["json_data"] == {"categories": ["Work"]}

    async def test_a_rename_rewrites_each_member(self) -> None:
        client, request = self._client(
            {"value": [{"id": "c1", "categories": ["Family", "Work"]}]}, {}
        )

        await client.rename_contact_group(self.family, "Kin")

        assert request.await_args.args == ("PATCH", "/me/contacts/c1")
        assert request.await_args.kwargs["json_data"] == {"categories": ["Kin", "Work"]}

    async def test_a_group_goes_from_each_member_and_nobody_is_deleted(self) -> None:
        client, request = self._client({"value": [{"id": "c1", "categories": ["Family"]}]}, {})

        await client.delete_contact_group(self.family)

        methods = [call.args[0] for call in request.await_args_list]
        assert methods == ["GET", "PATCH"]
        assert request.await_args.kwargs["json_data"] == {"categories": []}

    @pytest.mark.parametrize("name", ["contactGroups/f", "category:%%%", "category:"])
    async def test_an_id_it_did_not_mint_names_nothing(self, name: str) -> None:
        client, request = self._client()

        with pytest.raises(ConnectorAPIError):
            await client.delete_contact_group(name)

        request.assert_not_awaited()


class TestACard:
    def test_a_group_card_says_what_it_is(self) -> None:
        card = vobject.readOne(group_card("Family", "u1"))

        assert card.fn.value == "Family"
        assert card.uid.value == "u1"
        assert card.contents["x-addressbookserver-kind"][0].value == "group"

    def test_members_are_named_by_their_uid(self) -> None:
        text = card_with_members(group_card("Family", "u1"), add=["a", "b"], remove=[])

        person = normalize_vcard(text, "/g.vcf")

        assert person["isGroup"] is True
        assert person["groupMembers"] == ["a", "b"]

    def test_a_member_leaves_and_the_others_stay(self) -> None:
        text = card_with_members(group_card("Family", "u1"), add=["a", "b"], remove=[])

        left = card_with_members(text, add=[], remove=["a"])

        assert normalize_vcard(left)["groupMembers"] == ["b"]

    def test_a_member_is_never_named_twice(self) -> None:
        text = card_with_members(group_card("Family", "u1"), add=["a"], remove=[])

        again = card_with_members(text, add=["a"], remove=[])

        assert normalize_vcard(again)["groupMembers"] == ["a"]

    def test_a_rename_keeps_the_members(self) -> None:
        text = card_with_members(group_card("Family", "u1"), add=["a"], remove=[])

        renamed = normalize_vcard(renamed_group_card(text, "Kin"))

        assert renamed["names"][0]["displayName"] == "Kin"
        assert renamed["groupMembers"] == ["a"]

    def test_a_contact_is_no_group_and_keeps_its_uid(self) -> None:
        text = build_vcard("Ana Lima").replace("END:VCARD", "UID:abc\r\nEND:VCARD")

        person = normalize_vcard(text)

        assert "isGroup" not in person
        assert person["uid"] == "abc"


class TestApple:
    def _client(self, book: list[dict[str, Any]], card: str = "") -> tuple[Any, MagicMock]:
        http = MagicMock(
            get=AsyncMock(return_value=MagicMock(status_code=200, text=card)),
            put=AsyncMock(return_value=MagicMock(status_code=201)),
            delete=AsyncMock(return_value=MagicMock(status_code=204)),
        )
        client = AppleContactsClient.__new__(AppleContactsClient)
        client.user_id = uuid4()
        client._get_http_client = AsyncMock(return_value=http)
        client._execute_with_retry = _straight
        client._invalidate_contacts_cache = AsyncMock()
        client._discover_addressbook = AsyncMock(return_value="/addressbook/")
        client._get_all_contacts_cached = AsyncMock(return_value=(book, False, None))
        return client, http

    book = [
        {"resourceName": "/a.vcf", "uid": "a", "names": [{"displayName": "Ana"}]},
        {"resourceName": "/b.vcf", "uid": "b", "names": [{"displayName": "Bea"}]},
        {
            "resourceName": "/g.vcf",
            "uid": "g",
            "isGroup": True,
            "groupMembers": ["a"],
            "names": [{"displayName": "Family"}],
        },
    ]

    async def test_the_groups_are_the_group_cards_counted(self) -> None:
        client, _ = self._client(self.book)

        answer = await client.list_contact_groups()

        assert answer["contactGroups"] == [
            {
                "resourceName": "/g.vcf",
                "formattedName": "Family",
                "groupType": "USER_CONTACT_GROUP",
                "memberCount": 1,
            }
        ]

    async def test_its_people_are_those_it_names(self) -> None:
        client, _ = self._client(self.book)

        found = await client.group_people("/g.vcf", 200)

        assert [person["uid"] for person in found["people"]] == ["a"]
        assert found["cut"] is False

    async def test_a_group_past_the_bound_says_so(self) -> None:
        book = [*self.book[:2], {**self.book[2], "groupMembers": ["a", "b"]}]
        client, _ = self._client(book)

        found = await client.group_people("/g.vcf", 1)

        assert len(found["people"]) == 1 and found["cut"] is True

    async def test_the_groups_of_a_contact_name_it(self) -> None:
        client, _ = self._client(self.book)

        found = await client.groups_of_contact("/a.vcf")

        assert [item["formattedName"] for item in found] == ["Family"]
        assert await client.groups_of_contact("/b.vcf") == []

    async def test_opening_a_contact_reads_the_kept_book_and_a_write_a_fresh_one(self) -> None:
        client, _ = self._client(self.book, group_card("Family", "g"))

        await client.groups_of_contact("/a.vcf")
        await client.list_contact_groups()
        assert [call.args[0] for call in client._get_all_contacts_cached.await_args_list] == [
            True,
            True,
        ]

        client._get_all_contacts_cached.reset_mock()
        await client.change_group_members("/g.vcf", add=["/b.vcf"], remove=[])
        assert client._get_all_contacts_cached.await_args.args[0] is False

    async def test_a_group_is_a_new_card(self) -> None:
        client, http = self._client(self.book)

        made = await client.create_contact_group("Kin")

        url = http.put.await_args.args[0]
        assert url.startswith("/addressbook/") and url.endswith(".vcf")
        assert made["resourceName"] == url
        assert normalize_vcard(http.put.await_args.kwargs["content"])["isGroup"] is True

    async def test_a_member_is_named_by_the_uid_of_its_card(self) -> None:
        client, http = self._client(self.book, group_card("Family", "g"))

        await client.change_group_members("/g.vcf", add=["/b.vcf"], remove=[])

        written = http.put.await_args.kwargs["content"]
        assert normalize_vcard(written)["groupMembers"] == ["b"]

    async def test_a_contact_nobody_knows_is_refused_and_nothing_written(self) -> None:
        client, http = self._client(self.book, group_card("Family", "g"))

        with pytest.raises(ValueError):
            await client.change_group_members("/g.vcf", add=["/nobody.vcf"], remove=[])

        http.put.assert_not_awaited()

    async def test_a_group_goes_and_only_its_card_with_it(self) -> None:
        client, http = self._client(self.book)

        await client.delete_contact_group("/g.vcf")

        http.delete.assert_awaited_once()
        assert http.delete.await_args.args[0].endswith("/g.vcf")

    async def test_a_contact_is_never_taken_for_a_group(self) -> None:
        client, http = self._client(self.book)

        with pytest.raises(ValueError):
            await client.delete_contact_group("/a.vcf")

        http.delete.assert_not_awaited()

    async def test_a_group_card_is_no_contact_in_a_listing(self) -> None:
        client, _ = self._client(self.book)

        listing = await client._list_connections_impl(25, None, True, None)
        found = await client._search_contacts_impl("family", 25, True, None)

        assert [person["uid"] for person in listing["connections"]] == ["a", "b"]
        assert found["results"] == []


async def _straight(_name: str, function: Any, *args: Any, **kwargs: Any) -> Any:
    return await function(*args, **kwargs)
