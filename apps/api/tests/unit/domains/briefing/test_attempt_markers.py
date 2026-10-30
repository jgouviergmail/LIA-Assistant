"""Attempt markers and the generation fence of the dashboard's section cache (D1).

Measured (spec 2026-10-21 §0ter): a failed source was never cached, so every
completeness reader — ``/synthesis``, a worker waiting for the shared build —
saw the bundle as incomplete and rebuilt it, opening the failing source again;
and a push invalidation landing during a read let the read write its older
payload right after the delete, a stale card for a whole TTL (E5). The marker
settles a failure for the completeness readers only; the fence refuses a write
whose generation a push bumped meanwhile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.domains.briefing.cache_keys import attempt_marker_key, section_cache_key
from src.domains.briefing.cache_state import classify_cache_state
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.briefing.schemas import CardSection, CardStatus
from src.domains.briefing.section_outcomes import bump_section_generation
from src.domains.briefing.service import BriefingService
from src.domains.push_channels.cache_invalidation import invalidate_for_provider
from src.domains.push_channels.models import PushChannelProvider
from tests.unit.domains.briefing.page_load_harness import Rig, make_user

pytestmark = pytest.mark.unit


def _down(source: str = "google") -> ConnectorAccessError:
    return ConnectorAccessError(source, "connector_network", "socket timeout")


def _marker(rig: Rig, user: Any, section: str) -> str:
    return attempt_marker_key(user_id=user.id, language=user.language, section=section)


def _cached(rig: Rig, user: Any, section: str) -> str:
    return section_cache_key(user_id=user.id, language=user.language, section=section)


class TestAttemptMarkers:
    async def test_failed_live_read_writes_attempt_marker(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()

        key = _marker(rig, user, "agenda")
        assert key in rig.redis.keys()
        raw, expires_at = rig.redis._store[key]
        marker = CardSection.model_validate_json(raw)
        assert marker.status is CardStatus.ERROR
        assert expires_at - rig.clock.now == settings.briefing_section_attempt_marker_seconds
        assert _cached(rig, user, "agenda") not in rig.redis.keys()

    async def test_marker_carries_the_stale_copy(self) -> None:
        rig = Rig()
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            rig.clock.advance(24 * 3600)  # every section cache expired, last-good kept
            rig.failures["agenda"] = _down()
            await BriefingService(user).build_cards()

        marker = CardSection.model_validate_json(rig.redis._store[_marker(rig, user, "agenda")][0])
        assert marker.status is CardStatus.ERROR
        assert marker.data is not None and marker.stale_generated_at is not None

    async def test_completeness_reader_treats_marker_as_settled(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            service = BriefingService(user)
            await service.build_cards()
            bundle, missing = await service._read_cached_bundle()

        assert missing == frozenset()
        assert bundle.agenda.status is CardStatus.ERROR

    async def test_synthesis_does_not_rebuild_after_attempted_failure(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            rig.reset_calls()
            await BriefingService(user).build_text()

        assert rig.builds == 0
        assert rig.calls["agenda"] == 0

    async def test_cards_route_ignores_marker(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            rig.reset_calls()
            cards = await BriefingService(user).build_cards()

        assert rig.calls["agenda"] == 1  # the source is retried live
        assert cards.agenda.status is CardStatus.ERROR

    async def test_success_deletes_marker(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            del rig.failures["agenda"]
            cards = await BriefingService(user).build_cards()

        assert cards.agenda.status is CardStatus.OK
        assert _marker(rig, user, "agenda") not in rig.redis.keys()
        assert _cached(rig, user, "agenda") in rig.redis.keys()

    async def test_marker_disabled_keeps_the_old_behaviour(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with (
            patch.object(settings, "briefing_section_attempt_marker_seconds", 0),
            rig.installed(),
        ):
            service = BriefingService(user)
            await service.build_cards()
            _bundle, missing = await service._read_cached_bundle()

        assert missing == frozenset({"agenda"})


class TestCacheStateByProvenance:
    def test_live_build_slower_than_old_threshold_is_cold(self) -> None:
        old = datetime.now(UTC) - timedelta(seconds=2)
        live = [(CardSection(status=CardStatus.OK, generated_at=old), True) for _ in range(3)]
        assert classify_cache_state(live) == "cold"

    def test_cached_sections_are_warm_and_a_mix_is_partial(self) -> None:
        now = datetime.now(UTC)
        hit = CardSection(status=CardStatus.OK, generated_at=now, from_cache=True)
        live = CardSection(status=CardStatus.OK, generated_at=now)
        assert classify_cache_state([(hit, True), (hit, True)]) == "warm"
        assert classify_cache_state([(hit, True), (live, True)]) == "partial"

    def test_hidden_and_always_live_sections_do_not_count(self) -> None:
        now = datetime.now(UTC)
        hidden = CardSection(status=CardStatus.HIDDEN, generated_at=now)
        hit = CardSection(status=CardStatus.OK, generated_at=now, from_cache=True)
        live = CardSection(status=CardStatus.OK, generated_at=now)
        assert classify_cache_state([(hidden, True), (hit, True), (live, False)]) == "warm"


class TestGenerationFence:
    async def test_push_during_read_drops_the_write(self) -> None:
        """A Gmail push lands while the mails are being read: no stale card, next read live."""
        rig = Rig()
        user = make_user()
        real_fetch = rig._fetcher("mails")
        pushes: list[int] = []

        async def push_mid_read(*args: object, **kwargs: object) -> Any:
            if not pushes:  # one push, during the first read only
                pushes.append(1)
                await invalidate_for_provider(PushChannelProvider.GOOGLE_GMAIL.value, user.id)
            return await real_fetch(*args, **kwargs)

        with (
            rig.installed(),
            patch(
                "src.domains.push_channels.cache_invalidation.get_redis_cache",
                return_value=rig.redis,
                new_callable=_async_returning,
            ),
            patch("src.domains.briefing.service.fetch_mails", side_effect=push_mid_read),
        ):
            await BriefingService(user).build_cards()
            assert _cached(rig, user, "mails") not in rig.redis.keys()
            rig.reset_calls()
            await BriefingService(user).build_cards()

        assert rig.calls["mails"] == 1  # the next read is live
        assert _cached(rig, user, "mails") in rig.redis.keys()

    async def test_write_without_push_commits(self) -> None:
        rig = Rig()
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            rig.reset_calls()
            await BriefingService(user).build_cards()

        assert rig.calls["mails"] == 0  # served from the committed cache

    async def test_push_before_read_does_not_fence_it(self) -> None:
        """A generation bumped BEFORE the read began is the read's own: it commits."""
        rig = Rig()
        user = make_user()
        with rig.installed():
            await bump_section_generation(user_id=user.id, section="mails")
            await BriefingService(user).build_cards()

        assert _cached(rig, user, "mails") in rig.redis.keys()

    async def test_redis_down_writes_as_today(self) -> None:
        """An unreadable generation falls back to the unfenced write (the floor)."""
        rig = Rig()
        user = make_user()

        async def no_generation(_key: str) -> None:
            return None

        with (
            rig.installed(),
            patch("src.domains.briefing.service.read_generation", no_generation),
        ):
            await BriefingService(user).build_cards()

        assert _cached(rig, user, "mails") in rig.redis.keys()
        assert not any(":gen:" in key for key in rig.redis.keys())


