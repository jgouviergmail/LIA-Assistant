"""People API otherContacts + contactGroups client contract (lot C, 2026-08).

The `contacts.other.readonly` scope has been granted since the first OAuth
version but the endpoints were never called (2026-08 audit): "other contacts"
(people interacted with but never saved) and contact groups (family,
colleagues) are first-class People API data LIA ignored.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import GOOGLE_OTHER_CONTACTS_FIELDS
from src.domains.connectors.clients.google_people_client import GooglePeopleClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> GooglePeopleClient:
    instance = GooglePeopleClient.__new__(GooglePeopleClient)
    instance.user_id = uuid4()
    return instance


@pytest.fixture
def request_spy(client: GooglePeopleClient) -> AsyncMock:
    spy = AsyncMock(return_value={})
    client._make_request = spy  # type: ignore[method-assign]
    return spy


class TestSearchOtherContacts:
    async def test_calls_search_endpoint_with_supported_read_mask(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        """otherContacts only supports emailAddresses/names/phoneNumbers —
        any other field is a 400 from Google."""
        request_spy.return_value = {"results": [{"person": {"names": []}}]}
        result = await client.search_other_contacts("marc")

        assert request_spy.call_args.args[:2] == ("GET", "/otherContacts:search")
        params = request_spy.call_args.kwargs["params"]
        assert params["query"] == "marc"
        assert set(params["readMask"].split(",")) == set(GOOGLE_OTHER_CONTACTS_FIELDS)
        assert result["results"] == [{"person": {"names": []}}]

    async def test_page_size_is_capped(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        await client.search_other_contacts("marc", max_results=500)
        params = request_spy.call_args.kwargs["params"]
        assert params["pageSize"] <= 50


class TestListContactGroups:
    async def test_calls_contact_groups_endpoint(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        request_spy.return_value = {"contactGroups": [{"resourceName": "contactGroups/x"}]}
        result = await client.list_contact_groups()
        assert request_spy.call_args.args[:2] == ("GET", "/contactGroups")
        assert result["contactGroups"] == [{"resourceName": "contactGroups/x"}]


class TestGetContactGroup:
    async def test_fetches_group_with_members(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        await client.get_contact_group("contactGroups/abc", max_members=50)
        assert request_spy.call_args.args[:2] == ("GET", "/contactGroups/abc")
        assert request_spy.call_args.kwargs["params"]["maxMembers"] == 50


class TestGetPeopleBatch:
    async def test_batch_get_with_resource_names_and_fields(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        await client.get_people_batch(["people/1", "people/2"], fields=["names", "emailAddresses"])
        assert request_spy.call_args.args[:2] == ("GET", "/people:batchGet")
        params = request_spy.call_args.kwargs["params"]
        assert params["resourceNames"] == ["people/1", "people/2"]
        assert params["personFields"] == "names,emailAddresses"

    async def test_empty_resource_names_short_circuits_without_api_call(
        self, client: GooglePeopleClient, request_spy: AsyncMock
    ) -> None:
        result = await client.get_people_batch([])
        assert result == {"responses": []}
        request_spy.assert_not_called()
