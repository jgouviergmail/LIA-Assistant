"""The act keeps what its first response showed — best-effort, never an invented section."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.briefing.act_snapshot import keep_served, served_sections
from src.domains.briefing.cache_keys import act_snapshot_key
from src.domains.briefing.constants import SECTION_SMS
from src.domains.briefing.schemas import CardSection, CardStatus

pytestmark = pytest.mark.unit

AT = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
CACHE = "src.domains.briefing.act_snapshot.get_redis_cache"


class _Redis:
    """The two commands the copy uses, with the expiry each write asked for."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiries: dict[str, int] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key], self.expiries[key] = value, ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


def _section(status: CardStatus) -> CardSection:
    return CardSection(status=status, generated_at=AT, data=None)


async def test_what_was_shown_comes_back_whole_for_the_acts_lifetime() -> None:
    redis, owner, act = _Redis(), uuid4(), "act-1"
    shown = {
        "mails": _section(CardStatus.OK),
        "agenda": _section(CardStatus.ERROR),
        "weather": _section(CardStatus.PENDING),  # not read yet: nothing to keep
        "health": _section(CardStatus.HIDDEN),
        SECTION_SMS: _section(CardStatus.OK),  # read live on its own terms
    }
    with patch(CACHE, AsyncMock(return_value=redis)):
        await keep_served(user_id=owner, act_id=act, sections=shown)
        kept = await served_sections(user_id=owner, act_id=act)

    assert kept == {"mails": shown["mails"], "agenda": shown["agenda"]}
    key = act_snapshot_key(user_id=owner, act_id=act)
    assert redis.expiries[key] == settings.briefing_act_token_ttl_seconds


async def test_a_response_that_showed_nothing_writes_nothing() -> None:
    cache = AsyncMock()
    with patch(CACHE, cache):
        await keep_served(
            user_id=uuid4(), act_id="act-1", sections={"mails": _section(CardStatus.PENDING)}
        )

    cache.assert_not_awaited()


@pytest.mark.parametrize(
    "stored",
    [None, "not json", '{"mails": "{\\"status\\": \\"nonsense\\"}"}'],
    ids=["never-kept", "unreadable", "invalid-section"],
)
async def test_a_missing_or_unreadable_copy_is_no_copy(stored: str | None) -> None:
    redis, owner = _Redis(), uuid4()
    if stored is not None:
        redis.values[act_snapshot_key(user_id=owner, act_id="act-1")] = stored
    with patch(CACHE, AsyncMock(return_value=redis)):
        assert await served_sections(user_id=owner, act_id="act-1") == {}


async def test_a_cache_down_loses_the_copy_and_nothing_else() -> None:
    down: Any = AsyncMock(side_effect=ConnectionError("cache down"))
    with patch(CACHE, down):
        await keep_served(
            user_id=uuid4(), act_id="act-1", sections={"mails": _section(CardStatus.OK)}
        )
        assert await served_sections(user_id=uuid4(), act_id="act-1") == {}

    assert down.await_count == 2
