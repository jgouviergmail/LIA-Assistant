"""A contacts listing is sorted by family then given name, on every provider (ADR-369).

Owner request 2026-10-31. A cursor-paged listing can only be ordered where it is paged:
Google sorts its own pages (``LAST_NAME_ASCENDING``) and so does Graph (its test sits with
its client); iCloud, read whole anyway, sorts by ``contact_order_key`` before it pages, so a
page follows the one before it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient

pytestmark = pytest.mark.unit


def _person(given: str, family: str) -> dict[str, Any]:
    return {
        "resourceName": f"people/{given.lower()}",
        "names": [{"displayName": f"{given} {family}", "givenName": given, "familyName": family}],
    }


async def test_google_sorts_its_pages_by_family_name() -> None:
    client = GooglePeopleClient.__new__(GooglePeopleClient)
    client.user_id = uuid4()
    client._get_cache = AsyncMock(  # type: ignore[method-assign]
        return_value=MagicMock(get_list=AsyncMock(), set_list=AsyncMock())
    )
    request = AsyncMock(return_value={"connections": []})
    client._make_request = request  # type: ignore[method-assign]

    await client.list_connections(page_size=25, page_token="p2", use_cache=False)

    params = request.await_args.kwargs["params"]
    assert params["sortOrder"] == "LAST_NAME_ASCENDING"
    assert params["pageToken"] == "p2"


async def test_icloud_pages_the_book_in_family_then_given_order() -> None:
    client = AppleContactsClient.__new__(AppleContactsClient)
    book = [
        _person("Zoé", "Martin"),
        _person("Mathéo", "Garnet"),
        _person("Anne", "Martin"),
        _person("Hua", "Garnet"),
        _person("Bob", "Durand"),
    ]
    with patch.object(
        client, "_get_all_contacts_cached", AsyncMock(return_value=(book, False, None))
    ):
        first = await client._list_connections_impl(3, None, False, None)
        second = await client._list_connections_impl(3, first["nextPageToken"], False, None)

    shown = [
        person["names"][0]["displayName"]
        for person in [*first["connections"], *second["connections"]]
    ]
    assert shown == ["Bob Durand", "Hua Garnet", "Mathéo Garnet", "Anne Martin", "Zoé Martin"]
    assert (first["nextPageToken"], second["nextPageToken"]) == ("3", None)
