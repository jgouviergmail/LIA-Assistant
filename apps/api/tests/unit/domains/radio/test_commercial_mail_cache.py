"""Real Radio-to-Briefing source path: policy-specific cache and push invalidation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.briefing import fetchers, service
from src.domains.briefing.cache_keys import section_keys_every_language
from src.domains.briefing.schemas import CardSection, CardStatus, MailItem, MailsData
from src.domains.connectors import active_client
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.push_channels.cache_invalidation import invalidate_for_provider
from src.domains.radio import adapters
from src.domains.radio.personal import PersonalSource, briefing_drafts, personal_facts
from src.domains.users.models import User

pytestmark = pytest.mark.unit


class Cache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, *, ex):
        self.data[key] = value

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    async def scan_iter(self, *, match):
        return
        yield


async def test_same_owner_concurrent_radio_and_dashboard_do_not_share_promotional_cache(
    monkeypatch,
) -> None:
    cache = Cache()
    user = User(id=uuid4(), language="en", timezone="UTC", briefing_preferences={})
    count = 0
    scans = []
    messages = [
        {"id": str(i), "subject": "Something for you", "labelIds": ["CATEGORY_PROMOTIONS"]}
        for i in range(12)
    ]
    messages.append(
        {"id": "real", "subject": "A family dinner", "from": "Family <family@example.test>"}
    )

    class Client:
        async def search_emails(self, **kwargs):
            nonlocal count
            count += 1
            scans.append(kwargs["max_results"])
            await asyncio.sleep(0)
            return {"messages": messages[: kwargs["max_results"]]}

    @asynccontextmanager
    async def opened(*args):
        yield ActiveClient(Client(), ConnectorType.GOOGLE_GMAIL, None)

    async def redis():
        return cache

    class Database:
        async def get(self, model, owner):
            assert model is User and owner == user.id
            return user

    @asynccontextmanager
    async def database():
        yield Database()

    monkeypatch.setattr(active_client, "open_active_client", opened)
    monkeypatch.setattr(service, "get_redis_cache", redis)
    monkeypatch.setattr(service, "fetch_mails", fetchers.fetch_mails)
    monkeypatch.setattr(fetchers.settings, "briefing_max_mails_items", 1)
    monkeypatch.setattr(adapters, "get_db_context", database)
    ordinary = service.BriefingService(user)
    radio_read = await adapters._cards_of(user.id)
    consultations = []
    normal, radio = await asyncio.gather(
        ordinary.read_selected_cards(frozenset({"mails"})),
        radio_read(
            frozenset({"mails"}), on_read=lambda name, status: consultations.append((name, status))
        ),
    )
    assert normal.mails.data.items[0].subject == "Something for you"
    assert radio.mails.data.items[0].subject == "A family dinner"
    assert normal.mails.data.total_unread_today == 1
    assert radio.mails.data.total_unread_today == len(messages)
    assert count == 2 and sorted(scans)[0] == 1
    assert consultations == [("mails", CardStatus.OK)]
    drafts = briefing_drafts(radio)
    facts = personal_facts(drafts)
    assert any("A family dinner" in fact.text for fact in facts.day)
    assert "Something for you" not in str(drafts[PersonalSource.MAILS])

    cached = await radio_read(
        frozenset({"mails"}), on_read=lambda *args: consultations.append(args)
    )
    assert cached.mails.from_cache and count == 2 and len(consultations) == 1
    editorial = service.BriefingService(user, exclude_commercial_mails=True)
    assert editorial._cache_key("mails") != ordinary._cache_key("mails")
    assert editorial._flight_key(frozenset()) != ordinary._flight_key(frozenset())
    assert editorial._claim_key() != ordinary._claim_key()
    assert editorial._last_good_key("mails") != ordinary._last_good_key("mails")
    assert editorial._cache_key("mails") in cache.data
    assert editorial._last_good_key("mails") in cache.data
    assert editorial._last_good_key("mails") in section_keys_every_language(
        user_id=user.id, section="mails"
    )
    monkeypatch.setattr("src.domains.push_channels.cache_invalidation.get_redis_cache", redis)
    await invalidate_for_provider("google_gmail", user.id)
    assert editorial._cache_key("mails") not in cache.data
    assert editorial._last_good_key("mails") not in cache.data


async def test_old_unfiltered_payload_and_lastgood_cannot_satisfy_editorial_read(
    monkeypatch,
) -> None:
    cache = Cache()
    user = User(id=uuid4(), language="en", timezone="UTC", briefing_preferences={})
    normal = service.BriefingService(user)
    editorial = service.BriefingService(user, exclude_commercial_mails=True)
    old = CardSection(
        status=CardStatus.OK,
        generated_at=datetime.now(UTC),
        data=MailsData(
            items=[MailItem(subject="Something for you", received_local="now")],
            total_unread_today=1,
        ),
    )
    cache.data[normal._cache_key("mails")] = old.model_dump_json()
    cache.data[normal._last_good_key("mails")] = old.model_dump_json()

    async def redis():
        return cache

    async def failed(**kwargs):
        assert kwargs["exclude_commercial_mails"] is True
        raise TimeoutError

    monkeypatch.setattr(service, "get_redis_cache", redis)
    monkeypatch.setattr(service, "fetch_mails", failed)
    cards = await editorial.read_selected_cards(frozenset({"mails"}))
    assert cards.mails.status is CardStatus.ERROR and cards.mails.data is None
    assert not cards.mails.from_cache
