"""
Heartbeat Context Aggregator.

Fetches context from multiple sources in parallel (asyncio.gather) for
the LLM decision phase. Each source is independently failable — a single
source failure does not block other sources.

Sources:
- Calendar: upcoming events (Google Calendar, Apple Calendar, or Microsoft — dynamic resolution)
- Tasks: pending/overdue tasks (Google Tasks or Microsoft To Do — dynamic resolution)
- Emails: today's unread inbox emails (Gmail, Apple Email, or Microsoft Outlook — dynamic resolution)
- Weather: current conditions + change detection (rain, temp, wind)
- Interests: trending user interest topics
- Memories: relevant entries from LangGraph Store
- Activity: last user interaction timestamp
- Recent heartbeats: anti-redundancy within heartbeat type
- Recent interest notifications: cross-type dedup
- Time: local time context (always available)
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    GMAIL_FORMAT_METADATA,
    HEARTBEAT_CONTEXT_CALENDAR_HOURS_DEFAULT,
    HEARTBEAT_CONTEXT_EMAILS_MAX_DEFAULT,
    HEARTBEAT_CONTEXT_MEMORY_LIMIT_DEFAULT,
    HEARTBEAT_CONTEXT_TASKS_DAYS_DEFAULT,
    HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH_DEFAULT,
    HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW_DEFAULT,
    HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD_DEFAULT,
    HEARTBEAT_WEATHER_WIND_THRESHOLD_DEFAULT,
    JOURNALS_ENABLED_DEFAULT,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.heartbeat.schemas import HeartbeatContext, WeatherChange
from src.domains.interests.models import InterestNotification, UserInterest

logger = structlog.get_logger(__name__)


def _format_event_time(dt_field: dict[str, Any] | None, user_tz: ZoneInfo) -> str:
    """Convert a calendar event start/end dict to a human-readable local time.

    Handles all three providers:
    - Google:    {"dateTime": "2026-03-15T14:00:00+01:00"}  (offset in string)
    - Microsoft: {"dateTime": "2026-03-15T10:00:00", "timeZone": "Europe/Paris"}
    - Apple:     {"dateTime": "2026-03-15T15:00:00"}  (CalDAV: may be naive)
    - All-day:   {"date": "2026-03-15"}

    Naive datetimes (no offset, no timeZone field) are assumed to be in the
    user's local timezone, which is the correct default for CalDAV servers that
    return local times without TZID.

    Returns a compact string in the user's timezone:
    - Today's events: '15:00'
    - Other days: '2026-03-16 09:00'
    - All-day: '2026-03-15 (all day)'
    - Missing data: '?'
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

        # Naive datetime: use explicit timeZone field (Microsoft) or user tz (CalDAV)
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
        # Include date when the event is not today
        if local_dt.date() != now_local.date():
            return local_dt.strftime("%Y-%m-%d %H:%M")
        return local_dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return str(raw)


def _extract_due_date(due_str: str | None) -> str:
    """Extract a human-readable date from an RFC 3339 task due string.

    Task due dates are conceptually dates, not datetimes (Google Tasks always
    uses midnight UTC). Extracting the date portion avoids misleading timezone
    conversions that could shift the date by one day.

    Examples:
        '2026-03-15T00:00:00.000Z' → '2026-03-15'
        '2026-03-15' → '2026-03-15'
        None → 'no date'
    """
    if not due_str:
        return "no date"
    # Extract YYYY-MM-DD from ISO/RFC 3339 string
    return due_str[:10] if len(due_str) >= 10 else due_str


def _format_utc_datetime(dt: datetime | None, user_tz: ZoneInfo) -> str:
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


def _resolve_user_tz(user: Any) -> ZoneInfo:
    """Resolve the user's timezone with safe fallback.

    Falls back to DEFAULT_USER_DISPLAY_TIMEZONE if the user's timezone
    attribute is missing, None, or invalid.
    """
    try:
        return ZoneInfo(user.timezone)
    except (KeyError, ValueError, AttributeError, TypeError):
        return ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)


