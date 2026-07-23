"""Hidden briefing sections (UXR Lot 5, B4) — a user-hidden card is a pure
placeholder: its fetcher is NEVER awaited and no cache IO happens (the
economy is the point, not just the display). The synthesis cache path honors
the same preference.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.constants import SECTION_REMINDERS, SECTION_WEATHER
from src.domains.briefing.schemas import CardStatus
from src.domains.briefing.service import BriefingService


def _make_user(briefing_preferences: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        full_name="Jean",
        email="jean@example.com",
        language="fr",
        timezone="Europe/Paris",
        health_metrics_agents_enabled=False,
        briefing_preferences=briefing_preferences,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestHiddenSectionShortCircuit:
    async def test_hidden_section_never_fetches_nor_touches_cache(self) -> None:
        svc = BriefingService(user=_make_user({"hidden": [SECTION_WEATHER], "order": []}))
        fetcher = AsyncMock()
        with patch.object(svc, "_read_cache", new=AsyncMock()) as read_cache:
            section = await svc._section(SECTION_WEATHER, fetcher, ttl=3600, force=False)

        assert section.status == CardStatus.HIDDEN
        assert section.data is None
        fetcher.assert_not_awaited()
        read_cache.assert_not_awaited()

    async def test_visible_section_still_fetches(self) -> None:
        svc = BriefingService(user=_make_user({"hidden": [SECTION_WEATHER], "order": []}))
        fetcher = AsyncMock(return_value=None)
        with patch.object(svc, "_read_cache", new=AsyncMock(return_value=None)):
            section = await svc._section(SECTION_REMINDERS, fetcher, ttl=0, force=True)

        fetcher.assert_awaited_once()
        assert section.status in (CardStatus.OK, CardStatus.EMPTY)

    async def test_null_preferences_hide_nothing(self) -> None:
        svc = BriefingService(user=_make_user(None))
        assert svc._hidden_sections == frozenset()

    async def test_malformed_preferences_hide_nothing(self) -> None:
        svc = BriefingService(user=_make_user({"hidden": "oops"}))  # type: ignore[arg-type]
        assert svc._hidden_sections == frozenset()


@pytest.mark.unit
@pytest.mark.asyncio
class TestHiddenSectionCachePath:
    async def test_synthesis_cache_read_returns_hidden_placeholder(self) -> None:
        svc = BriefingService(user=_make_user({"hidden": [SECTION_WEATHER], "order": []}))
        with patch.object(svc, "_read_cache", new=AsyncMock()) as read_cache:
            section = await svc._read_section_cache(SECTION_WEATHER)

        assert section is not None and section.status == CardStatus.HIDDEN
        read_cache.assert_not_awaited()

    async def test_live_section_skips_cache_without_placeholder(self) -> None:
        svc = BriefingService(user=_make_user(None))
        with patch.object(svc, "_read_cache", new=AsyncMock()) as read_cache:
            section = await svc._read_section_cache(SECTION_REMINDERS, live=True)

        assert section is None
        read_cache.assert_not_awaited()
