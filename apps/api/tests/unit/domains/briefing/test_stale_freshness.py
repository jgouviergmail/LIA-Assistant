"""D-04 honest freshness — stale-while-error net, from_cache flag, wire compat.

What must hold:
- an OK-with-data fetch remembers its payload under the long-TTL last-good key;
- a later ERROR on the same section serves that payload ALONGSIDE the error
  (status/code/CTA untouched), stamped with the ORIGINAL generation time and
  the failed attempt time;
- without a last-good copy the error stays bare (no invented data);
- a cache hit says so on the wire (from_cache) without persisting the flag;
- payloads cached BEFORE this change still validate (additive defaults);
- the net is disabled entirely by TTL 0.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData
from src.domains.briefing.service import BriefingService


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        full_name="Jean",
        email="jean@example.com",
        language="fr",
        timezone="Europe/Paris",
        health_metrics_agents_enabled=False,
    )


def _make_weather(temp: float = 18.0) -> WeatherData:
    return WeatherData(
        temperature_c=temp,
        condition_code="Clear",
        description="Ensoleillé",
        icon_emoji="☀️",
        location_city="Paris",
        forecast_alert=None,
    )


class _FakeRedis:
    """Minimal async get/set store — enough for the briefing cache contract."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex


def _patch_redis(fake: _FakeRedis):
    return patch(
        "src.domains.briefing.service.get_redis_cache",
        AsyncMock(return_value=fake),
    )


async def _failing_fetcher():
    raise ConnectorAccessError("calendar", "connector_network", "socket timeout")


async def _ok_weather():
    return _make_weather()


@pytest.mark.unit
@pytest.mark.asyncio
class TestStaleWhileError:
    async def test_error_serves_the_last_known_good_payload(self) -> None:
        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        with _patch_redis(fake):
            good = await svc._section("weather", _ok_weather, ttl=3600, force=False)
            # force=True bypasses the fresh main cache and hits the broken fetcher.
            errored = await svc._section("weather", _failing_fetcher, ttl=3600, force=True)

        assert errored.status == CardStatus.ERROR
        assert errored.error_code == "connector_network"
        # The card is NOT a hole: the last good payload rides along…
        assert errored.data is not None
        # …stamped with its ORIGINAL generation time, not the error time.
        assert errored.stale_generated_at == good.generated_at
        assert errored.last_attempt_at is not None
        assert errored.last_attempt_at >= good.generated_at

    async def test_error_without_last_good_stays_bare(self) -> None:
        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        with _patch_redis(fake):
            errored = await svc._section("weather", _failing_fetcher, ttl=3600, force=True)

        assert errored.status == CardStatus.ERROR
        assert errored.data is None
        assert errored.stale_generated_at is None
        assert errored.last_attempt_at is not None

    async def test_last_good_uses_the_configured_ttl(self) -> None:
        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        with _patch_redis(fake):
            await svc._section("weather", _ok_weather, ttl=3600, force=False)

        lastgood_keys = [k for k in fake.store if ":lastgood:" in k]
        assert len(lastgood_keys) == 1
        # Never hardcode a settings-driven threshold (project rule).
        assert fake.ttls[lastgood_keys[0]] == settings.briefing_last_good_ttl_seconds

    async def test_ttl_zero_disables_the_net(self) -> None:
        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        with (
            _patch_redis(fake),
            patch.object(settings, "briefing_last_good_ttl_seconds", 0),
        ):
            await svc._section("weather", _ok_weather, ttl=3600, force=False)
            errored = await svc._section("weather", _failing_fetcher, ttl=3600, force=True)

        assert [k for k in fake.store if ":lastgood:" in k] == []
        assert errored.data is None

    async def test_empty_sections_never_feed_the_net(self) -> None:
        # "Nothing today" is a valid live answer but a useless stale fallback.
        from src.domains.briefing.schemas import AgendaData

        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        async def _empty_agenda():
            return AgendaData(events=[])

        with _patch_redis(fake):
            await svc._section("agenda", _empty_agenda, ttl=600, force=False)

        assert [k for k in fake.store if ":lastgood:" in k] == []


@pytest.mark.unit
@pytest.mark.asyncio
class TestFromCacheFlag:
    async def test_cache_hit_is_labeled_on_the_wire_but_not_persisted(self) -> None:
        svc = BriefingService(user=_make_user())
        fake = _FakeRedis()

        with _patch_redis(fake):
            live = await svc._section("weather", _ok_weather, ttl=3600, force=False)
            hit = await svc._section("weather", _ok_weather, ttl=3600, force=False)

        assert live.from_cache is False
        assert hit.from_cache is True
        # The STORED payload stays from_cache=false — the flag describes the
        # serving path, not the data, so it must be computed per read.
        main_keys = [k for k in fake.store if ":lastgood:" not in k]
        assert len(main_keys) == 1
        assert '"from_cache":false' in fake.store[main_keys[0]].replace(" ", "")


@pytest.mark.unit
class TestWireCompat:
    def test_new_fields_round_trip(self) -> None:
        now = datetime.now(UTC)
        section = CardSection(
            status=CardStatus.ERROR,
            data=_make_weather(),
            generated_at=now,
            error_code="connector_network",
            from_cache=True,
            stale_generated_at=now,
            last_attempt_at=now,
        )
        rebuilt = CardSection.model_validate_json(section.model_dump_json())
        assert rebuilt == section

    def test_pre_d04_cached_payload_still_validates(self) -> None:
        # Exactly what sits in Redis from before this change: no new fields.
        legacy = (
            '{"status": "ok", "data": null, '
            '"generated_at": "2026-07-29T06:00:00Z", '
            '"error_code": null, "error_message": null}'
        )
        section = CardSection.model_validate_json(legacy)
        assert section.from_cache is False
        assert section.stale_generated_at is None
        assert section.last_attempt_at is None
