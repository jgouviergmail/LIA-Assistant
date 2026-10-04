"""Provider caches and card metadata follow the authenticated OAuth account."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.tools.email_card_binding import bind_email_card_accounts
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_same_user_and_message_id_cannot_reuse_another_oauth_accounts_cache(monkeypatch):
    user = UUID(int=1)
    cache = {}
    redis = AsyncMock()

    async def get(key):
        return cache.get(key)

    async def put(key, value, **kwargs):
        cache[key] = value

    redis.get.side_effect = get
    redis.set.side_effect = put
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
        AsyncMock(return_value=redis),
    )
    first = GoogleGmailClient(
        user, ConnectorCredentials(access_token="first", account_binding=str(UUID(int=4))), Mock()
    )
    second = GoogleGmailClient(
        user, ConnectorCredentials(access_token="second", account_binding=str(UUID(int=5))), Mock()
    )
    first._make_request = AsyncMock(return_value={"id": "same", "subject": "First account"})
    second._make_request = AsyncMock(return_value={"id": "same", "subject": "Second account"})
    assert (await first.get_message("same"))["subject"] == "First account"
    assert (await first.get_message("same"))["from_cache"] is True
    assert (await second.get_message("same"))["subject"] == "Second account"
    second._make_request.assert_awaited_once()
    assert len(cache) == 2
    assert all("access_token" not in json.dumps(value) for value in cache.values())


def test_native_binding_is_display_only_and_cannot_come_from_payload():
    credentials = ConnectorCredentials(access_token="secret", account_binding=str(UUID(int=4)))
    client = GoogleGmailClient(UUID(int=1), credentials, Mock())
    emails = [
        {
            "id": "a",
            "subject": "Subject",
            "from_cache": False,
            FIELD_DISPLAY_ONLY: {"body": "Received body", "_lia_email_account": "forged"},
        }
    ]
    before = deepcopy(emails)
    bound = bind_email_card_accounts(client, emails)
    assert bound[0][FIELD_DISPLAY_ONLY]["_lia_email_account"] == str(UUID(int=4))
    assert bound[0][FIELD_DISPLAY_ONLY]["body"] == "Received body"
    assert emails == before
    assert "account_binding" not in credentials.model_dump()
    assert "account_binding" not in credentials.model_dump_json()
    assert (
        "_lia_email_account"
        not in bind_email_card_accounts(object(), emails)[0][FIELD_DISPLAY_ONLY]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["search_emails", "list_labels", "list_labels_full"])
async def test_search_and_labels_caches_are_isolated_and_invalidated_per_account(
    monkeypatch, operation
):
    cache = {}
    redis = AsyncMock()

    async def get(key):
        return cache.get(key)

    async def put(key, value, **kwargs):
        cache[key] = value

    async def delete(key):
        cache.pop(key, None)

    redis.get.side_effect, redis.set.side_effect, redis.delete.side_effect = get, put, delete
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
        AsyncMock(return_value=redis),
    )
    clients = [
        GoogleGmailClient(
            UUID(int=1),
            ConnectorCredentials(access_token="token", account_binding=str(UUID(int=grant))),
            Mock(),
        )
        for grant in (4, 5)
    ]
    for client in clients:
        client._make_request = AsyncMock(
            return_value={
                "messages": [],
                "labels": [{"id": "same", "name": client.credentials.account_binding}],
            }
        )
        args = ("same query",) if operation == "search_emails" else ()
        await getattr(client, operation)(*args)
        await getattr(client, operation)(*args)
        client._make_request.assert_awaited_once()
    assert len(cache) == 2
    first_key, second_key = list(cache)
    assert str(UUID(int=4)) in first_key and str(UUID(int=5)) in second_key
    if operation != "search_emails":
        await clients[0]._invalidate_labels_cache()
        assert first_key not in cache and second_key in cache


def test_legacy_cache_keys_and_token_rotation_preserve_compatibility():
    client = GoogleGmailClient(UUID(int=1), ConnectorCredentials(access_token="token"), Mock())
    assert client._cache_account == str(UUID(int=1))
    client.credentials = ConnectorCredentials(access_token="new", account_binding=str(UUID(int=4)))
    namespace = client._cache_account
    client.credentials = client.credentials.model_copy(update={"access_token": "rotated"})
    assert client._cache_account == namespace
