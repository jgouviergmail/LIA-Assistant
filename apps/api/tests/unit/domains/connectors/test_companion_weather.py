"""The companion's weather: present conditions at the person's place, from any read.

ADR-294 (follow-up of 2026-11-13): the face used to borrow ONE reader's cache, the
dashboard card's, and lost its weather an hour after the last dashboard visit while
the heartbeat, the discussions, the routines and the chat read the same place many
times a day. Every read of the present conditions now leaves an observation through
one door, never older than the one it replaces, and says so to the person's tabs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import COMPANION_WEATHER_CACHE_PREFIX, PRESENT_WEATHER_FRESH_SECONDS
from src.domains.connectors import companion_weather
from src.domains.connectors.companion_weather import (
    COMPANION_WEATHER_SIGNAL,
    companion_weather_key,
    is_present,
    observe_current,
    publish_companion_weather,
    read_companion_observation,
)
from src.infrastructure.cache.key_families import KeyScope, scope_of

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)
MODULE = "src.domains.connectors.companion_weather"


def reading(**overrides: Any) -> dict[str, Any]:
    """An OWM-shaped answer of ``get_current_weather`` (both providers answer this shape)."""
    payload: dict[str, Any] = {
        "dt": int((NOW - timedelta(minutes=5)).timestamp()),
        "main": {"temp": 3.4, "humidity": 80},
        "weather": [{"main": "Rain", "description": "pluie fine"}],
        "wind": {"speed": 5.0, "deg": 270},
        "name": "Paris",
        "coord": {"lat": 48.8566, "lon": 2.3522},
    }
    payload.update(overrides)
    return payload


def test_observes_the_present_conditions_and_nothing_of_the_place() -> None:
    observed = observe_current(reading(), now=NOW)

    assert observed is not None
    assert observed.temperature_c == 3.4
    assert observed.condition_code == "Rain"
    # The card's own conversion: metres per second to kilometres per hour.
    assert observed.wind_speed_kmh == 18.0
    assert observed.observed_at == NOW - timedelta(minutes=5)
    dumped = observed.model_dump_json()
    for private in ("Paris", "48.85", "2.35", "pluie"):
        assert private not in dumped


def test_a_provider_condition_is_read_in_the_one_vocabulary() -> None:
    observed = observe_current(reading(weather=[{"main": "RAIN"}]), now=NOW)

    assert observed is not None
    assert observed.condition_code == "Rain"


@pytest.mark.parametrize(
    "broken",
    [
        {"main": {}},
        {"main": {"temp": None}},
        {"main": {"temp": "warm"}},
        {"main": {"temp": float("nan")}},
        # JSON ``true`` is no temperature, even though Python counts it as 1.
        {"main": {"temp": True}},
        {"main": {"temp": 120}},
        {"main": "not a block"},
        {"wind": {"speed": -3}},
    ],
)
def test_an_unreadable_reading_is_no_observation(broken: dict[str, Any]) -> None:
    assert observe_current(reading(**broken), now=NOW) is None


@pytest.mark.parametrize("speed", [float("nan"), float("inf"), "strong", None])
def test_an_unreadable_wind_leaves_the_observation_without_wind(speed: object) -> None:
    # Unreadable is absent, as for the date: the temperature still dresses the face.
    observed = observe_current(reading(wind={"speed": speed}), now=NOW)

    assert observed is not None
    assert observed.wind_speed_kmh is None
    assert observed.temperature_c == 3.4


def test_a_reading_older_than_the_present_is_not_the_present() -> None:
    stale = int((NOW - timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS + 1)).timestamp())

    assert observe_current(reading(dt=stale), now=NOW) is None


def test_the_present_ends_exactly_when_it_ages_out_on_both_sides() -> None:
    # One rule for the door that keeps an observation and the endpoint that shows it.
    edge = NOW - timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS)
    just_inside = edge + timedelta(seconds=1)

    assert observe_current(reading(dt=int(edge.timestamp())), now=NOW) is None
    assert observe_current(reading(dt=int(just_inside.timestamp())), now=NOW) is not None
    assert is_present(edge, NOW) is False
    assert is_present(just_inside, NOW) is True
    assert is_present(NOW + timedelta(seconds=1), NOW) is False


@pytest.mark.parametrize(
    "dt",
    [
        None,
        "soon",
        int((NOW + timedelta(minutes=3)).timestamp()),
        # Instants no datetime can hold: unreadable, like an absent one.
        10**20,
        -(10**20),
    ],
)
def test_an_undated_future_or_impossible_reading_is_observed_now(dt: object) -> None:
    observed = observe_current(reading(dt=dt), now=NOW)

    assert observed is not None
    assert observed.observed_at == NOW


def test_the_key_is_the_accounts_own_and_a_declared_cache() -> None:
    user = uuid4()

    key = companion_weather_key(user)

    assert key == f"{COMPANION_WEATHER_CACHE_PREFIX}:{user}"
    assert scope_of(key) == KeyScope.USER_CACHE


def _redis(eval_answer: int) -> MagicMock:
    redis = MagicMock()
    redis.eval = AsyncMock(return_value=eval_answer)
    return redis


async def test_a_new_observation_is_kept_until_it_ages_out_and_said_to_the_tabs() -> None:
    user = uuid4()
    redis = _redis(1)
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)) as publish,
    ):
        assert await publish_companion_weather(user, reading(), now=NOW) is True

    script, keys, key, payload, observed_ms, ttl_ms = redis.eval.await_args.args
    assert script == companion_weather.KEEP_NEWER_SCRIPT
    assert (keys, key) == (1, companion_weather_key(user))
    stored = json.loads(payload)
    assert stored["observed_ms"] == int(observed_ms)
    assert stored["observation"]["temperature_c"] == 3.4
    # Kept exactly as long as it stays the present: one hour from its observation.
    assert int(ttl_ms) == (PRESENT_WEATHER_FRESH_SECONDS - 5 * 60) * 1000
    publish.assert_awaited_once_with(user, {"type": COMPANION_WEATHER_SIGNAL})


async def test_an_older_observation_neither_replaces_the_newer_nor_says_anything() -> None:
    redis = _redis(0)
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)) as publish,
    ):
        assert await publish_companion_weather(uuid4(), reading(), now=NOW) is False

    publish.assert_not_awaited()


@pytest.mark.parametrize("answer", [{"main": {}}, None, ["not", "a", "mapping"], "text"])
async def test_an_unreadable_reading_touches_nothing(answer: object) -> None:
    # The clients' read contract types the answer ``object``: anything but a
    # mapping is refused by the door, never by the reader's own failure.
    redis = _redis(1)
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", AsyncMock()) as publish,
    ):
        assert await publish_companion_weather(uuid4(), answer, now=NOW) is False

    redis.eval.assert_not_awaited()
    publish.assert_not_awaited()


async def test_an_observation_about_to_age_out_is_kept_for_its_last_millisecond() -> None:
    # 0.4 ms of present left: a zero expiry would be refused by Redis.
    redis = _redis(1)
    dt = NOW.timestamp() - PRESENT_WEATHER_FRESH_SECONDS + 0.0004
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)),
    ):
        assert await publish_companion_weather(uuid4(), reading(dt=dt), now=NOW) is True

    assert int(redis.eval.await_args.args[-1]) == 1


@pytest.mark.parametrize("where", ["cache", "channel"])
async def test_a_failure_never_fails_the_read_that_offered_it(where: str) -> None:
    redis = _redis(1)
    if where == "cache":
        redis.eval = AsyncMock(side_effect=ConnectionError("down"))
    publish = AsyncMock(side_effect=ConnectionError("down") if where == "channel" else None)
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", publish),
    ):
        kept = await publish_companion_weather(uuid4(), reading(), now=NOW)

    # Kept or not, the reader goes on: the observation is a by-product of its read.
    assert kept is (where == "channel")


async def test_a_date_no_datetime_can_hold_never_fails_the_read_that_offered_it() -> None:
    redis = _redis(1)
    with (
        patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)),
        patch(f"{MODULE}.publish_to_user", AsyncMock(return_value=True)),
    ):
        kept = await publish_companion_weather(uuid4(), reading(dt=10**20), now=NOW)

    assert kept is True


async def test_reads_back_the_kept_observation() -> None:
    observed = observe_current(reading(), now=NOW)
    assert observed is not None
    stored = json.dumps(
        {"observed_ms": 0, "observation": json.loads(observed.model_dump_json())}
    ).encode()
    redis = MagicMock()
    redis.get = AsyncMock(return_value=stored)
    with patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)):
        assert await read_companion_observation(uuid4()) == observed


@pytest.mark.parametrize("raw", [None, b"{broken", b'{"observation": {"temperature_c": "x"}}'])
async def test_nothing_or_garbage_reads_as_no_observation(raw: bytes | None) -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=raw)
    with patch(f"{MODULE}.get_redis_cache", AsyncMock(return_value=redis)):
        assert await read_companion_observation(uuid4()) is None


async def test_a_cache_failure_reads_as_no_observation() -> None:
    with patch(f"{MODULE}.get_redis_cache", AsyncMock(side_effect=ConnectionError("down"))):
        assert await read_companion_observation(uuid4()) is None
