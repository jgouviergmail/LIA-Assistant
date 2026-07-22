"""Standalone heartbeat context sources and pure detection rules.

Extracted from ``ContextAggregator`` (interdomain program Lot 1) to keep
``context_aggregator.py`` under its frozen file-size cap — a logical file
never grows (CLAUDE.md). Everything here is either a pure rules function
(weather transition detection) or a self-contained source fetcher that
manages its own I/O (birthdays with a Redis cache, other-surface
notification window). ``ContextAggregator`` keeps thin delegate methods so
its orchestration surface is unchanged.

This module must NEVER import ``context_aggregator`` (one-way dependency).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.heartbeat.schemas import WeatherChange

logger = structlog.get_logger(__name__)

# P10 — extended anti-redundancy window: archived proactive messages from
# other surfaces, mapped metadata ``type`` → compact kind label for the
# decision prompt. Heartbeat and interest notifications are NOT listed here:
# they have their own dedicated windows (double-counting would dilute both).
_OTHER_PROACTIVE_METADATA_KINDS: dict[str, str] = {
    "proactive_reminder": "reminder",
    "proactive_phone_call": "phone_call",
}

# Per-source row cap for the extended window (3 sources → ≤ 9 lines of prompt).
_OTHER_NOTIFICATIONS_LIMIT_PER_SOURCE = 3


def format_utc_datetime(dt: datetime | None, user_tz: ZoneInfo) -> str:
    """Convert a UTC-aware datetime to a compact user-local string.

    Used for timestamps from the database (created_at fields) that are
    stored in UTC and need user-friendly display in the LLM prompt.

    Returns:
        Formatted string like '2026-03-15 15:30' or '?' if None.
    """
    if dt is None:
        return "?"
    try:
        local_dt = dt.astimezone(user_tz)
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, AttributeError):
        return str(dt)


def resolve_user_tz(user: Any) -> ZoneInfo:
    """Resolve the user's timezone with safe fallback.

    Falls back to DEFAULT_USER_DISPLAY_TIMEZONE if the user's timezone
    attribute is missing, None, or invalid.
    """
    try:
        return ZoneInfo(user.timezone)
    except (KeyError, ValueError, AttributeError, TypeError):
        return ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)


def detect_weather_changes(
    current: dict[str, Any],
    hourly: list[dict[str, Any]],
    user_tz: ZoneInfo,
    settings: Any,
) -> list[WeatherChange]:
    """Detect notable weather transitions between now and forecast.

    Temperature detection compares the average temperature of today vs
    tomorrow (in the user's local timezone) to filter out the natural
    day/night cycle, which previously caused noisy "temperature drop"
    alerts about nighttime cooling. Rain and wind alerts still use the
    3-hour forecast entries directly.

    The current weather API (/data/2.5/weather) does NOT return 'pop'.
    We use weather[0].main (e.g. "Rain", "Clear") for current state,
    then forecast 'pop' values for predictions.

    Args:
        current: Current weather data from API.
        hourly: Forecast entries (3-hour intervals).
        user_tz: User's timezone for time display.
        settings: App settings with threshold values.

    Returns:
        List of detected WeatherChange events.
    """
    changes: list[WeatherChange] = []

    current_condition = current.get("weather", [{}])[0].get("main", "").lower()
    is_currently_raining = current_condition in (
        "rain",
        "drizzle",
        "thunderstorm",
    )

    rain_high = settings.heartbeat_weather_rain_threshold_high
    rain_low = settings.heartbeat_weather_rain_threshold_low
    temp_threshold = settings.heartbeat_weather_temp_change_threshold
    wind_threshold = settings.heartbeat_weather_wind_threshold

    # Track detected types to avoid duplicate detections
    detected_types: set[str] = set()

    # Temperature change: today vs tomorrow average (local timezone).
    # Requires at least 2 entries per day to avoid biased averages when
    # the job runs near local midnight.
    today_date = datetime.now(user_tz).date()
    tomorrow_date = today_date + timedelta(days=1)
    temps_today: list[float] = []
    temps_tomorrow: list[float] = []
    for entry in hourly:
        try:
            entry_time = datetime.fromtimestamp(entry["dt"], tz=user_tz)
        except (KeyError, ValueError, OSError):
            continue
        entry_temp = entry.get("main", {}).get("temp")
        if entry_temp is None:
            continue
        if entry_time.date() == today_date:
            temps_today.append(entry_temp)
        elif entry_time.date() == tomorrow_date:
            temps_tomorrow.append(entry_temp)

    if len(temps_today) >= 2 and len(temps_tomorrow) >= 2:
        avg_today = sum(temps_today) / len(temps_today)
        avg_tomorrow = sum(temps_tomorrow) / len(temps_tomorrow)
        diff = avg_today - avg_tomorrow  # > 0: colder tomorrow, < 0: warmer
        if abs(diff) > temp_threshold:
            change_type = "temp_drop" if diff > 0 else "temp_rise"
            direction = "colder" if diff > 0 else "warmer"
            severity = "warning" if abs(diff) > temp_threshold * 1.6 else "info"
            expected_at = datetime.combine(tomorrow_date, time(12, 0), tzinfo=user_tz)
            changes.append(
                WeatherChange(
                    change_type=change_type,
                    expected_at=expected_at,
                    description=(
                        f"Tomorrow {abs(diff):.0f}°C {direction} on average "
                        f"({avg_tomorrow:.0f}°C vs {avg_today:.0f}°C today)"
                    ),
                    severity=severity,
                )
            )
            detected_types.add(change_type)

    for entry in hourly:
        entry_pop = entry.get("pop", 0)
        try:
            entry_time = datetime.fromtimestamp(entry["dt"], tz=user_tz)
        except (KeyError, ValueError, OSError):
            continue

        time_str = entry_time.strftime("%H:%M")

        # Rain start: not raining now + high pop in forecast
        if (
            not is_currently_raining
            and entry_pop > rain_high
            and "rain_start" not in detected_types
        ):
            changes.append(
                WeatherChange(
                    change_type="rain_start",
                    expected_at=entry_time,
                    description=f"Rain expected around {time_str}",
                    severity="warning",
                )
            )
            detected_types.add("rain_start")
            is_currently_raining = True

        # Rain end: raining now + low pop in forecast
        elif is_currently_raining and entry_pop < rain_low and "rain_end" not in detected_types:
            changes.append(
                WeatherChange(
                    change_type="rain_end",
                    expected_at=entry_time,
                    description=f"Rain clearing around {time_str}",
                    severity="info",
                )
            )
            detected_types.add("rain_end")
            is_currently_raining = False

        # Wind alert
        wind_speed = entry.get("wind", {}).get("speed", 0)
        if wind_speed > wind_threshold and "wind_alert" not in detected_types:
            changes.append(
                WeatherChange(
                    change_type="wind_alert",
                    expected_at=entry_time,
                    description=f"Strong wind expected ({wind_speed:.0f} m/s)",
                    severity="warning",
                )
            )
            detected_types.add("wind_alert")

    return changes


# ------------------------------------------------------------------
# Birthdays source (P7 — shared connectors fetch, midnight-scoped cache)
# ------------------------------------------------------------------


async def fetch_birthdays_context(
    user_id: UUID,
    user: Any,
    settings: Any,
) -> list[dict[str, Any]] | None:
    """Fetch upcoming contact birthdays for the decision prompt.

    Cache-first: the underlying Google People fetch is a full contacts
    scan (up to 5 paginated calls), so results are cached in Redis until
    the next LOCAL midnight (``days_until`` is pre-computed — the same
    rationale as the briefing birthdays card). An empty scan is cached
    too (the emptiness is what cost the scan); a not-configured
    connector is NOT cached (the credential lookup is cheap).

    Silent-None on every failure — birthdays are a bonus source, never
    a blocker.

    Returns:
        List of {contact_name, days_until, age_at_next} dicts or None.
    """
    from src.core.constants import HEARTBEAT_BIRTHDAYS_MAX_ITEMS
    from src.core.time_utils import seconds_to_next_local_midnight

    user_tz = resolve_user_tz(user)
    cache_key = f"heartbeat:birthdays:{user_id}"

    redis = None
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if redis:
            cached = await redis.get(cache_key)
            if cached is not None:
                data = json.loads(cached)
                return data or None
    except Exception as e:
        logger.debug("heartbeat_birthdays_cache_read_failed", error=str(e))

    try:
        from src.domains.connectors.birthdays import fetch_upcoming_birthdays

        items = await fetch_upcoming_birthdays(
            user_id,
            user_tz,
            horizon_days=settings.heartbeat_context_birthdays_days,
            max_items=HEARTBEAT_BIRTHDAYS_MAX_ITEMS,
        )
    except Exception as e:
        # BirthdayFetchError and anything unexpected: bonus source, degrade.
        logger.warning(
            "heartbeat_birthdays_fetch_failed",
            user_id=str(user_id),
            error=str(e),
        )
        return None

    if items is None:
        return None

    payload: list[dict[str, Any]] = [
        {
            "contact_name": item.contact_name,
            "days_until": item.days_until,
            "age_at_next": item.age_at_next,
        }
        for item in items
    ]

    if redis:
        try:
            await redis.set(
                cache_key,
                json.dumps(payload),
                ex=seconds_to_next_local_midnight(user_tz),
            )
        except Exception as e:
            logger.debug("heartbeat_birthdays_cache_write_failed", error=str(e))

    return payload or None


# ------------------------------------------------------------------
# Open loops source (P5 — commitments ledger, ADR-139)
# ------------------------------------------------------------------


async def fetch_open_loops_context(
    db: AsyncSession,
    user_id: UUID,
    user: Any,
    settings: Any,
) -> list[dict[str, Any]] | None:
    """Fetch nudge-worthy open loops for the decision prompt.

    Runs the lazy soft-expiry first (no dedicated scheduler job — ADR-139),
    then filters the user's OPEN loops down to the nudge-worthy subset:

    - due within ``open_loops_nudge_due_hours`` (or overdue), OR
    - untouched for ``open_loops_nudge_stale_days`` (no-deadline loops);
    - AND outside the per-loop cooldown (``last_nudged_at`` older than
      ``open_loops_nudge_cooldown_days`` or never nudged).

    Entries carry the loop ``id`` so ``proactive_task`` can bump the
    cooldown fields after a delivered notification actually used the
    OPEN_LOOPS source.

    Returns:
        List of {id, subject, counterparty, direction, due_local, days_open}
        or None when the feature is disabled / nothing is nudge-worthy.
    """
    if not getattr(settings, "open_loops_enabled", False):
        return None

    from src.domains.open_loops.repository import OpenLoopRepository

    repo = OpenLoopRepository(db)
    now = datetime.now(UTC)

    # Lazy soft-expiry (commit handled by the fetcher's scoped session).
    await repo.expire_stale(user_id, cutoff=now - timedelta(days=settings.open_loops_expiry_days))

    loops = await repo.list_open_for_user(user_id, limit=settings.open_loops_max_open_per_user)
    if not loops:
        return None

    due_window = timedelta(hours=settings.open_loops_nudge_due_hours)
    stale_cutoff = now - timedelta(days=settings.open_loops_nudge_stale_days)
    cooldown_cutoff = now - timedelta(days=settings.open_loops_nudge_cooldown_days)
    user_tz = resolve_user_tz(user)

    entries: list[dict[str, Any]] = []
    for loop in loops:
        if loop.last_nudged_at is not None and loop.last_nudged_at > cooldown_cutoff:
            continue
        due_worthy = loop.due_hint is not None and loop.due_hint <= now + due_window
        stale_worthy = loop.due_hint is None and loop.updated_at <= stale_cutoff
        if not (due_worthy or stale_worthy):
            continue
        entries.append(
            {
                "id": str(loop.id),
                "subject": loop.subject,
                "counterparty": loop.counterparty,
                "direction": loop.direction,
                "due_local": (
                    format_utc_datetime(loop.due_hint, user_tz) if loop.due_hint else None
                ),
                "days_open": max(0, (now - loop.created_at).days),
            }
        )

    return entries or None


# ------------------------------------------------------------------
# Recent other proactive surfaces (P10 — extended anti-redundancy)
# ------------------------------------------------------------------


async def fetch_recent_other_notifications(
    db: AsyncSession,
    user_id: UUID,
    user: Any,
) -> list[dict[str, str]] | None:
    """Fetch proactive messages delivered by OTHER surfaces in the window.

    Two indexed queries, merged most-recent-first:
    - Archived proactive conversation messages (fired reminders and
      telephony call reports — ``message_metadata.type`` is set by the
      NotificationDispatcher archive path).
    - Scheduled-action executions (their results are archived as regular
      chat messages by ``stream_chat_response``, so the reliable signal
      is ``ScheduledAction.last_executed_at`` + title).

    Heartbeat/interest notifications are excluded: they already have
    dedicated windows (``_fetch_recent_heartbeats`` /
    ``_fetch_recent_interest_notifications``).

    Returns:
        List of {kind, created_at, content} dicts (user-local times,
        content excerpts) or None when nothing was delivered recently.
    """
    from src.core.constants import HEARTBEAT_CONTENT_EXCERPT_CHARS as _EXCERPT
    from src.domains.scheduled_actions.models import ScheduledAction

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.heartbeat_recent_window_days)
    user_tz = resolve_user_tz(user)
    rows: list[tuple[datetime, str, str]] = []

    # 1. Archived proactive messages (reminders, phone-call reports)
    result = await db.execute(
        select(
            ConversationMessage.created_at,
            ConversationMessage.content,
            ConversationMessage.message_metadata,
        )
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            ConversationMessage.created_at >= cutoff,
            ConversationMessage.message_metadata["type"].astext.in_(
                list(_OTHER_PROACTIVE_METADATA_KINDS)
            ),
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(_OTHER_NOTIFICATIONS_LIMIT_PER_SOURCE * 2)
    )
    for row in result.all():
        meta_type = (row.message_metadata or {}).get("type", "")
        kind = _OTHER_PROACTIVE_METADATA_KINDS.get(meta_type, "proactive")
        rows.append((row.created_at, kind, (row.content or "")[:_EXCERPT]))

    # 2. Scheduled-action executions (title names the delivered topic)
    result = await db.execute(
        select(ScheduledAction.title, ScheduledAction.last_executed_at)
        .where(
            ScheduledAction.user_id == user_id,
            ScheduledAction.last_executed_at.is_not(None),
            ScheduledAction.last_executed_at >= cutoff,
        )
        .order_by(ScheduledAction.last_executed_at.desc())
        .limit(_OTHER_NOTIFICATIONS_LIMIT_PER_SOURCE)
    )
    for row in result.all():
        rows.append((row.last_executed_at, "scheduled_action", row.title))

    if not rows:
        return None

    rows.sort(key=lambda r: r[0], reverse=True)
    return [
        {
            "kind": kind,
            "created_at": format_utc_datetime(created_at, user_tz),
            "content": content,
        }
        for created_at, kind, content in rows
    ]


# ------------------------------------------------------------------
# Departure advice (P6 — calendar × route × weather fusion)
# ------------------------------------------------------------------


def _parse_event_start(dt_field: dict[str, Any] | None, user_tz: ZoneInfo) -> datetime | None:
    """Parse a calendar start dict to an aware datetime (tolerant, None on failure)."""
    if not dt_field:
        return None
    raw = dt_field.get("dateTime")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        tz_name = dt_field.get("timeZone")
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(tz_name) if tz_name else user_tz)
        except (KeyError, ValueError):
            parsed = parsed.replace(tzinfo=user_tz)
    return parsed


def _departure_cache_key(user_id: UUID, target: dict[str, Any], start: datetime) -> str:
    """Deterministic Redis key for the per-(user, event) ETA budget cache.

    Built on a sha1 digest of the event identity triple — NEVER the builtin
    ``hash()``, whose string hashing is randomized per process
    (PYTHONHASHSEED): a randomized key would miss the cache on every other
    worker/restart and defeat the paid-Routes budget.
    """
    digest = hashlib.sha1(
        f"{target.get('summary')}|{target.get('location')}|{start.isoformat()}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]
    return f"heartbeat:departure:{user_id}:{digest}"


def _pick_departure_target(
    calendar_events: list[dict[str, Any]],
    user_tz: ZoneInfo,
    now: datetime,
    lookahead: timedelta,
) -> tuple[dict[str, Any], datetime] | None:
    """First located, parseable, in-window event — the departure candidate."""
    for event in calendar_events:
        if not event.get("location"):
            continue
        start = _parse_event_start(event.get("start_raw"), user_tz)
        if start is None or start <= now or start > now + lookahead:
            continue
        return event, start
    return None


async def fetch_departure_advice(
    user_id: UUID,
    user: Any,
    settings: Any,
    calendar_events: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Traffic-aware leave-by advice for the next located event (P6).

    Second-pass consumer: reuses the calendar events already fetched by the
    first pass (``start_raw`` carries the provider start dict). Budget is
    strict — at most ONE Routes call per cycle, Redis-cached per
    (user, event) for ``heartbeat_departure_cache_ttl_seconds``. Silent-None
    on every gate or failure (bonus source, never a blocker).

    Returns:
        {event_title, event_start_local, eta_minutes, leave_by_local,
        destination} or None.
    """
    if not getattr(settings, "heartbeat_departure_enabled", False):
        return None
    if not calendar_events:
        return None

    user_tz = resolve_user_tz(user)
    now = datetime.now(UTC)
    lookahead = timedelta(hours=settings.heartbeat_departure_lookahead_hours)

    picked = _pick_departure_target(calendar_events, user_tz, now, lookahead)
    if picked is None:
        return None
    target, target_start = picked

    cache_key = _departure_cache_key(user_id, target, target_start)
    redis = None
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if redis:
            cached = await redis.get(cache_key)
            if cached is not None:
                loaded = json.loads(cached)
                return loaded if isinstance(loaded, dict) else None
    except Exception as e:
        logger.debug("heartbeat_departure_cache_read_failed", error=str(e))

    from src.domains.users.user_location_service import NoLocationAvailableError

    language = getattr(user, "language", None) or settings.default_language
    try:
        advice = await _compute_departure_advice(user, target, target_start, user_tz, language)
        if advice is None:
            return None
        if redis:
            try:
                await redis.set(
                    cache_key,
                    json.dumps(advice),
                    ex=settings.heartbeat_departure_cache_ttl_seconds,
                )
            except Exception as e:
                logger.debug("heartbeat_departure_cache_write_failed", error=str(e))
        return advice
    except NoLocationAvailableError:
        # Expected gate, not a failure: no home location configured means the
        # origin cannot be resolved — stay silent (bonus source, every cycle).
        logger.debug("heartbeat_departure_no_location", user_id=str(user_id))
        return None
    except Exception as e:
        logger.warning(
            "heartbeat_departure_failed",
            user_id=str(user_id),
            error=str(e),
        )
        return None


async def _compute_departure_advice(
    user: Any,
    target: dict[str, Any],
    target_start: datetime,
    user_tz: ZoneInfo,
    language: str,
) -> dict[str, Any] | None:
    """Resolve origin, call Routes (traffic-aware), build the advice dict.

    Raises:
        NoLocationAvailableError: When the user has no home location — the
            caller treats it as an expected gate (silent None).
    """
    from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient
    from src.domains.users.user_location_service import UserLocationService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        effective = await UserLocationService(db).get_effective_location_for_proactive(user)

    client = GoogleRoutesClient(language=language)
    try:
        route = await client.compute_route(
            origin=f"{effective.lat},{effective.lon}",
            destination=str(target["location"]),
            arrival_time=target_start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    finally:
        await client.close()

    routes = route.get("routes") or []
    duration_str = str((routes[0] if routes else {}).get("duration", ""))
    if not duration_str.endswith("s"):
        return None
    eta_minutes = max(1, int(duration_str.rstrip("s")) // 60)
    leave_by = target_start - timedelta(minutes=eta_minutes)

    return {
        "event_title": target.get("summary", "Untitled"),
        "event_start_local": target_start.astimezone(user_tz).strftime("%H:%M"),
        "eta_minutes": eta_minutes,
        "leave_by_local": leave_by.astimezone(user_tz).strftime("%H:%M"),
        "destination": str(target["location"]),
    }
