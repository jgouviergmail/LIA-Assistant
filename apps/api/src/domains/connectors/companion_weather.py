"""The companion's weather: the present conditions at the person's place, from any read.

The companion never asks a weather provider (ADR-294): it shows what LIA already
read. It used to borrow ONE reader's cache, the dashboard card's, kept an hour,
while the heartbeat, the proactive discussions, the weather routines and the
chat's own weather tool read the same place many times a day and kept it to
themselves: an hour after the last dashboard visit the face lost its weather, and
only a page that rebuilt the card brought it back (owner report, 2026-11-13).

Every read of the PRESENT conditions at the person's own place now offers what it
observed here, through one door: ``publish_companion_weather``. The newest
observation stays — a script on the Redis server refuses an older one, since
readers run at their own pace on several workers — for as long as it is still the
present, and a new one is said on the person's real-time channel, so an open tab
shows it without being reloaded. ``read_companion_observation`` reads it back.

An observation holds no place: a temperature, a condition, a wind speed and the
instant the provider observed them. A city someone names in the chat is not the
person's present, and its reader never offers it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any, Final
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.constants import COMPANION_WEATHER_CACHE_PREFIX, PRESENT_WEATHER_FRESH_SECONDS
from src.domains.connectors.clients.weather_normalization import canonical_weather_main
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.user_channel import publish_to_user

logger = structlog.get_logger(__name__)

#: The event a person's open tabs receive when a newer observation was kept.
COMPANION_WEATHER_SIGNAL: Final = "companion_weather"

#: Keeps the newer observation: an older one, landing late from another reader,
#: leaves the kept one in place. KEYS[1] the account's key; ARGV the stored value,
#: its observation instant (ms) and how long it stays the present (ms).
KEEP_NEWER_SCRIPT: Final = """
local kept = redis.call('GET', KEYS[1])
if kept then
  local ok, decoded = pcall(cjson.decode, kept)
  if ok and type(decoded) == 'table' and tonumber(decoded['observed_ms'])
      and tonumber(decoded['observed_ms']) >= tonumber(ARGV[2]) then
    return 0
  end
end
redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[3])
return 1
"""


class CompanionObservation(BaseModel):
    """The present conditions at the person's place, as one read observed them."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    temperature_c: float = Field(ge=-100, le=65, description="Air temperature, Celsius.")
    condition_code: str = Field(
        min_length=1, max_length=32, description="Condition, in the OWM main vocabulary."
    )
    wind_speed_kmh: float | None = Field(
        default=None, ge=0, le=500, description="Wind speed, km/h, when the reading has one."
    )
    observed_at: datetime = Field(description="When the provider observed it (UTC).")


def companion_weather_key(user_id: UUID | str) -> str:
    """The Redis key of an account's newest present weather.

    Args:
        user_id: The account.

    Returns:
        The key, in the declared ``companion:weather`` family (``USER_CACHE``).
    """
    return f"{COMPANION_WEATHER_CACHE_PREFIX}:{user_id}"


def is_present(observed_at: datetime, now: datetime) -> bool:
    """Whether an observation is still the present: from its instant until it ages out.

    One rule for the door that keeps an observation and the endpoint that shows one
    (``briefing.companion``), so neither shows what the other would refuse.

    Args:
        observed_at: When the provider observed it.
        now: The instant of the question.

    Returns:
        True from ``observed_at`` until ``PRESENT_WEATHER_FRESH_SECONDS`` later.
    """
    return 0 <= (now - observed_at).total_seconds() < PRESENT_WEATHER_FRESH_SECONDS


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _observed_at(raw: object, now: datetime) -> datetime:
    """The provider's instant, never later than the read.

    An undated reading is now, and so is one whose instant no ``datetime`` can hold:
    unreadable is not a reason to fail the read that offered it.
    """
    stamp = _number(raw)
    if stamp is None:
        return now
    try:
        observed = datetime.fromtimestamp(stamp, UTC)
    except OverflowError, OSError, ValueError:
        return now
    return min(observed, now)


