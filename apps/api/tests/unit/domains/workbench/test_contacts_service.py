"""The contacts of the « Tools » section (ADR-369, Task 7.1, D4).

The account's contacts by cursor; a search and a group, which the provider
answers in one go, say when they may hold more. A contact's lists are typed:
a list sent replaces that list, a list left out is kept, and a list the
provider cannot hold is refused whole with its bound. A stale change is a
conflict; a contact gone is gone. Groups and « other contacts » are Google's.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.constants import (
    GOOGLE_CONTACTS_SEARCH_PAGE_MAX,
    WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
)
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.normalizers.contact_values import ContactValuesRefused
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import availability, contacts_service
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.schemas.contacts import ContactChange, ContactsQuery, NewContact

pytestmark = pytest.mark.unit

USER = uuid4()
GOOGLE, GRAPH, CARDDAV = (
    ConnectorType.GOOGLE_CONTACTS,
    ConnectorType.MICROSOFT_CONTACTS,
    ConnectorType.APPLE_CONTACTS,
)
KEY = "11111111-1111-4111-8111-111111111111"


def _door(client: Any, kind: ConnectorType) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(contacts_service, "open_tool_client", opened)


def _person(resource: str = "people/c1", **overrides: Any) -> dict[str, Any]:
    return {
        "resourceName": resource,
        "names": [{"displayName": "Ana Lima"}],
        "emailAddresses": [
            {"value": "ana@example.org", "type": "work"},
            {"value": "ana@home.example", "type": "home"},
        ],
        "phoneNumbers": [{"value": "+33 6 12 34 56 78", "type": "mobile"}],
        "addresses": [{"formattedValue": "1 rue de la Paix, Paris", "type": "home"}],
        "organizations": [{"name": "Atlas"}],
        "biographies": [{"value": "Met at the fair."}],
        **overrides,
    }


class TestTheList:
    async def test_the_account_s_contacts_by_cursor_read_fresh(self) -> None:
        client = MagicMock(
            list_connections=AsyncMock(
                return_value={"connections": [_person()], "nextPageToken": "p2"}
            )
        )
        with _door(client, GOOGLE):
            page = await contacts_service.list_contacts(USER, ContactsQuery(page_token="p1"))

        client.list_connections.assert_awaited_once_with(
            page_size=listing_page_size(), page_token="p1", use_cache=False
        )
        (row,) = page.items
        assert (row.id, row.name, row.email, row.phone, row.organization) == (
            "people/c1",
            "Ana Lima",
            "ana@example.org",
            "+33 6 12 34 56 78",
            "Atlas",
        )
        assert (page.next_page_token, page.truncated) == ("p2", False)

    async def test_graph_s_cursor_is_read_too(self) -> None:
        client = MagicMock(
            list_connections=AsyncMock(return_value={"connections": [], "next_page_token": "g2"})
        )
        with _door(client, GRAPH):
            page = await contacts_service.list_contacts(USER, ContactsQuery())

        assert page.next_page_token == "g2"

    async def test_a_search_says_when_it_answered_a_full_page(self) -> None:
        full = [{"person": _person(f"people/c{index}")} for index in range(listing_page_size())]
        client = MagicMock(search_contacts=AsyncMock(return_value={"results": full}))
        with _door(client, CARDDAV):
            page = await contacts_service.list_contacts(USER, ContactsQuery(q="ana"))

        client.search_contacts.assert_awaited_once_with(
            "ana", max_results=listing_page_size(), use_cache=False
        )
        assert (len(page.items), page.next_page_token, page.truncated) == (
            listing_page_size(),
            None,
            True,
        )

    @pytest.mark.parametrize("search", ["search_contacts", "search_other_contacts"])
    async def test_a_search_is_cut_at_google_s_own_cap_and_says_so(
        self, search: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Google answers at most GOOGLE_CONTACTS_SEARCH_PAGE_MAX results whatever it is
        # asked: a page set larger would read a full answer as the whole.
        monkeypatch.setattr(availability.settings, "workbench_page_size", 50)
        monkeypatch.setattr(availability.settings, "api_max_items_per_request", 50)
        cap = GOOGLE_CONTACTS_SEARCH_PAGE_MAX
        full = [{"person": _person(f"people/c{index}")} for index in range(cap)]
        client = MagicMock(**{search: AsyncMock(return_value={"results": full})})
        with _door(client, GOOGLE):
            if search == "search_contacts":
                page = await contacts_service.list_contacts(USER, ContactsQuery(q="ana"))
            else:
                page = await contacts_service.search_other(USER, "ana")

        getattr(client, search).assert_awaited_once_with("ana", max_results=cap, use_cache=False)
        assert (len(page.items), page.truncated) == (cap, True)

    async def test_a_group_is_paged_through_its_members_and_its_cut_said(self) -> None:
        # Google lists a group's members in no order: the whole group (read at most
        # GOOGLE_CONTACT_GROUP_MAX_MEMBERS, one batch) is sorted, THEN paged — by family,
        # then given name (owner request 2026-10-31).
        members = [f"people/m{index:02d}" for index in range(30)]
        people = [
            _person(name, names=[{"givenName": "Ana", "familyName": f"Z{29 - index:02d}"}])
            for index, name in enumerate(members)
        ]
        client = MagicMock(
            get_contact_group=AsyncMock(
                return_value={"memberResourceNames": members, "memberCount": 40}
            ),
            get_people_batch=AsyncMock(
                return_value={"responses": [{"person": person} for person in people]}
            ),
        )
        with _door(client, GOOGLE):
            page = await contacts_service.list_contacts(
                USER, ContactsQuery(group="contactGroups/friends", page_token="25")
            )

        assert client.get_people_batch.await_args.args[0] == members
        assert [row.family_name for row in page.items] == ["Z25", "Z26", "Z27", "Z28", "Z29"]
        assert (len(page.items), page.next_page_token, page.truncated) == (5, None, True)

    async def test_a_contact_carries_its_given_and_family_names(self) -> None:
        """The list draws « Given Family » (owner request 2026-10-31)."""
        person = _person(
            names=[{"displayName": "Lima, Ana", "givenName": "Ana", "familyName": "Lima"}]
        )
        client = MagicMock(list_connections=AsyncMock(return_value={"connections": [person]}))
        with _door(client, GRAPH):
            page = await contacts_service.list_contacts(USER, ContactsQuery())

        (row,) = page.items
        assert (row.name, row.given_name, row.family_name) == ("Lima, Ana", "Ana", "Lima")

    async def test_a_search_comes_back_by_family_then_given_name(self) -> None:
        found = [
            {
                "person": _person(
                    f"people/{given}", names=[{"givenName": given, "familyName": family}]
                )
            }
            for given, family in (("Zoé", "Martin"), ("Hua", "Garnet"), ("Anne", "Martin"))
        ]
        client = MagicMock(search_contacts=AsyncMock(return_value={"results": found}))
        with _door(client, GOOGLE):
            page = await contacts_service.list_contacts(USER, ContactsQuery(q="a"))

        assert [(row.given_name, row.family_name) for row in page.items] == [
            ("Hua", "Garnet"),
            ("Anne", "Martin"),
            ("Zoé", "Martin"),
        ]

    async def test_a_group_or_other_contacts_where_the_provider_has_none(self) -> None:
        client = MagicMock()
        with _door(client, GRAPH), pytest.raises(BaseAPIException) as caught:
            await contacts_service.list_contacts(USER, ContactsQuery(group="contactGroups/x"))
        assert caught.value.detail["code"] == "not_supported_by_provider"
        with _door(client, CARDDAV), pytest.raises(BaseAPIException):
            await contacts_service.list_groups(USER)
        with _door(client, GRAPH), pytest.raises(BaseAPIException):
            await contacts_service.search_other(USER, "ana")

    def test_a_search_inside_a_group_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ContactsQuery(q="ana", group="contactGroups/x")


class TestOneContact:
    async def test_a_contact_is_read_whole_and_typed(self) -> None:
        client = MagicMock(get_person=AsyncMock(return_value=_person()))
        with _door(client, GOOGLE):
            contact = await contacts_service.read_contact(USER, "people/c1")

        client.get_person.assert_awaited_once_with("people/c1", use_cache=False)
        assert [(e.value, e.type) for e in contact.emails] == [
            ("ana@example.org", "work"),
            ("ana@home.example", "home"),
        ]
        assert contact.addresses[0].formatted == "1 rue de la Paix, Paris"
        assert contact.notes == "Met at the fair."

    async def test_a_contact_is_read_as_its_provider_wrote_it(self) -> None:
        # Google writes a postal address on several lines and keeps a kind the person
        # typed: read with the WRITE rules, both made the detail a 500 (measured on
        # dev, 2026-10-31: « ContactAddress formatted should match pattern »).
        lines = "3 place de la Bourse\n69002 Lyon\nFrance"
        person = _person(
            addresses=[{"formattedValue": lines, "type": "Bureau de Lyon"}],
            phoneNumbers=[{"value": "+33 6 12 34 56 78", "type": "Portable (perso)"}],
            emailAddresses=[{"value": "ana@example.org", "type": "Travail – équipe"}],
        )
        client = MagicMock(get_person=AsyncMock(return_value=person))
        with _door(client, GOOGLE):
            contact = await contacts_service.read_contact(USER, "people/c1")

        assert [(a.formatted, a.type) for a in contact.addresses] == [(lines, "Bureau de Lyon")]
        assert contact.phones[0].type == "Portable (perso)"
        assert contact.emails[0].type == "Travail – équipe"

    def test_an_address_keeps_its_lines_and_a_kind_any_script_on_the_way_in(self) -> None:
        lines = "3 place de la Bourse\r\n69002 Lyon"
        change = ContactChange.model_validate(
            {
                "id": "people/c1",
                "addresses": [{"formatted": lines, "type": "Bureau de Lyon"}],
                "phones": [{"value": "+33 1 00", "type": "Téléphone (fixe)"}],
            }
        )

        assert change.addresses is not None and change.addresses[0].formatted == lines
        assert change.phones is not None and change.phones[0].type == "Téléphone (fixe)"

    @pytest.mark.parametrize(
        "lists",
        [
            {"emails": [{"value": "ana@example.org\nbcc: x@example.org"}]},
            {"phones": [{"value": "+33\t1 00"}]},
            {"addresses": [{"formatted": "3 place\x07de la Bourse"}]},
            {"addresses": [{"formatted": "x" * (WORKBENCH_CONTACT_ADDRESS_MAX_CHARS + 1)}]},
            {"phones": [{"value": "+33 1 00", "type": "Portable\nperso"}]},
        ],
    )
    def test_a_value_breaking_its_shape_is_refused(self, lists: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            ContactChange.model_validate({"id": "people/c1", **lists})

    async def test_a_new_contact_is_created_once_with_its_typed_lists(self) -> None:
        client = MagicMock(create_contact=AsyncMock(return_value=_person()))
        request = NewContact.model_validate(
            {
                "name": "Ana Lima",
                "emails": [{"value": "ana@example.org", "type": "work"}],
                "phones": [],
                "idempotency_key": KEY,
            }
        )
        keys: list[Any] = []

        async def once(user_id: Any, key: Any, operation: Any, **kwargs: Any) -> Any:
            keys.append(key)
            return await operation()

        with _door(client, GOOGLE), patch.object(contacts_service, "run_once", once):
            await contacts_service.create_contact(USER, request)

        assert keys == [request.idempotency_key]
        kwargs = client.create_contact.await_args.kwargs
        assert kwargs["emails"] == [{"value": "ana@example.org", "type": "work"}]
        assert kwargs["phones"] == []

    async def test_a_change_sends_only_the_lists_it_names(self) -> None:
        client = MagicMock(update_contact=AsyncMock(return_value=_person()))
        change = ContactChange.model_validate(
            {"id": "people/c1", "phones": [{"value": "+33 1 00", "type": "work"}]}
        )
        with _door(client, GOOGLE):
            await contacts_service.update_contact(USER, change)

        kwargs = client.update_contact.await_args.kwargs
        assert kwargs["phones"] == [{"value": "+33 1 00", "type": "work"}]
        assert kwargs["emails"] is None and kwargs["addresses"] is None

    async def test_a_list_the_provider_cannot_hold_is_refused_with_its_bound(self) -> None:
        client = MagicMock(update_contact=AsyncMock(side_effect=ContactValuesRefused("emails", 3)))
        change = ContactChange.model_validate(
            {"id": "c1", "emails": [{"value": f"a{i}@example.org"} for i in range(4)]}
        )
        with _door(client, GRAPH), pytest.raises(BaseAPIException) as caught:
            await contacts_service.update_contact(USER, change)

        assert caught.value.detail == {
            "code": "not_supported_by_provider",
            "bound": 3,
            "field": "emails",
        }

    async def test_a_stale_change_is_a_conflict(self) -> None:
        stale = ConnectorAPIError(connector_type="apple_contacts", status_code=412, detail="x")
        client = MagicMock(update_contact=AsyncMock(side_effect=stale))
        with _door(client, CARDDAV), pytest.raises(BaseAPIException) as caught:
            await contacts_service.update_contact(
                USER, ContactChange.model_validate({"id": "c1", "name": "Ana"})
            )

        assert caught.value.detail["code"] == "conflict"

    async def test_a_contact_gone_is_said_gone(self) -> None:
        gone = ConnectorAPIError(connector_type="google_contacts", status_code=404, detail="x")
        client = MagicMock(delete_contact=AsyncMock(side_effect=gone))
        with _door(client, GOOGLE), pytest.raises(BaseAPIException) as caught:
            await contacts_service.delete_contact(USER, "people/c1")

        assert caught.value.detail["code"] == "item_gone"

    def test_a_change_naming_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ContactChange.model_validate({"id": "c1"})


class TestGoogleOnly:
    async def test_the_person_s_groups_come_first(self) -> None:
        client = MagicMock(
            list_contact_groups=AsyncMock(
                return_value={
                    "contactGroups": [
                        {
                            "resourceName": "contactGroups/myContacts",
                            "formattedName": "My contacts",
                            "groupType": "SYSTEM_CONTACT_GROUP",
                        },
                        {
                            "resourceName": "contactGroups/f",
                            "name": "Friends",
                            "memberCount": 7,
                            "groupType": "USER_CONTACT_GROUP",
                        },
                    ]
                }
            )
        )
        with _door(client, GOOGLE):
            groups = await contacts_service.list_groups(USER)

        assert [(g.id, g.name, g.count) for g in groups.groups] == [
            ("contactGroups/f", "Friends", 7),
            ("contactGroups/myContacts", "My contacts", None),
        ]

    async def test_other_contacts_are_searched_fresh(self) -> None:
        client = MagicMock(
            search_other_contacts=AsyncMock(return_value={"results": [{"person": _person()}]})
        )
        with _door(client, GOOGLE):
            page = await contacts_service.search_other(USER, "ana")

        client.search_other_contacts.assert_awaited_once_with(
            "ana", max_results=listing_page_size(), use_cache=False
        )
        assert page.items[0].email == "ana@example.org"