class ContextAggregator:
    """Aggregates context from multiple sources for heartbeat LLM decision.

    Each source fetch is independent and failable. Sources are fetched
    in parallel via asyncio.gather(return_exceptions=True).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def aggregate(
        self,
        user_id: UUID,
        user: Any,
    ) -> HeartbeatContext:
        """Fetch all context sources in parallel and build HeartbeatContext.

        Args:
            user_id: User UUID.
            user: User ORM model (for timezone, home_location, etc.).

        Returns:
            HeartbeatContext with all available data.
        """
        settings = get_settings()
        context = HeartbeatContext()

        # Always compute time context (no I/O, cannot fail)
        self._compute_time_context(context, user)

        # Parallel fetch of all I/O-bound sources
        results = await asyncio.gather(
            self._fetch_calendar(user_id, user, settings),
            self._fetch_tasks(user_id, user, settings),
            self._fetch_emails(user_id, user, settings),
            self._fetch_weather_with_changes(user_id, user, settings),
            self._fetch_interests(user_id),
            self._fetch_memories(user_id, settings),
            self._fetch_activity(user_id),
            self._fetch_recent_heartbeats(user_id, user),
            self._fetch_recent_interest_notifications(user_id, user),
            return_exceptions=True,
        )

        # Unpack results with stable ordering (matches gather order)
        source_names = [
            "calendar",
            "tasks",
            "emails",
            "weather",
            "interests",
            "memories",
            "activity",
            "recent_heartbeats",
            "recent_interests",
        ]

        for name, result in zip(source_names, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "heartbeat_source_failed",
                    source=name,
                    error=str(result),
                    user_id=str(user_id),
                )
                context.failed_sources.append(name)
                continue

            if result is None:
                continue

            # Apply result to context based on source name
            self._apply_source_result(context, name, result)

        # Second pass: fetch journals with a dynamic query built from
        # the aggregated context (calendar summary, weather, interests).
        # This ensures journal entries are selected based on actual
        # notification context, not a static generic query.
        try:
            journal_query = self._build_journal_query_from_context(context)
            journal_result = await self._fetch_journals(user_id, user, query=journal_query)
            if journal_result:
                self._apply_source_result(context, "journals", journal_result)
        except Exception as e:
            logger.warning(
                "heartbeat_journals_second_pass_failed",
                user_id=str(user_id),
                error=str(e),
            )

        return context

    def _apply_source_result(
        self,
        context: HeartbeatContext,
        name: str,
        result: Any,
    ) -> None:
        """Apply a source result to the appropriate context fields."""
        if name == "calendar" and result:
            context.calendar_events = result
            context.available_sources.append("calendar")

        elif name == "tasks" and result:
            context.pending_tasks = result
            context.available_sources.append("tasks")

        elif name == "emails" and result:
            context.unread_emails = result
            context.available_sources.append("emails")

        elif name == "weather" and result:
            weather_current, weather_changes = result
            if weather_current:
                context.weather_current = weather_current
                context.available_sources.append("weather")
            if weather_changes:
                context.weather_changes = weather_changes

        elif name == "interests" and result:
            context.trending_interests = result
            context.available_sources.append("interests")

        elif name == "memories" and result:
            context.user_memories = result
            context.available_sources.append("memories")

        elif name == "activity" and result:
            last_at, hours_since = result
            context.last_interaction_at = last_at
            context.hours_since_last_interaction = hours_since

        elif name == "recent_heartbeats" and result:
            context.recent_heartbeats = result

        elif name == "recent_interests" and result:
            context.recent_interest_notifications = result

        elif name == "journals" and result:
            context.journal_entries = result
            context.available_sources.append("journals")

    # ------------------------------------------------------------------
    # Time context (synchronous, always succeeds)
    # ------------------------------------------------------------------

    def _compute_time_context(self, context: HeartbeatContext, user: Any) -> None:
        """Compute local time context for the user."""
        user_tz = _resolve_user_tz(user)

        now_local = datetime.now(user_tz)
        context.user_local_time = now_local
        context.day_of_week = now_local.strftime("%A")

        hour = now_local.hour
        if hour < 12:
            context.time_of_day = "morning"
        elif hour < 18:
            context.time_of_day = "afternoon"
        else:
            context.time_of_day = "evening"

    # ------------------------------------------------------------------
    # Calendar source
    # ------------------------------------------------------------------

    async def _fetch_calendar(
        self,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> list[dict[str, Any]] | None:
        """Fetch upcoming calendar events from the active provider (Google, Apple, or Microsoft).

        Uses dynamic provider resolution to support both Google Calendar and
        Apple Calendar. Resolves the user's preferred default calendar from
        connector preferences.

        Returns:
            List of event dicts or None if unavailable.
        """
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.preferences import ConnectorPreferencesService
        from src.domains.connectors.preferences.resolver import resolve_calendar_name
        from src.domains.connectors.provider_resolver import resolve_active_connector
        from src.domains.connectors.repository import ConnectorRepository

        connector_service = ConnectorService(self._db)

        # Dynamically resolve the active calendar provider (Google, Apple, or Microsoft)
        resolved_type = await resolve_active_connector(user_id, "calendar", connector_service)
        if resolved_type is None:
            return None

        # Get credentials based on provider type
        credentials: Any = None
        if resolved_type.is_apple:
            credentials = await connector_service.get_apple_credentials(user_id, resolved_type)
        else:
            credentials = await connector_service.get_connector_credentials(user_id, resolved_type)
        if not credentials:
            return None

        # Instantiate the appropriate client
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return None
        client = client_class(user_id, credentials, connector_service)

        # Resolve default calendar from user preferences
        calendar_id = "primary"
        try:
            repo = ConnectorRepository(self._db)
            connector = await repo.get_by_user_and_type(user_id, resolved_type)
            if connector and connector.preferences_encrypted:
                default_name = ConnectorPreferencesService.get_preference_value(
                    resolved_type.value,
                    connector.preferences_encrypted,
                    "default_calendar_name",
                )
                if default_name:
                    calendar_id = await resolve_calendar_name(
                        client=client,
                        name=default_name,
                        fallback="primary",
                    )
                    logger.debug(
                        "heartbeat_calendar_using_preference",
                        default_calendar_name=default_name,
                        resolved_calendar_id=calendar_id,
                        provider=resolved_type.value,
                        user_id=str(user_id),
                    )
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            logger.warning("heartbeat_calendar_preference_resolution_failed", error=str(e))

        hours = getattr(
            settings, "heartbeat_context_calendar_hours", HEARTBEAT_CONTEXT_CALENDAR_HOURS_DEFAULT
        )
        now = datetime.now(UTC)
        time_min = now.isoformat()
        time_max = (now + timedelta(hours=hours)).isoformat()

        result = await client.list_events(
            time_min=time_min,
            time_max=time_max,
            max_results=10,
            calendar_id=calendar_id,
            fields=["id", "summary", "start", "end", "location"],
        )

        events = result.get("items", [])
        if not events:
            return None

        # Resolve user timezone for display (same source as _compute_time_context)
        user_tz = _resolve_user_tz(user)

        # Extract minimal event data for the prompt, converting times to user timezone
        return [
            {
                "summary": e.get("summary", "Untitled"),
                "start": _format_event_time(e.get("start"), user_tz),
                "end": _format_event_time(e.get("end"), user_tz),
                "location": e.get("location"),
            }
            for e in events
        ]

    # ------------------------------------------------------------------
    # Tasks source (Google Tasks or Microsoft To Do)
    # ------------------------------------------------------------------

    async def _fetch_tasks(
        self,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> list[dict[str, Any]] | None:
        """Fetch pending and overdue tasks from the active provider.

        Uses dynamic provider resolution to support both Google Tasks and
        Microsoft To Do. Resolves the user's preferred default task list
        from connector preferences.

        Returns:
            List of task dicts or None if unavailable.
        """
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.preferences import ConnectorPreferencesService
        from src.domains.connectors.preferences.resolver import resolve_task_list_name
        from src.domains.connectors.provider_resolver import resolve_active_connector
        from src.domains.connectors.repository import ConnectorRepository

        connector_service = ConnectorService(self._db)

        # Dynamically resolve the active tasks provider (Google or Microsoft)
        resolved_type = await resolve_active_connector(user_id, "tasks", connector_service)
        if resolved_type is None:
            return None

        # Get credentials
        credentials = await connector_service.get_connector_credentials(user_id, resolved_type)
        if not credentials:
            return None

        # Instantiate the appropriate client
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return None
        client = client_class(user_id, credentials, connector_service)

        # Resolve default task list from user preferences
        task_list_id = "@default"
        try:
            repo = ConnectorRepository(self._db)
            connector = await repo.get_by_user_and_type(user_id, resolved_type)
            if connector and connector.preferences_encrypted:
                default_name = ConnectorPreferencesService.get_preference_value(
                    resolved_type.value,
                    connector.preferences_encrypted,
                    "default_task_list_name",
                )
                if default_name:
                    task_list_id = await resolve_task_list_name(
                        client=client,
                        name=default_name,
                        fallback="@default",
                    )
                    logger.debug(
                        "heartbeat_tasks_using_preference",
                        default_task_list_name=default_name,
                        resolved_task_list_id=task_list_id,
                        provider=resolved_type.value,
                        user_id=str(user_id),
                    )
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            logger.warning("heartbeat_tasks_preference_resolution_failed", error=str(e))

        days = getattr(
            settings, "heartbeat_context_tasks_days", HEARTBEAT_CONTEXT_TASKS_DAYS_DEFAULT
        )
        now = datetime.now(UTC)
        # RFC 3339 timestamp for due_max filter.
        due_max = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

        result = await client.list_tasks(
            task_list_id=task_list_id,
            max_results=10,
            show_completed=False,
            due_max=due_max,
        )

        tasks = result.get("items", [])
        if not tasks:
            return None

        # Extract minimal task data for the prompt, flag overdue tasks.
        # Both Google Tasks and Microsoft To Do normalizers return "due" as
        # RFC 3339 and "status" as "needsAction"/"completed" (normalized).
        # Due dates are conceptually dates (not datetimes) — extract date only.
        return [
            {
                "title": t.get("title", "Untitled"),
                "due": _extract_due_date(t.get("due")),
                "overdue": self._is_task_overdue(t, now),
            }
            for t in tasks
            if t.get("status") == "needsAction"
        ]

    @staticmethod
    def _is_task_overdue(task: dict[str, Any], now: datetime) -> bool:
        """Check if a task is overdue by parsing the RFC 3339 due date.

        Args:
            task: Task dict (normalized format from any provider).
            now: Current UTC datetime for comparison.

        Returns:
            True if the task is overdue (due date in the past and not completed).
        """
        due_str = task.get("due")
        if not due_str or task.get("status") != "needsAction":
            return False
        try:
            # Google Tasks returns "2026-03-03T00:00:00.000Z" (RFC 3339).
            # datetime.fromisoformat handles both "Z" (Python 3.11+) and "+00:00".
            due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
            return due_dt < now
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Weather source + change detection
    # ------------------------------------------------------------------

    async def _fetch_weather_with_changes(
        self,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> tuple[dict[str, Any] | None, list[WeatherChange] | None] | None:
        """Fetch current weather and detect upcoming transitions.

        Returns:
            Tuple of (current_weather, changes) or None if unavailable.
        """
        # Check OpenWeatherMap connector
        connector_service = ConnectorService(self._db)
        credentials = await connector_service.get_api_key_credentials(
            user_id, ConnectorType.OPENWEATHERMAP
        )
        if not credentials:
            return None

        # Decrypt home location
        if not user.home_location_encrypted:
            return None

        from src.core.security.utils import decrypt_data

        try:
            location_json = decrypt_data(user.home_location_encrypted)
            location = json.loads(location_json)
            lat = location.get("lat")
            lon = location.get("lon")
            if lat is None or lon is None:
                return None
        except (ValueError, json.JSONDecodeError, KeyError):
            logger.debug(
                "heartbeat_weather_location_decrypt_failed",
                user_id=str(user_id),
            )
            return None

        from src.domains.connectors.clients.openweathermap_client import (
            OpenWeatherMapClient,
        )

        client = OpenWeatherMapClient(api_key=credentials.api_key, user_id=user_id)

        # Fetch current + forecast in parallel
        results = await asyncio.gather(
            client.get_current_weather(lat=lat, lon=lon, units="metric"),
            client.get_forecast(lat=lat, lon=lon, units="metric", cnt=8),
            return_exceptions=True,
        )
        current_result: dict[str, Any] | BaseException = results[0]
        forecast_result: dict[str, Any] | BaseException = results[1]

        current = None
        if not isinstance(current_result, BaseException):
            current = current_result

        changes = None
        if not isinstance(forecast_result, BaseException) and current:
            user_tz = _resolve_user_tz(user)

            hourly = forecast_result.get("list", [])
            changes = self._detect_weather_changes(current, hourly, user_tz, settings)

        return current, changes

    def _detect_weather_changes(
        self,
        current: dict[str, Any],
        hourly: list[dict[str, Any]],
        user_tz: ZoneInfo,
        settings: Any,
    ) -> list[WeatherChange]:
        """Detect notable weather transitions between now and forecast.

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
        current_temp = current.get("main", {}).get("temp", 0)

        rain_high = getattr(
            settings,
            "heartbeat_weather_rain_threshold_high",
            HEARTBEAT_WEATHER_RAIN_THRESHOLD_HIGH_DEFAULT,
        )
        rain_low = getattr(
            settings,
            "heartbeat_weather_rain_threshold_low",
            HEARTBEAT_WEATHER_RAIN_THRESHOLD_LOW_DEFAULT,
        )
        temp_threshold = getattr(
            settings,
            "heartbeat_weather_temp_change_threshold",
            HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD_DEFAULT,
        )
        wind_threshold = getattr(
            settings, "heartbeat_weather_wind_threshold", HEARTBEAT_WEATHER_WIND_THRESHOLD_DEFAULT
        )

        # Track detected types to avoid duplicate detections
        detected_types: set[str] = set()

        for entry in hourly:
            entry_pop = entry.get("pop", 0)
            entry_temp = entry.get("main", {}).get("temp", current_temp)
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

            # Temperature drop
            temp_diff = current_temp - entry_temp
            if temp_diff > temp_threshold and "temp_drop" not in detected_types:
                severity = "warning" if temp_diff > temp_threshold * 1.6 else "info"
                changes.append(
                    WeatherChange(
                        change_type="temp_drop",
                        expected_at=entry_time,
                        description=(f"Temperature dropping {temp_diff:.0f}°C by {time_str}"),
                        severity=severity,
                    )
                )
                detected_types.add("temp_drop")

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
    # Emails source (unread inbox)
    # ------------------------------------------------------------------

    async def _fetch_emails(
        self,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> list[dict[str, str]] | None:
        """Fetch today's unread inbox emails from the active provider.

        Uses dynamic provider resolution to support Google Gmail,
        Apple Email, and Microsoft Outlook. Only returns emails received
        today (user's local date). Returns minimal metadata (from,
        subject, date, snippet) for the LLM decision prompt.

        All three providers return normalized messages with top-level
        from/subject/snippet/internalDate fields. Apple's search_emails
        returns only IDs (full messages cached in Redis), so get_message()
        is called for those — a Redis cache hit, no extra round-trip.

        Returns:
            List of email summary dicts or None if unavailable.
        """
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.provider_resolver import resolve_active_connector

        connector_service = ConnectorService(self._db)

        # Dynamically resolve the active email provider
        resolved_type = await resolve_active_connector(user_id, "email", connector_service)
        if resolved_type is None:
            return None

        # Get credentials based on provider type
        credentials: Any = None
        if resolved_type.is_apple:
            credentials = await connector_service.get_apple_credentials(user_id, resolved_type)
        else:
            credentials = await connector_service.get_connector_credentials(user_id, resolved_type)
        if not credentials:
            return None

        # Instantiate the appropriate client
        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            return None
        client = client_class(user_id, credentials, connector_service)

        max_emails = getattr(
            settings, "heartbeat_context_emails_max", HEARTBEAT_CONTEXT_EMAILS_MAX_DEFAULT
        )

        # Filter to today's unread emails only (user's local date).
        # Gmail-style `after:` uses the date as a lower bound (inclusive).
        user_tz = _resolve_user_tz(user)
        today_str = datetime.now(user_tz).strftime("%Y/%m/%d")

        # All providers accept Gmail-style query syntax (normalized internally)
        result = await client.search_emails(
            query=f"is:unread after:{today_str}",
            max_results=max_emails,
            use_cache=True,
        )

        messages = result.get("messages", [])
        if not messages:
            return None

        # For providers that return only IDs (Apple), fetch full messages.
        # Apple's search_emails caches full messages in Redis, so get_message
        # is a cache hit — no extra IMAP round-trips.
        full_messages = []
        for msg in messages:
            if set(msg.keys()) <= {"id", "threadId"}:
                try:
                    full_msg = await client.get_message(
                        msg["id"], format=GMAIL_FORMAT_METADATA, use_cache=True
                    )
                    if full_msg:
                        full_messages.append(full_msg)
                except Exception:
                    logger.debug(
                        "heartbeat_email_fetch_message_failed",
                        message_id=msg.get("id"),
                        user_id=str(user_id),
                    )
            else:
                full_messages.append(msg)

        if not full_messages:
            return None

        # Extract minimal email data for the prompt.
        # All providers now return top-level from/subject/snippet/internalDate:
        # - Google: normalized in GoogleGmailClient._normalize_message_fields()
        # - Apple: normalized in normalize_imap_message()
        # - Microsoft: normalized in normalize_graph_message()
        emails = []
        for msg in full_messages:
            emails.append(
                {
                    "from": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "date": self._format_email_date(msg.get("internalDate"), user_tz),
                    "snippet": msg.get("snippet", ""),
                }
            )

        return emails if emails else None

    @staticmethod
    def _format_email_date(
        internal_date: str | int | None,
        user_tz: ZoneInfo,
    ) -> str:
        """Convert email internalDate (epoch ms) to a user-local time string.

        Args:
            internal_date: Epoch milliseconds as string or int, or None.
            user_tz: User's timezone for display.

        Returns:
            Formatted string like '2026-03-15 15:30' or '?' if unavailable.
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

    # ------------------------------------------------------------------
    # Interests source
    # ------------------------------------------------------------------

    async def _fetch_interests(
        self,
        user_id: UUID,
    ) -> list[dict[str, str]] | None:
        """Fetch trending user interest topics.

        Returns:
            List of {topic} dicts or None if unavailable.
        """
        from src.domains.interests.repository import InterestRepository

        repo = InterestRepository(self._db)
        interests = await repo.get_top_weighted_interests(
            user_id=user_id,
            top_percent=0.3,
            exclude_in_cooldown=False,
        )

        if not interests:
            return None

        return [{"topic": interest.topic} for interest, _weight in interests]

    # ------------------------------------------------------------------
    # Memories source
    # ------------------------------------------------------------------

    async def _fetch_memories(
        self,
        user_id: UUID,
        settings: Any,
    ) -> list[str] | None:
        """Fetch relevant user memories from LangGraph Store.

        Returns:
            List of memory content strings or None if unavailable.
        """
        from src.domains.agents.context.store import get_tool_context_store

        limit = getattr(
            settings, "heartbeat_context_memory_limit", HEARTBEAT_CONTEXT_MEMORY_LIMIT_DEFAULT
        )

        store = await get_tool_context_store()
        results = await store.asearch(
            (str(user_id), "memories"),
            query="important upcoming events preferences routines",
            limit=limit,
        )

        if not results:
            return None

        memories = []
        for item in results:
            value = item.value if hasattr(item, "value") else item
            if isinstance(value, dict):
                content = value.get("content", str(value))
            else:
                content = str(value)
            if content:
                memories.append(content[:200])  # Truncate to save tokens

        return memories if memories else None

    # ------------------------------------------------------------------
    # Activity source
    # ------------------------------------------------------------------

    async def _fetch_activity(
        self,
        user_id: UUID,
    ) -> tuple[datetime, float] | None:
        """Get last user interaction time.

        Returns:
            Tuple of (last_interaction_at, hours_since) or None.
        """
        # Query last user message via Conversation JOIN
        result = await self._db.execute(
            select(ConversationMessage.created_at)
            .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user_id,
                ConversationMessage.role == "user",
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        last_at = result.scalar_one_or_none()

        if not last_at:
            return None

        now = datetime.now(UTC)
        hours_since = (now - last_at).total_seconds() / 3600
        return last_at, hours_since

    # ------------------------------------------------------------------
    # Recent heartbeats (anti-redundancy)
    # ------------------------------------------------------------------

    async def _fetch_recent_heartbeats(
        self,
        user_id: UUID,
        user: Any,
    ) -> list[dict[str, str]] | None:
        """Fetch recent heartbeat notifications for anti-redundancy.

        Returns:
            List of {sources_used, decision_reason, created_at} dicts
            with created_at converted to the user's local timezone.
        """
        repo = HeartbeatNotificationRepository(self._db)
        notifications = await repo.get_recent_by_user(user_id, limit=5)

        if not notifications:
            return None

        user_tz = _resolve_user_tz(user)
        return [
            {
                "sources_used": n.sources_used,
                "decision_reason": n.decision_reason or "N/A",
                "created_at": _format_utc_datetime(n.created_at, user_tz),
            }
            for n in notifications
        ]

    # ------------------------------------------------------------------
    # Recent interest notifications (cross-type dedup)
    # ------------------------------------------------------------------

    async def _fetch_recent_interest_notifications(
        self,
        user_id: UUID,
        user: Any,
    ) -> list[dict[str, str]] | None:
        """Fetch recent interest notifications for cross-type dedup.

        Direct SQL JOIN query since InterestNotificationRepository lacks
        a suitable method combining topic name + created_at.

        Returns:
            List of {topic, created_at} dicts with created_at converted
            to the user's local timezone.
        """
        result = await self._db.execute(
            select(
                InterestNotification.created_at,
                UserInterest.topic,
            )
            .join(
                UserInterest,
                InterestNotification.interest_id == UserInterest.id,
            )
            .where(InterestNotification.user_id == user_id)
            .order_by(InterestNotification.created_at.desc())
            .limit(5)
        )
        rows = result.all()

        if not rows:
            return None

        user_tz = _resolve_user_tz(user)
        return [
            {
                "topic": row.topic,
                "created_at": _format_utc_datetime(row.created_at, user_tz),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Journals (Personal Journals — semantic relevance search)
    # ------------------------------------------------------------------

    def _build_journal_query_from_context(self, context: HeartbeatContext) -> str:
        """Build a semantic search query from aggregated heartbeat context.

        Combines summaries of available context sources into a query
        that will find the most relevant journal entries for this
        specific notification cycle.

        Args:
            context: Aggregated heartbeat context (calendar, weather, etc.)

        Returns:
            Query string for embedding-based semantic search
        """
        parts: list[str] = []

        if context.calendar_events:
            summaries = [e.get("summary", "") for e in context.calendar_events[:3]]
            parts.append(f"upcoming events: {', '.join(summaries)}")

        if context.weather_current:
            desc = context.weather_current.get("description", "")
            parts.append(f"weather: {desc}")

        if context.trending_interests:
            topics = [i.get("topic", "") for i in context.trending_interests[:3]]
            parts.append(f"interests: {', '.join(topics)}")

        if context.pending_tasks:
            tasks = [t.get("title", "") for t in context.pending_tasks[:3]]
            parts.append(f"tasks: {', '.join(tasks)}")

        if context.unread_emails:
            subjects = [e.get("subject", "") for e in context.unread_emails[:2]]
            parts.append(f"emails: {', '.join(subjects)}")

        # Fallback if no context available
        if not parts:
            return "user preferences observations patterns priorities"

        return " ".join(parts)

    async def _fetch_journals(
        self,
        user_id: UUID,
        user: Any,
        query: str = "",
    ) -> list[dict[str, str]] | None:
        """Fetch relevant journal entries for heartbeat context enrichment.

        Uses semantic search with a dynamic query built from the
        aggregated heartbeat context to find journal entries that
        are specifically relevant to the current notification cycle.
        Skipped if journals are disabled for the user.

        Args:
            user_id: User UUID
            user: User model instance
            query: Semantic search query (built from aggregated context)

        Returns:
            List of journal entry dicts, or None if disabled/empty
        """
        # Skip if journals disabled
        if not getattr(user, "journals_enabled", JOURNALS_ENABLED_DEFAULT):
            return None

        try:
            from src.domains.journals.repository import JournalEntryRepository
            from src.infrastructure.llm.local_embeddings import get_local_embeddings

            repo = JournalEntryRepository(self._db)

            embeddings = get_local_embeddings()
            search_query = query or "user preferences observations patterns priorities"
            query_embedding = embeddings.embed_query(search_query)

            if not query_embedding:
                return None

            from src.core.config import settings as app_settings

            scored_entries = await repo.search_by_relevance(
                user_id=user_id,
                query_embedding=query_embedding,
                limit=3,  # Keep small for heartbeat budget
                min_score=app_settings.journal_context_min_score,
            )

            if not scored_entries:
                return None

            return [
                {
                    "title": entry.title,
                    "content_preview": entry.content[:200],
                    "theme": entry.theme,
                    "mood": entry.mood,
                    "date": entry.created_at.strftime("%Y-%m-%d"),
                    "score": f"{score:.2f}",
                }
                for entry, score in scored_entries
            ]

        except Exception as e:
            logger.warning(
                "heartbeat_journals_fetch_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return None
