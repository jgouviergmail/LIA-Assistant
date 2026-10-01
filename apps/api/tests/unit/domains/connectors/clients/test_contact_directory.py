"""The whole address book, read the same way on every contacts provider.

``list_email_directory`` feeds the recipient suggestions of « Send by e-mail »,
which match names and numbers themselves because the providers' own searches
disagree. What is pinned here is what each provider requires of a whole read,
and what the caller is told when the book is longer than its cap.
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.constants import (
    GOOGLE_PEOPLE_CONNECTIONS_PAGE_SIZE_MAX,
    MICROSOFT_CONTACTS_DIRECTORY_PAGE_SIZE,
)
from src.domains.connectors.clients import contact_directory
from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.contact_directory import (
    DirectoryStamp,
    cached_directory,
    compact_person,
    directory_stamp,
    invalidate_contacts_cache,
)
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.models import ConnectorType
from src.infrastructure.utils import shared_flight

pytestmark = pytest.mark.unit


class MemoryRedis:
    """The four calls ``ContactsCache`` makes, over a dict."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        """The compare-and-delete release of a claim."""
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        return sum(1 for key in keys if self.store.pop(key, None) is not None)

    async def scan(self, cursor: int, match: str, count: int) -> tuple[int, list[str]]:
        return 0, [key for key in self.store if fnmatch.fnmatch(key, match)]


@pytest.fixture
def redis() -> Iterator[MemoryRedis]:
    memory = MemoryRedis()
    with (
        patch.object(contact_directory, "get_redis_cache", AsyncMock(return_value=memory)),
        patch.object(shared_flight, "get_redis_cache", AsyncMock(return_value=memory)),
    ):
        yield memory


def _person(index: int) -> dict[str, Any]:
    return {"names": [{"displayName": f"Person {index}"}]}


def _google(user_id: UUID) -> GooglePeopleClient:
    client = GooglePeopleClient.__new__(GooglePeopleClient)
    client.user_id = user_id
    client.connector_type = ConnectorType.GOOGLE_CONTACTS
    return client


def _microsoft(user_id: UUID) -> MicrosoftContactsClient:
    client = MicrosoftContactsClient.__new__(MicrosoftContactsClient)
    client.user_id = user_id
    client.connector_type = ConnectorType.MICROSOFT_CONTACTS
    return client


class TestGoogle:
    async def test_pages_keep_every_parameter_but_the_token(self, redis: MemoryRedis) -> None:
        """Google refuses a page whose parameters differ from the first call's."""
        client = _google(uuid4())
        pages = [
            {"connections": [_person(1), _person(2)], "nextPageToken": "t1"},
            {"connections": [_person(3)]},
        ]
        request = AsyncMock(side_effect=pages)

        with patch.object(client, "_make_request", request):
            directory = await client.list_email_directory(5000)

        first, second = (call.kwargs["params"] for call in request.call_args_list)
        assert first["pageSize"] == second["pageSize"] == GOOGLE_PEOPLE_CONNECTIONS_PAGE_SIZE_MAX
        assert first["sortOrder"] == "LAST_MODIFIED_DESCENDING"
        assert set(first["personFields"].split(",")) == {"names", "emailAddresses", "phoneNumbers"}
        assert "pageToken" not in first and second["pageToken"] == "t1"
        assert {k: v for k, v in second.items() if k != "pageToken"} == first
        assert len(directory.persons) == 3
        assert directory.truncated is False and directory.from_cache is False

    async def test_a_book_longer_than_the_cap_is_cut_and_says_so(self, redis: MemoryRedis) -> None:
        client = _google(uuid4())
        request = AsyncMock(
            return_value={"connections": [_person(i) for i in range(3)], "nextPageToken": "more"}
        )

        with patch.object(client, "_make_request", request):
            directory = await client.list_email_directory(2)

        assert request.await_count == 1
        assert request.call_args.kwargs["params"]["pageSize"] == 2
        assert len(directory.persons) == 2
        assert directory.truncated is True

    async def test_exactly_the_cap_with_nothing_after_is_not_cut(self, redis: MemoryRedis) -> None:
        client = _google(uuid4())
        request = AsyncMock(return_value={"connections": [_person(1), _person(2)]})

        with patch.object(client, "_make_request", request):
            directory = await client.list_email_directory(2)

        assert directory.truncated is False

    async def test_the_second_read_is_served_by_the_cache_until_a_write(
        self, redis: MemoryRedis
    ) -> None:
        user_id = uuid4()
        client = _google(user_id)
        request = AsyncMock(return_value={"connections": [_person(1)]})

        with patch.object(client, "_make_request", request):
            await client.list_email_directory(100)
            cached = await client.list_email_directory(100)
            assert request.await_count == 1
            assert cached.from_cache is True
            assert cached.persons == [compact_person(_person(1))]
            first_version = cached.version

            await invalidate_contacts_cache(user_id)
            reread = await client.list_email_directory(100)

        assert request.await_count == 2
        assert reread.from_cache is False
        # A new copy of the book is a new version: what a reader derived is stale.
        assert first_version and reread.version and reread.version != first_version


