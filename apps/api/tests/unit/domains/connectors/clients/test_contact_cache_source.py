"""A cached contact is never re-attributed to a newly connected account."""

import fnmatch
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from src.core.content_source import content_source_binding
from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.infrastructure.cache.contacts_cache import ContactsCache

pytestmark = pytest.mark.unit


def _redis() -> MagicMock:
    """Replace Redis transport, keeping the real cache's key and envelope logic."""
    entries: dict[str, str] = {}

    async def get(key: str) -> str | None:
        return entries.get(key)

    async def put(key: str, value: str, *, ex: int) -> None:
        assert ex > 0
        entries[key] = value

    async def delete(*keys: str) -> int:
        removed = sum(key in entries for key in keys)
        for key in keys:
            entries.pop(key, None)
        return removed

    async def scan(cursor: int, *, match: str, count: int) -> tuple[int, list[str]]:
        return 0, [key for key in entries if fnmatch.fnmatchcase(key, match)]

    return MagicMock(
        get=AsyncMock(side_effect=get),
        set=AsyncMock(side_effect=put),
        delete=AsyncMock(side_effect=delete),
        scan=AsyncMock(side_effect=scan),
    )


async def test_google_client_reuses_own_cache_and_reads_again_after_source_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _redis()
    monkeypatch.setattr(
        "src.domains.connectors.clients.cache_mixin.get_redis_cache", AsyncMock(return_value=redis)
    )
    user = uuid4()
    first = GooglePeopleClient(
        user, ConnectorCredentials(access_token="unused", account_binding="grant-a"), MagicMock()
    )
    second = GooglePeopleClient(
        user, ConnectorCredentials(access_token="unused", account_binding="grant-b"), MagicMock()
    )
    a = AsyncMock(
        return_value={
            "results": [
                {
                    "person": {
                        "resourceName": "people/same-id",
                        "names": [{"displayName": "First account"}],
                    }
                }
            ]
        }
    )
    b = AsyncMock(
        return_value={
            "results": [
                {
                    "person": {
                        "resourceName": "people/same-id",
                        "names": [{"displayName": "Second account"}],
                    }
                }
            ]
        }
    )
    monkeypatch.setattr(first, "_make_request", a)
    monkeypatch.setattr(second, "_make_request", b)
    try:
        assert not (await first.search_contacts("same-query"))["from_cache"]
        assert (await first.search_contacts("same-query"))["from_cache"]
        second_result = await second.search_contacts("same-query")
        assert not second_result["from_cache"]
        assert second_result["results"][0]["person"]["names"][0]["displayName"] == "Second account"
        assert (await second.search_contacts("same-query"))["from_cache"]
        assert a.await_count == b.await_count == 1
    finally:
        await first.close()
        await second.close()


async def test_every_google_record_cache_is_scoped_and_invalidation_reaches_all_sources() -> None:
    redis = _redis()
    old = ContactsCache(redis)
    first, second, missing = old.for_source("a" * 64), old.for_source("b" * 64), old.for_source("")
    user = uuid4()
    for cache in (old, first):
        await cache.set_list(user, {"owner": "first"})
        await cache.set_search(user, "same-query", {"owner": "first"})
        await cache.set_details(user, "people/same-id", {"owner": "first"})
    assert (await first.get_list(user))[0] == {"owner": "first"}
    for cache in (second, missing):
        assert (await cache.get_list(user))[0] is None
        assert (await cache.get_search(user, "same-query"))[0] is None
        assert (await cache.get_details(user, "people/same-id"))[0] is None
    writes = redis.set.await_count
    await missing.set_list(user, {"unproven": True})
    await missing.set_search(user, "q", {"unproven": True})
    await missing.set_details(user, "id", {"unproven": True})
    assert redis.set.await_count == writes
    await second.set_list(user, {"owner": "second"})
    await old.invalidate_user(user)
    assert (await first.get_list(user))[0] is None
    assert (await second.get_list(user))[0] is None
    assert (await old.get_list(user))[0] is None


async def test_apple_principal_change_cannot_adopt_a_cached_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _redis()
    monkeypatch.setattr(
        "src.domains.connectors.clients.apple_contacts_client.get_redis_session",
        AsyncMock(return_value=redis),
    )
    user = uuid4()
    first = AppleContactsClient(
        user, AppleCredentials(apple_id="a@example.test", app_password="unused"), MagicMock()
    )
    second = AppleContactsClient(
        user, AppleCredentials(apple_id="b@example.test", app_password="unused"), MagicMock()
    )
    first_key = f"apple_contacts:{user}:all:{content_source_binding(first)}"
    await redis.set(
        first_key,
        json.dumps(
            {
                "contacts": [{"resourceName": "same-id", "name": "First account"}],
                "cached_at": "2026-11-08T00:00:00Z",
            }
        ),
        ex=60,
    )
    await redis.set(f"apple_contacts:{user}:all", json.dumps([{"name": "Legacy"}]), ex=60)
    second._addressbook_url = "https://contacts.example.test/book/"
    transport = MagicMock(
        request=AsyncMock(return_value=httpx.Response(207, text='<d:multistatus xmlns:d="DAV:"/>'))
    )
    monkeypatch.setattr(second, "_get_http_client", AsyncMock(return_value=transport))
    try:
        own, cached, _ = await first._get_all_contacts_cached(True)
        assert cached and own[0]["name"] == "First account"
        current, cached, _ = await second._get_all_contacts_cached(True)
        assert not cached and current == []
        transport.request.assert_awaited_once()
    finally:
        await first.close()
        await second.close()