def _async_returning(*, return_value: Any) -> Any:
    async def _get() -> Any:
        return return_value

    return _get


async def _no_generation(_key: str) -> None:
    return None


class TestBestEffortWrites:
    """The cache serves a section; it never decides whether the page renders."""

    async def test_an_unfenced_success_clears_the_failed_attempts_marker(self) -> None:
        rig = Rig(failures={"agenda": _down()})
        user = make_user()
        with rig.installed():
            await BriefingService(user).build_cards()
            assert _marker(rig, user, "agenda") in rig.redis.keys()
            rig.failures.clear()
            with patch("src.domains.briefing.service.read_generation", _no_generation):
                await BriefingService(user).build_cards()

        assert _marker(rig, user, "agenda") not in rig.redis.keys()
        assert _cached(rig, user, "agenda") in rig.redis.keys()

    async def test_a_fenced_write_the_cache_refuses_leaves_the_cards_whole(self) -> None:
        rig = Rig()
        user = make_user()

        async def refused(*_args: object, **_kwargs: object) -> Any:
            raise ConnectionError("cache down")

        with rig.installed(), patch.object(rig.redis, "eval", refused):
            bundle = await BriefingService(user).build_cards()

        assert bundle.agenda is not None
        assert _cached(rig, user, "agenda") not in rig.redis.keys()