class TestMicrosoft:
    async def test_follows_the_next_link_at_a_fixed_page(self, redis: MemoryRedis) -> None:
        client = _microsoft(uuid4())
        first = {
            "value": [{"displayName": "Ana", "emailAddresses": [{"address": "ana@example.org"}]}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/contacts?$skip=1",
        }
        second = {"value": [{"displayName": "Bo", "mobilePhone": "+33 6 12 34 56 78"}]}
        request = AsyncMock(return_value=first)
        follow = AsyncMock(return_value=second)

        with (
            patch.object(client, "_make_request", request),
            patch.object(client, "_make_request_full_url", follow),
        ):
            directory = await client.list_email_directory(5000)

        assert request.call_args.args[2]["$top"] == MICROSOFT_CONTACTS_DIRECTORY_PAGE_SIZE
        follow.assert_awaited_once_with("GET", first["@odata.nextLink"])
        assert [p["names"][0]["displayName"] for p in directory.persons] == ["Ana", "Bo"]
        assert directory.persons[0]["emailAddresses"][0]["value"] == "ana@example.org"
        assert directory.truncated is False

    async def test_a_book_longer_than_the_cap_is_cut_and_says_so(self, redis: MemoryRedis) -> None:
        client = _microsoft(uuid4())
        request = AsyncMock(
            return_value={
                "value": [{"displayName": f"P{i}"} for i in range(3)],
                "@odata.nextLink": "https://graph.microsoft.com/next",
            }
        )
        follow = AsyncMock()

        with (
            patch.object(client, "_make_request", request),
            patch.object(client, "_make_request_full_url", follow),
        ):
            directory = await client.list_email_directory(3)

        follow.assert_not_awaited()
        assert len(directory.persons) == 3
        assert directory.truncated is True

    async def test_a_write_drops_the_cached_directory(self, redis: MemoryRedis) -> None:
        """Parity with Google: a contact created here must be suggested at once."""
        user_id = uuid4()
        client = _microsoft(user_id)
        await cached_directory(
            user_id, ConnectorType.MICROSOFT_CONTACTS.value, 10, AsyncMock(return_value=([], False))
        )
        assert any(key.startswith("contacts_directory:") for key in redis.store)

        with patch.object(client, "_make_request", AsyncMock(return_value={"id": "c1"})):
            await client.create_contact(name="Ana", email="ana@example.org")

        assert not any(key.startswith("contacts_directory:") for key in redis.store)


class TestApple:
    async def test_is_a_compact_cut_of_the_icloud_book_in_the_shared_cache(
        self, redis: MemoryRedis
    ) -> None:
        client = AppleContactsClient.__new__(AppleContactsClient)
        client.user_id = uuid4()
        everything = [_person(i) for i in range(5)]
        with patch.object(
            client,
            "_get_all_contacts_cached",
            AsyncMock(return_value=(everything, True, "2026-10-01T00:00:00Z")),
        ):
            directory = await client._list_email_directory_impl(3)

        assert directory.persons == [compact_person(p) for p in everything[:3]]
        assert directory.truncated is True
        assert directory.version is not None
        assert any("apple_contacts" in key for key in redis.store)

    async def test_a_write_drops_the_shared_directory_too(self, redis: MemoryRedis) -> None:
        user_id = uuid4()
        client = AppleContactsClient.__new__(AppleContactsClient)
        client.user_id = user_id
        await cached_directory(user_id, "apple_contacts", 10, AsyncMock(return_value=([], False)))

        with patch.object(contact_directory, "get_redis_cache", AsyncMock(return_value=redis)):
            await client._invalidate_contacts_cache()

        assert not any(key.startswith("contacts_directory:") for key in redis.store)


class TestCompactAndStamp:
    def test_only_names_addresses_and_numbers_are_kept(self) -> None:
        person = {
            "resourceName": "people/c1",
            "etag": "abc",
            "photos": [{"url": "https://example.org/p.jpg"}],
            "names": [
                {
                    "metadata": {"primary": True},
                    "displayName": "Ana Lima",
                    "givenName": "Ana",
                    "familyName": "Lima",
                    "unstructuredName": "Ana Lima",
                }
            ],
            "emailAddresses": [{"metadata": {}, "value": "ana@example.org", "type": "work"}],
            "phoneNumbers": [{"value": "06 12 34 56 78", "canonicalForm": "+33612345678"}],
        }

        assert compact_person(person) == {
            "names": [{"displayName": "Ana Lima", "givenName": "Ana", "familyName": "Lima"}],
            "emailAddresses": [{"value": "ana@example.org"}],
            "phoneNumbers": [{"value": "06 12 34 56 78"}],
        }

    @pytest.mark.parametrize("junk", [None, "x", {"names": "x", "emailAddresses": [1, {}]}])
    def test_a_malformed_person_compacts_to_nothing_rather_than_raising(self, junk: Any) -> None:
        assert compact_person(junk) in ({}, {"names": [], "emailAddresses": [], "phoneNumbers": []})

    async def test_the_stamp_names_the_version_and_the_cut_of_the_book(
        self, redis: MemoryRedis
    ) -> None:
        user_id = uuid4()
        directory = await cached_directory(
            user_id, "google_contacts", 2, AsyncMock(return_value=([_person(1)], True))
        )

        stamp = await directory_stamp(user_id, "google_contacts", 2)

        assert stamp == DirectoryStamp(version=directory.version or "", truncated=True)
        assert await directory_stamp(user_id, "google_contacts", 3) is None

    async def test_an_invalidation_drops_the_stamp_with_the_book(self, redis: MemoryRedis) -> None:
        user_id = uuid4()
        await cached_directory(user_id, "google_contacts", 2, AsyncMock(return_value=([], False)))

        await invalidate_contacts_cache(user_id)

        assert await directory_stamp(user_id, "google_contacts", 2) is None


async def test_an_unreachable_cache_still_reads_the_provider() -> None:
    read = AsyncMock(return_value=([_person(1)], False))
    with patch.object(
        contact_directory, "get_redis_cache", AsyncMock(side_effect=ConnectionError("down"))
    ):
        directory = await cached_directory(uuid4(), "google_contacts", 10, read)

    read.assert_awaited_once_with(10)
    assert directory.persons == [_person(1)] and directory.from_cache is False


async def test_two_cold_reads_at_once_read_the_provider_once(redis: MemoryRedis) -> None:
    """Two keystrokes on two workers: one provider read, the other waits for it."""
    release = asyncio.Event()
    calls = 0

    async def slow_read(max_contacts: int) -> tuple[list[dict[str, Any]], bool]:
        nonlocal calls
        calls += 1
        await release.wait()
        return [_person(1)], False

    user_id = uuid4()
    first = asyncio.create_task(cached_directory(user_id, "google_contacts", 10, slow_read))
    await asyncio.sleep(0)
    second = asyncio.create_task(cached_directory(user_id, "google_contacts", 10, slow_read))
    await asyncio.sleep(0.05)
    release.set()
    results = await asyncio.gather(first, second)

    assert calls == 1
    compact = [compact_person(_person(1))]
    assert [r.persons for r in results] == [compact, compact]
    assert sorted(r.from_cache for r in results) == [False, True]
