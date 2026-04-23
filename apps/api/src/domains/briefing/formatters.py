"""UI-facing formatters — raw API/DB data to UI-ready models.

Pure functions: no DB, no I/O, no global state. Trivially unit-testable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.core.time_utils import format_time_with_date_context
from src.domains.briefing.constants import BRIEFING_WEATHER_DAILY_FORECAST_DAYS
from src.domains.briefing.schemas import (
    AgendaEventItem,
    BirthdayItem,
    DailyForecastItem,
    HealthSummaryItem,
    MailItem,
    ReminderItem,
    WeatherData,
)
from src.domains.reminders.models import Reminder

# =============================================================================
# Weather formatting
# =============================================================================

# Map OpenWeatherMap "main" condition codes to a single emoji.
# Reference: https://openweathermap.org/weather-conditions
WEATHER_EMOJI_MAP: dict[str, str] = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Mist": "🌫️",
    "Smoke": "🌫️",
    "Haze": "🌫️",
    "Dust": "🌫️",
    "Fog": "🌫️",
    "Sand": "🌫️",
    "Ash": "🌫️",
    "Squall": "🌬️",
    "Tornado": "🌪️",
}
WEATHER_EMOJI_DEFAULT = "🌤️"


def format_weather_data(
    *,
    current: dict[str, Any],
    forecast: dict[str, Any],
    city: str | None,
    user_tz: ZoneInfo,
) -> WeatherData:
    """Build a WeatherData payload from OpenWeatherMap responses.

    Description is taken from the API (already localized via the ``lang`` param).
    Min/max temperatures and precipitation probability come from the forecast
    (today's slots only). Wind speed is converted from m/s to km/h.

    Args:
        current: Response of ``client.get_current_weather()``.
        forecast: Response of ``client.get_forecast()`` (cnt=8 = next ~24 h).
        city: Reverse-geocoded city name (or None if resolution failed).
        user_tz: User timezone for slot filtering and time labels.

    Returns:
        WeatherData ready for the UI.
    """
    main = current.get("main", {}) or {}
    temp = float(main.get("temp", 0.0))

    weather_arr = current.get("weather", []) or []
    first = weather_arr[0] if weather_arr else {}
    condition_code = first.get("main", "Unknown") or "Unknown"
    description = (first.get("description") or "").strip()
    if description:
        # OWM returns lowercase descriptions — capitalize first letter for display
        description = description[0].upper() + description[1:]

    icon_emoji = WEATHER_EMOJI_MAP.get(condition_code, WEATHER_EMOJI_DEFAULT)

    # Wind: convert m/s → km/h, format cardinal direction.
    wind = current.get("wind", {}) or {}
    wind_speed_ms = wind.get("speed")
    wind_speed_kmh: float | None = (
        round(float(wind_speed_ms) * 3.6, 1) if wind_speed_ms is not None else None
    )
    wind_deg = wind.get("deg")
    wind_direction_cardinal: str | None = _wind_deg_to_cardinal(wind_deg)

    # Today's min/max from forecast slots in user's local "today" date.
    temp_min, temp_max = _today_min_max_from_forecast(forecast, user_tz)

    # Next 3 h precipitation probability (first forecast slot).
    pop_first = _first_forecast_pop(forecast)

    forecast_alert = _detect_forecast_alert(current=current, forecast=forecast, user_tz=user_tz)

    # 5-day daily summary aggregated from the 3-h forecast slots.
    daily_forecast = _aggregate_daily_forecast(forecast, user_tz)

    return WeatherData(
        temperature_c=round(temp, 1),
        temperature_min_c=temp_min,
        temperature_max_c=temp_max,
        condition_code=condition_code,
        description=description or condition_code,
        icon_emoji=icon_emoji,
        location_city=city,
        wind_speed_kmh=wind_speed_kmh,
        wind_direction_cardinal=wind_direction_cardinal,
        precipitation_probability=pop_first,
        forecast_alert=forecast_alert,
        daily_forecast=daily_forecast,
    )


# Conditions ranked by "severity" — when a day has a mix, we surface the more
# notable one as the daily icon (rain dominates over clear, etc.).
_CONDITION_SEVERITY: dict[str, int] = {
    "Thunderstorm": 100,
    "Tornado": 100,
    "Snow": 90,
    "Rain": 80,
    "Drizzle": 70,
    "Squall": 60,
    "Fog": 50,
    "Mist": 50,
    "Haze": 50,
    "Smoke": 50,
    "Dust": 50,
    "Sand": 50,
    "Ash": 50,
    "Clouds": 30,
    "Clear": 10,
}


def _pick_dominant_condition(condition_codes: list[str]) -> str:
    """Pick the most representative condition code for a day.

    Rule: the condition with the highest severity score wins. If two conditions
    tie (e.g. all "Clear"), the most frequent one wins (mode).
    """
    if not condition_codes:
        return "Unknown"
    # Count occurrences
    counts: dict[str, int] = {}
    for code in condition_codes:
        counts[code] = counts.get(code, 0) + 1
    # Sort by (severity desc, count desc) and take the first
    return max(
        counts.keys(),
        key=lambda c: (_CONDITION_SEVERITY.get(c, 20), counts[c]),
    )


def _aggregate_daily_forecast(
    forecast: dict[str, Any],
    user_tz: ZoneInfo,
) -> list[DailyForecastItem]:
    """Aggregate the 3-h forecast slots into per-day summaries (today + next N days).

    For each day:
    - temp_min / temp_max = min and max across all slots of that day
    - condition_code = dominant condition (severity-weighted, then frequency)
    - icon_emoji from WEATHER_EMOJI_MAP

    Days with too few slots (e.g. last day with only 1 slot late at night) are
    still surfaced — the user benefits from any signal beyond today.
    """
    today_local = datetime.now(user_tz).date()
    horizon_end = today_local.toordinal() + (BRIEFING_WEATHER_DAILY_FORECAST_DAYS - 1)

    by_day: dict[str, dict[str, Any]] = {}
    for entry in forecast.get("list", []) or []:
        try:
            ts = entry.get("dt")
            if ts is None:
                continue
            slot_local = datetime.fromtimestamp(int(ts), tz=user_tz)
            slot_date = slot_local.date()
            if slot_date.toordinal() > horizon_end:
                continue
            date_key = slot_date.isoformat()
        except (ValueError, TypeError, OSError):
            continue

        bucket = by_day.setdefault(date_key, {"temps": [], "conditions": [], "date_obj": slot_date})

        slot_main = entry.get("main", {}) or {}
        for key in ("temp_min", "temp_max", "temp"):
            val = slot_main.get(key)
            if val is not None:
                try:
                    bucket["temps"].append(float(val))
                except (TypeError, ValueError):
                    pass

        weather_arr = entry.get("weather", []) or []
        if weather_arr:
            code = weather_arr[0].get("main")
            if code:
                bucket["conditions"].append(str(code))

    items: list[DailyForecastItem] = []
    for date_key in sorted(by_day.keys()):
        bucket = by_day[date_key]
        if not bucket["temps"]:
            continue
        condition = _pick_dominant_condition(bucket["conditions"])
        items.append(
            DailyForecastItem(
                date_iso=date_key,
                temp_min_c=round(min(bucket["temps"]), 1),
                temp_max_c=round(max(bucket["temps"]), 1),
                condition_code=condition,
                icon_emoji=WEATHER_EMOJI_MAP.get(condition, WEATHER_EMOJI_DEFAULT),
            )
        )
    return items[:BRIEFING_WEATHER_DAILY_FORECAST_DAYS]


# Cardinal direction lookup — 8 sectors of 45° each, centered on N=0°.
_CARDINALS: tuple[str, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _wind_deg_to_cardinal(deg: float | int | None) -> str | None:
    """Convert wind degrees (0-360, 0=N, clockwise) to a cardinal point.

    Uses 8 equal sectors of 45° centered on each cardinal/intercardinal point:
    N covers [-22.5, 22.5), NE [22.5, 67.5), E [67.5, 112.5), etc.
    """
    if deg is None:
        return None
    try:
        d = float(deg) % 360
    except (TypeError, ValueError):
        return None
    # Shift by +22.5 then floor-divide by 45 → index 0..7 in _CARDINALS.
    index = int(((d + 22.5) % 360) // 45)
    return _CARDINALS[index]


def _today_min_max_from_forecast(
    forecast: dict[str, Any],
    user_tz: ZoneInfo,
) -> tuple[float | None, float | None]:
    """Extract today's expected min/max temperatures from forecast 3 h slots.

    Falls back to (None, None) when no slot for today is available (e.g. fetched
    after 21h with cnt=8 covering only future days).
    """
    today_local = datetime.now(user_tz).date()
    temps: list[float] = []
    for entry in forecast.get("list", []) or []:
        try:
            ts = entry.get("dt")
            if ts is None:
                continue
            slot_local = datetime.fromtimestamp(int(ts), tz=user_tz)
            if slot_local.date() != today_local:
                continue
            slot_main = entry.get("main", {}) or {}
            t_min = slot_main.get("temp_min")
            t_max = slot_main.get("temp_max")
            if t_min is not None:
                temps.append(float(t_min))
            if t_max is not None:
                temps.append(float(t_max))
        except (ValueError, TypeError, OSError):
            continue
    if not temps:
        return None, None
    return round(min(temps), 1), round(max(temps), 1)


def _first_forecast_pop(forecast: dict[str, Any]) -> float | None:
    """Return the precipitation probability (0.0 – 1.0) of the next forecast slot."""
    entries = forecast.get("list", []) or []
    if not entries:
        return None
    pop = entries[0].get("pop")
    if pop is None:
        return None
    try:
        value = float(pop)
    except (TypeError, ValueError):
        return None
    # Clamp to [0, 1] just in case the API ever returns out-of-range values.
    return max(0.0, min(1.0, value))


def _detect_forecast_alert(
    *,
    current: dict[str, Any],
    forecast: dict[str, Any],
    user_tz: ZoneInfo,
) -> str | None:
    """Detect a notable upcoming change in the next 24 h.

    Looks for the first rain/thunder/snow start in the forecast list when the
    current weather isn't already in that state. Returns a short localized-style
    string suitable for direct display ("Rain expected at 16:00") — kept short
    so the LLM synthesis can elaborate if desired.

    Args:
        current: Current weather response.
        forecast: Forecast response (3-h slots).
        user_tz: User timezone for time formatting.

    Returns:
        One-liner alert string, or None if no notable change.
    """
    current_arr = current.get("weather", []) or []
    current_main = (current_arr[0].get("main") if current_arr else "") or ""

    NOTABLE = {"Rain", "Thunderstorm", "Snow", "Drizzle"}
    if current_main in NOTABLE:
        return None  # already happening — no point alerting

    entries = forecast.get("list", []) or []
    for entry in entries:
        weather_arr = entry.get("weather", []) or []
        if not weather_arr:
            continue
        slot_main = weather_arr[0].get("main", "") or ""
        if slot_main not in NOTABLE:
            continue
        try:
            ts = entry.get("dt")
            if ts is None:
                continue
            dt = datetime.fromtimestamp(int(ts), tz=user_tz)
            time_str = dt.strftime("%H:%M")
            return f"{slot_main} expected at {time_str}"
        except (ValueError, TypeError, OSError):
            continue
    return None


# =============================================================================
# Agenda formatting (multi-provider event normalization)
# =============================================================================


def is_event_past(raw_event: dict[str, Any], now: datetime, user_tz: ZoneInfo) -> bool:
    """Return True when the event has already ended (end strictly before now).

    Used to filter out lingering "in progress just before time_min" events the
    Google Calendar API may still return due to its inclusive end-time filter.
    All-day events with ``end.date == today`` are considered past at midnight.

    Args:
        raw_event: Raw event dict (any provider).
        now: Reference datetime (UTC or tz-aware).
        user_tz: User timezone (used for naive datetime resolution).

    Returns:
        True if the event ended before now → caller should skip it.
        False if still ongoing or in the future.
        False also when end is missing/unparseable (we don't drop events
        on unknown end — they remain visible).
    """
    end_field = raw_event.get("end")
    if not end_field:
        return False
    # All-day: end is the day AFTER the last day (Google convention).
    date_str = end_field.get("date")
    if date_str and not end_field.get("dateTime"):
        try:
            end_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=user_tz)
            return end_date <= now.astimezone(user_tz)
        except (ValueError, TypeError):
            return False
    raw = end_field.get("dateTime")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            event_tz_str = end_field.get("timeZone")
            try:
                dt = dt.replace(tzinfo=ZoneInfo(event_tz_str) if event_tz_str else user_tz)
            except (KeyError, ValueError):
                dt = dt.replace(tzinfo=user_tz)
        return dt <= now.astimezone(dt.tzinfo or user_tz)
    except (ValueError, TypeError):
        return False


def format_agenda_event(raw_event: dict[str, Any], user_tz: ZoneInfo) -> AgendaEventItem:
    """Convert a Google/Apple/Microsoft event dict to UI item.

    Mirrors the proven logic from heartbeat.context_aggregator._format_event_time
    so multi-provider behaviour is consistent across the app. Both start and
    end are formatted; end is None if missing or formatting fails.
    """
    title = raw_event.get("summary") or "Untitled"
    location = raw_event.get("location")
    start_local = _format_event_time(raw_event.get("start"), user_tz)
    end_field = raw_event.get("end")
    end_local: str | None = None
    if end_field:
        formatted_end = _format_event_time(end_field, user_tz)
        # Skip the placeholder for missing data so the UI can hide the line.
        if formatted_end and formatted_end != "?":
            end_local = formatted_end
    return AgendaEventItem(
        title=title,
        start_local=start_local,
        end_local=end_local,
        location=location if location else None,
    )


def _format_event_time(dt_field: dict[str, Any] | None, user_tz: ZoneInfo) -> str:
    """Convert a calendar event start/end dict to a human-readable local time.

    Handles all three providers (Google offset, Microsoft timeZone field, Apple
    naive datetime) and all-day events. Naive datetimes default to the user's
    local timezone — correct for CalDAV.

    Returns:
        - 'HH:MM' if today
        - 'YYYY-MM-DD HH:MM' if other day
        - 'YYYY-MM-DD (all day)' for all-day events
        - '?' for missing data
    """
    if not dt_field:
        return "?"

    # All-day event
    date_str = dt_field.get("date")
    if date_str and not dt_field.get("dateTime"):
        return f"{date_str} (all day)"

    raw = dt_field.get("dateTime")
    if not raw:
        return "?"

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            event_tz_str = dt_field.get("timeZone")
            if event_tz_str:
                try:
                    event_tz = ZoneInfo(event_tz_str)
                except (KeyError, ValueError):
                    event_tz = user_tz
            else:
                event_tz = user_tz
            dt = dt.replace(tzinfo=event_tz)

        local_dt = dt.astimezone(user_tz)
        now_local = datetime.now(user_tz)
        if local_dt.date() != now_local.date():
            return local_dt.strftime("%Y-%m-%d %H:%M")
        return local_dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return str(raw)


# =============================================================================
# Mail formatting
# =============================================================================


def format_email_item(raw_msg: dict[str, Any], user_tz: ZoneInfo) -> MailItem:
    """Convert a normalized email message to a MailItem.

    Parses the RFC 2822 ``from`` header to extract display name + email.
    All providers normalize messages to top-level ``from`` / ``subject`` /
    ``internalDate`` fields, so a single accessor works.
    """
    raw_from = (raw_msg.get("from") or "").strip()
    sender_name, sender_email = _parse_from_header(raw_from)
    subject = (raw_msg.get("subject") or "").strip() or "(no subject)"
    received_local = _format_email_internal_date(raw_msg.get("internalDate"), user_tz)
    return MailItem(
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        received_local=received_local,
    )


# Pre-compiled regex for parsing 'Display Name <email@domain.com>' (RFC 2822 friendly).
_FROM_HEADER_REGEX = __import__("re").compile(r'^"?(.*?)"?\s*<\s*([^>\s]+)\s*>\s*$')


def _parse_from_header(raw: str) -> tuple[str | None, str | None]:
    """Extract (display_name, email) from a raw RFC 2822 From header.

    Examples:
        'Sophie Martin <sophie@acme.com>'      → ('Sophie Martin', 'sophie@acme.com')
        '"Sophie, M." <sophie@acme.com>'       → ('Sophie, M.', 'sophie@acme.com')
        'sophie@acme.com'                      → (None, 'sophie@acme.com')
        'Sophie Martin'                        → ('Sophie Martin', None)
        ''                                     → (None, None)
    """
    if not raw:
        return None, None
    raw = raw.strip()
    match = _FROM_HEADER_REGEX.match(raw)
    if match:
        name = match.group(1).strip().strip('"').strip()
        email = match.group(2).strip()
        return (name or None), (email or None)
    if "@" in raw:
        return None, raw
    return raw, None


def _format_email_internal_date(internal_date: str | int | None, user_tz: ZoneInfo) -> str:
    """Convert email ``internalDate`` (epoch ms) to a user-local time string.

    Returns:
        'HH:MM' if today, 'YYYY-MM-DD HH:MM' otherwise, '?' if missing/invalid.
    """
    if internal_date is None:
        return "?"
    try:
        epoch_ms = int(internal_date)
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=user_tz)
        now_local = datetime.now(user_tz)
        if dt.date() == now_local.date():
            return dt.strftime("%H:%M")
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return "?"


# =============================================================================
# Reminder formatting
# =============================================================================


def format_reminder_item(
    reminder: Reminder, user_tz: ZoneInfo, language: str | None = None
) -> ReminderItem:
    """Convert a Reminder ORM model to a UI item with localized time + date format."""
    trigger_local = _format_trigger_at_local(reminder.trigger_at, user_tz, language)
    return ReminderItem(
        content=reminder.content,
        trigger_at_local=trigger_local,
    )


def _format_trigger_at_local(
    trigger_at_utc: datetime, user_tz: ZoneInfo, language: str | None = None
) -> str:
    """Convert a UTC reminder trigger time to a friendly local string.

    Delegates to ``format_time_with_date_context`` (the canonical
    today/tomorrow/date helper in ``core.time_utils``) so the briefing card
    shares the same locale-aware pattern as the rest of the app and stays
    in sync with future i18n additions. The two flags fixed here encode the
    briefing-specific UX preferences:

    * ``time_first=True`` — time before the relative day / date prefix,
      validated UX choice (e.g. ``08:00 demain`` / ``08:00 24/04/2026``).
    * ``include_year=True`` — reminders can land months ahead, so the
      year disambiguates the date.

    Returns:
        - 'HH:MM' if today (date implicit)
        - 'HH:MM <tomorrow_word>' if tomorrow (locale-aware)
        - 'HH:MM <DD/MM/YYYY|MM/DD/YYYY|YYYY/MM/DD>' otherwise (locale-aware)
        - '?' on parsing error
    """
    try:
        if trigger_at_utc.tzinfo is None:
            trigger_at_utc = trigger_at_utc.replace(tzinfo=UTC)
        local_dt = trigger_at_utc.astimezone(user_tz)
        formatted = format_time_with_date_context(
            local_dt,
            reference_dt=datetime.now(user_tz),
            locale=language or "en",
            include_year=True,
            time_first=True,
        )
        # The canonical V3Messages.get_tomorrow registry returns a
        # capital-cased word (designed for sentence heads). Inside our
        # "HH:MM <word>" pattern, the word sits mid-string, so we lower
        # it for natural flow ("08:00 demain" / "08:00 tomorrow" rather
        # than "08:00 Demain" / "08:00 Tomorrow").
        # Note on German: this also yields "06:00 morgen" instead of the
        # noun-cased "Morgen" — acceptable in this UX context (timestamp
        # mid-line, not a sentence). Adjust here if a per-locale rule is
        # ever required.
        return formatted.lower()
    except (ValueError, TypeError, AttributeError):
        return "?"


# =============================================================================
# Birthday extraction (Google People API connections)
# =============================================================================


def upcoming_birthdays_from_connections(
    connections: list[dict[str, Any]],
    *,
    horizon_days: int,
    max_items: int,
    today: date | None = None,
) -> list[BirthdayItem]:
    """Extract upcoming birthdays from People API connections.

    Google People birthday format::

        {"birthdays": [{"date": {"month": 3, "day": 15, "year": 1990}, ...}]}

    The ``year`` is optional — many users record month + day only.

    Args:
        connections: ``connections`` array from ``GooglePeopleClient.list_connections``.
        horizon_days: Look-ahead window from today (e.g. 14).
        max_items: Cap on the returned list size.
        today: Override for testing; defaults to ``date.today()``.

    Returns:
        List of BirthdayItem sorted ascending by ``days_until``.
        Birthdays today have days_until=0.
    """
    today = today or date.today()
    horizon_end = today.toordinal() + horizon_days

    candidates: list[BirthdayItem] = []
    for connection in connections:
        name = _extract_primary_name(connection)
        if not name:
            continue
        for birthday in connection.get("birthdays", []) or []:
            date_field = birthday.get("date") or {}
            month = date_field.get("month")
            day = date_field.get("day")
            year = date_field.get("year")
            if not month or not day:
                continue
            try:
                next_occurrence = _next_birthday_occurrence(today, int(month), int(day))
            except ValueError:
                continue
            # _next_birthday_occurrence guarantees next_occurrence >= today, so days_until >= 0.
            if next_occurrence.toordinal() > horizon_end:
                continue
            days_until = next_occurrence.toordinal() - today.toordinal()
            age_at_next: int | None = None
            if year:
                date_iso = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                # Age at the upcoming birthday (the year of next_occurrence
                # naturally accounts for the rollover when the birthday this
                # year is already past).
                try:
                    age_at_next = next_occurrence.year - int(year)
                    if age_at_next < 0:
                        age_at_next = None
                except (ValueError, TypeError):
                    age_at_next = None
            else:
                date_iso = f"--{int(month):02d}-{int(day):02d}"
            candidates.append(
                BirthdayItem(
                    contact_name=name,
                    date_iso=date_iso,
                    days_until=days_until,
                    age_at_next=age_at_next,
                )
            )
            break  # one birthday per contact is enough

    candidates.sort(key=lambda item: (item.days_until, item.contact_name.lower()))
    return candidates[:max_items]


def _extract_primary_name(connection: dict[str, Any]) -> str | None:
    """Return the contact's display name from a People API connection.

    Prefers ``displayName`` from the primary names entry; falls back to the
    first names entry; returns None if no name is set.
    """
    names = connection.get("names") or []
    if not names:
        return None
    # Find the primary name (metadata.primary == True), else first.
    primary = next((n for n in names if (n.get("metadata") or {}).get("primary")), None)
    chosen = primary or names[0]
    display = (chosen.get("displayName") or "").strip()
    if display:
        return display
    given = (chosen.get("givenName") or "").strip()
    family = (chosen.get("familyName") or "").strip()
    combined = f"{given} {family}".strip()
    return combined or None


def _next_birthday_occurrence(today: date, month: int, day: int) -> date:
    """Return the next occurrence of (month, day) on or after today.

    Handles Feb 29 by rolling to Feb 28 in non-leap years.

    Raises:
        ValueError: If the (month, day) is invalid even after Feb 29 fallback.
    """

    def _safe_date(year: int, month: int, day: int) -> date:
        try:
            return date(year, month, day)
        except ValueError:
            # Feb 29 in a non-leap year → fall back to Feb 28
            if month == 2 and day == 29:
                return date(year, 2, 28)
            raise

    candidate = _safe_date(today.year, month, day)
    if candidate < today:
        candidate = _safe_date(today.year + 1, month, day)
    return candidate


# =============================================================================
# Health summary formatting
# =============================================================================


def daily_average_from_breakdown(
    breakdown: list[dict[str, Any]],
    *,
    window_days: int,
) -> tuple[float | None, int]:
    """Compute the per-day average from a daily breakdown list.

    The breakdown comes from ``HealthMetricsService.compute_kind_daily_breakdown``
    and is shaped as ``[{"date": "YYYY-MM-DD", "value": <num>}, ...]``. Only
    days that actually have data appear in the list — missing days are not
    averaged in (the UI shows "moy. 14 j (12 jours)" so the user knows the
    coverage).

    Args:
        breakdown: List of ``{"date", "value"}`` dicts for the rolling window.
        window_days: Length of the rolling window (informational).

    Returns:
        Tuple ``(average, days_with_data)``. ``(None, 0)`` if no data at all.
    """
    if not breakdown:
        return None, 0
    values = [
        float(entry.get("value", 0.0)) for entry in breakdown if entry.get("value") is not None
    ]
    if not values:
        return None, 0
    avg = sum(values) / len(values)
    return round(avg, 1), len(values)


def make_health_summary_item(
    *,
    kind: str,
    value_today: float | None,
    value_avg_window: float | None,
    unit: str,
    window_days: int,
    days_with_data: int,
) -> HealthSummaryItem:
    """Build a HealthSummaryItem with today's value + rolling-window average.

    Raises ValueError if `kind` is not one of the registered health kinds —
    callers are expected to iterate over the registered kinds only.
    """
    if kind not in ("steps", "heart_rate"):
        raise ValueError(f"Unsupported health kind: {kind}")
    return HealthSummaryItem(
        kind=kind,
        value_today=value_today,
        value_avg_window=value_avg_window,
        unit=unit,
        window_days=window_days,
        days_with_data=days_with_data,
    )


def extract_today_value_from_summary(
    summary: dict[str, Any],
    *,
    kind: str,
) -> float | None:
    """Extract today's headline value from ``HealthMetricsService.compute_kind_summary``.

    The summary dict contains kind-specific aggregates:
    - steps (SUM aggregation)        → ``summary["total"]``
    - heart_rate (AVG_MIN_MAX)       → ``summary["avg"]``
    - LAST_VALUE kinds (future)      → ``summary["last"]``

    Returns None when no samples were collected today (``samples_count == 0``)
    so the UI can hide the today line gracefully.
    """
    if not summary or summary.get("samples_count", 0) == 0:
        return None
    if kind == "steps":
        value = summary.get("total")
    elif kind == "heart_rate":
        value = summary.get("avg")
    else:
        value = summary.get("last")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