def observe_current(current: Mapping[str, Any], *, now: datetime) -> CompanionObservation | None:
    """What a ``get_current_weather`` answer says of the present, with nothing of the place.

    Both weather providers answer in the OWM shape (lot E, 2026-08). The wind is
    converted the way the dashboard card converts it (m/s to km/h, one decimal).

    Args:
        current: The answer of ``get_current_weather``.
        now: The instant of the read.

    Returns:
        The observation, or ``None`` when the answer has no readable temperature,
        holds an impossible value, or is no longer the present.
    """
    main = current.get("main")
    temperature = _number(main.get("temp")) if isinstance(main, Mapping) else None
    conditions = current.get("weather")
    first = conditions[0] if isinstance(conditions, list) and conditions else None
    condition = first.get("main") if isinstance(first, Mapping) else None
    wind = current.get("wind")
    speed = _number(wind.get("speed")) if isinstance(wind, Mapping) else None
    observed_at = _observed_at(current.get("dt"), now)
    if not is_present(observed_at, now):
        return None
    # The model refuses what is missing or impossible: no temperature, a value out of bounds.
    try:
        return CompanionObservation(
            temperature_c=temperature,
            condition_code=canonical_weather_main(condition if isinstance(condition, str) else ""),
            wind_speed_kmh=round(speed * 3.6, 1) if speed is not None else None,
            observed_at=observed_at,
        )
    except ValidationError:
        return None


async def publish_companion_weather(
    user_id: UUID, current: object, *, now: datetime | None = None
) -> bool:
    """Offer one read of the present at the person's place to their companion.

    The one door every reader of the present weather calls (guarded by
    ``test_companion_weather_readers_guard.py``). Never raises: the observation is
    a by-product of the reader's own work, whose outcome it must never change.

    Args:
        user_id: Whose place was read.
        current: The ``get_current_weather`` answer, as the reader received it:
            the clients' read contract types it ``object``, so anything but a
            mapping is refused here rather than cast by every caller.
        now: The instant of the read (defaults to now).

    Returns:
        True when the observation was kept (it was newer than the kept one).
    """
    instant = now or datetime.now(UTC)
    if not isinstance(current, Mapping):
        return False
    observation = observe_current(current, now=instant)
    if observation is None:
        return False
    observed_ms = int(observation.observed_at.timestamp() * 1000)
    present_ms = int(
        (observation.observed_at + timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS) - instant)
        / timedelta(milliseconds=1)
    )
    payload = json.dumps(
        {"observed_ms": observed_ms, "observation": observation.model_dump(mode="json")}
    )
    try:
        redis = await get_redis_cache()
        kept = await redis.eval(
            KEEP_NEWER_SCRIPT,
            1,
            companion_weather_key(user_id),
            payload,
            observed_ms,
            max(1, present_ms),
        )
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort here
        logger.debug("companion_weather_keep_failed", error_type=type(exc).__name__)
        return False
    if int(kept or 0) != 1:
        return False
    try:
        await publish_to_user(user_id, {"type": COMPANION_WEATHER_SIGNAL})
    except Exception as exc:  # noqa: BLE001 - a closed tab catches up on its next read
        logger.debug("companion_weather_signal_failed", error_type=type(exc).__name__)
    return True


async def read_companion_observation(user_id: UUID | str) -> CompanionObservation | None:
    """The newest present weather an account's reads left, or ``None``.

    Never raises: an absent, unreadable or unreachable value reads as no
    observation. Its age is the caller's to judge (``briefing.companion``).

    Args:
        user_id: The account.

    Returns:
        The kept observation.
    """
    try:
        redis = await get_redis_cache()
        raw = await redis.get(companion_weather_key(user_id))
        if raw is None:
            return None
        stored = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return CompanionObservation.model_validate(stored["observation"])
    except Exception as exc:  # noqa: BLE001 - absent and unreadable are the same answer
        logger.debug("companion_weather_read_failed", error_type=type(exc).__name__)
        return None
