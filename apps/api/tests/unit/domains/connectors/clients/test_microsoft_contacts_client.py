"""Unit tests for MicrosoftContactsClient (Graph provider for the ``contacts`` category).

Zero coverage until now, while the contacts tools consume its payloads through
the Google People API shape. The invariants pinned here are the ones a silent
drift would break without any error surfacing:

- the ``{"person": ...}`` envelope on search (tools index ``results[i]["person"]``),
- the ``people/{id}`` resource-name round-trip used by read/update/delete,
- the global volumetry ceiling on both search and list.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> MicrosoftContactsClient:
    return MicrosoftContactsClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )


GRAPH_CONTACT = {
    "id": "AAMk-contact-1",
    "displayName": "Jane Doe",
    "givenName": "Jane",
    "surname": "Doe",
    "emailAddresses": [{"address": "jane.doe@example.com", "name": "Work"}],
    "businessPhones": ["+33123456789"],
    "mobilePhone": "+33612345678",
    "companyName": "ACME Corp",
    "jobTitle": "CTO",
}


def _request(client: MicrosoftContactsClient, response: dict) -> AsyncMock:
    mock = AsyncMock(return_value=response)
    client._make_request = mock  # type: ignore[method-assign]
    return mock


# ============================================================================
# SEARCH
# ============================================================================


class TestSearchContacts:
    """Graph ``$search`` results must reach the tools in People API shape."""

    async def test_wraps_results_in_the_person_envelope(
        self, client: MicrosoftContactsClient
    ) -> None:
        _request(client, {"value": [GRAPH_CONTACT]})

        result = await client.search_contacts("jane")

        assert result["totalItems"] == 1
        person = result["results"][0]["person"]
        assert person["names"][0]["displayName"] == "Jane Doe"
        assert person["resourceName"] == "people/AAMk-contact-1"

    async def test_quotes_the_search_term(self, client: MicrosoftContactsClient) -> None:
        request = _request(client, {"value": []})

        await client.search_contacts("jane doe")

        _method, endpoint, params = request.await_args.args
        assert endpoint == "/me/contacts"
        assert params["$search"] == '"jane doe"'

    async def test_applies_the_global_volumetry_cap(self, client: MicrosoftContactsClient) -> None:
        from src.domains.connectors.clients.base_google_client import apply_max_items_limit

        request = _request(client, {"value": []})

        await client.search_contacts("jane", max_results=10_000)

        _method, _endpoint, params = request.await_args.args
        assert params["$top"] == apply_max_items_limit(10_000)

    async def test_empty_result_set(self, client: MicrosoftContactsClient) -> None:
        _request(client, {"value": []})

        result = await client.search_contacts("nobody")

        assert result["results"] == []
        assert result["totalItems"] == 0

    async def test_declares_its_freshness_metadata(self, client: MicrosoftContactsClient) -> None:
        """Every contacts provider must state whether the payload came from a cache."""
        _request(client, {"value": []})

        result = await client.search_contacts("jane")

        assert result["from_cache"] is False
        assert result[FIELD_CACHED_AT] is None


# ============================================================================
# LIST
# ============================================================================


class TestListConnections:
    """Listing goes through the OData paginator and stays capped."""

    async def test_returns_normalised_connections(self, client: MicrosoftContactsClient) -> None:
        paginate = AsyncMock(return_value={"value": [{"resourceName": "people/1"}]})
        client._get_paginated_odata = paginate  # type: ignore[method-assign]

        result = await client.list_connections(page_size=50)

        assert result["connections"] == [{"resourceName": "people/1"}]
        assert result["totalItems"] == 1

    async def test_orders_by_display_name(self, client: MicrosoftContactsClient) -> None:
        paginate = AsyncMock(return_value={"value": []})
        client._get_paginated_odata = paginate  # type: ignore[method-assign]

        await client.list_connections()

        assert paginate.await_args.kwargs["params"]["$orderby"] == "displayName"

    async def test_applies_the_global_volumetry_cap(self, client: MicrosoftContactsClient) -> None:
        from src.domains.connectors.clients.base_google_client import apply_max_items_limit

        paginate = AsyncMock(return_value={"value": []})
        client._get_paginated_odata = paginate  # type: ignore[method-assign]

        await client.list_connections(page_size=10_000)

        assert paginate.await_args.kwargs["max_results"] == apply_max_items_limit(10_000)

    async def test_transform_normalises_each_item(self, client: MicrosoftContactsClient) -> None:
        """The transform callback is what turns Graph rows into People API rows."""
        captured: dict = {}

        async def _capture(**kwargs):
            captured["transform"] = kwargs["transform_items"]
            return {"value": []}

        client._get_paginated_odata = AsyncMock(side_effect=_capture)  # type: ignore[method-assign]

        await client.list_connections()

        normalised = captured["transform"]([GRAPH_CONTACT])
        assert normalised[0]["resourceName"] == "people/AAMk-contact-1"


# ============================================================================
# READ / WRITE — resource-name round-trip
# ============================================================================


class TestResourceNameRoundTrip:
    """``people/{id}`` is the tool-facing identifier; Graph wants the bare id."""

    async def test_get_person_strips_the_people_prefix(
        self, client: MicrosoftContactsClient
    ) -> None:
        request = _request(client, GRAPH_CONTACT)

        person = await client.get_person("people/AAMk-contact-1")

        _method, endpoint, _params = request.await_args.args
        assert endpoint == "/me/contacts/AAMk-contact-1"
        assert person["resourceName"] == "people/AAMk-contact-1"

    async def test_get_person_accepts_a_bare_id(self, client: MicrosoftContactsClient) -> None:
        request = _request(client, GRAPH_CONTACT)

        await client.get_person("AAMk-contact-1")

        _method, endpoint, _params = request.await_args.args
        assert endpoint == "/me/contacts/AAMk-contact-1"

    async def test_update_contact_patches_the_bare_id(
        self, client: MicrosoftContactsClient
    ) -> None:
        request = _request(client, GRAPH_CONTACT)

        await client.update_contact("people/AAMk-contact-1", email="new@example.com")

        method, endpoint = request.await_args.args
        assert method == "PATCH"
        assert endpoint == "/me/contacts/AAMk-contact-1"

    async def test_delete_contact_deletes_the_bare_id(
        self, client: MicrosoftContactsClient
    ) -> None:
        request = _request(client, {})

        assert await client.delete_contact("people/AAMk-contact-1") is True

        method, endpoint = request.await_args.args
        assert method == "DELETE"
        assert endpoint == "/me/contacts/AAMk-contact-1"

    async def test_create_contact_posts_a_graph_body(self, client: MicrosoftContactsClient) -> None:
        request = _request(client, GRAPH_CONTACT)

        result = await client.create_contact(
            "Jane Doe", email="jane.doe@example.com", organization="ACME Corp"
        )

        method, endpoint = request.await_args.args
        body = request.await_args.kwargs["json_data"]
        assert (method, endpoint) == ("POST", "/me/contacts")
        assert body["displayName"] == "Jane Doe"
        assert result["resourceName"] == "people/AAMk-contact-1"
