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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import (
    GMAIL_FORMAT_METADATA,
    HEARTBEAT_CONTENT_EXCERPT_CHARS,
)
from src.domains.connectors.service import ConnectorService
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.heartbeat.context_sources import (
    detect_weather_changes,
    fetch_birthdays_context,
    fetch_departure_advice,
    fetch_open_loops_context,
    fetch_recent_other_notifications,
)
from src.domains.heartbeat.context_sources import (
    format_utc_datetime as _format_utc_datetime,
)
from src.domains.heartbeat.context_sources import (
    resolve_user_tz as _resolve_user_tz,
)
from src.domains.heartbeat.habit_context import fetch_habits_context
from src.domains.heartbeat.health_context import fetch_health_signals
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.heartbeat.schemas import HeartbeatContext, WeatherChange
from src.domains.heartbeat.source_policy import is_source_enabled
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.push_channels.wake import WakePayload
from src.infrastructure.database.session import get_db_context

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
                except KeyError, ValueError:
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
    except ValueError, TypeError:
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


class ContextAggregator:
    """Aggregates context from multiple sources for heartbeat LLM decision.

    Each source fetch is independent and failable. Sources are fetched
    in parallel via asyncio.gather(return_exceptions=True).

    CRITICAL — DB SESSIONS: SQLAlchemy AsyncSession does NOT allow concurrent
    operations on a single session. Every fetcher gathered in ``aggregate()``
    therefore runs with its OWN session (``_with_fresh_session`` /
    ``get_db_context()``, same pattern as ``briefing/fetchers.py``); sharing
    ``self._db`` across the gather lost sources non-deterministically
    (audit N-209). ``self._db`` remains ONLY for the sequential second pass
    (``_fetch_journals``) that runs after the gather completes;
    ``_fetch_memories`` also runs in that second pass but manages its own
    scoped session internally.
    """

    def __init__(self, db: AsyncSession, wake: WakePayload | None = None) -> None:
        self._db = db
        self._wake = wake  # ADR-261: what the push sweep already fetched

    async def _with_fresh_session(
        self,
        fetch: Callable[..., Awaitable[Any]],
        *args: Any,
    ) -> Any:
        """Run one gathered fetcher with a dedicated DB session.

        Args:
            fetch: Fetcher coroutine function taking the session first.
            *args: Remaining fetcher arguments.

        Returns:
            Whatever the fetcher returns.
        """
        async with get_db_context() as db:
            return await fetch(db, *args)

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

        # Parallel fetch of all I/O-bound sources — one DB session PER fetcher
        # (see class docstring); fetch_health_signals manages its own scoped
        # session internally. Memories are NOT fetched here: like journals,
        # they run in the second pass with a dynamic query (P8, ADR-135
        # symmetry — the historical static query anchored the same memories
        # cycle after cycle).
        #
        # Refused sources are skipped BEFORE their coroutine is built: a
        # coroutine created and never awaited leaks and warns, and skipping at
        # fetch time is also what makes a silenced source stop costing an API
        # call. The names NOT in the registry (activity, the anti-redundancy
        # windows) are never gated — they say what was already sent.
        # `scoped=True` means the fetcher expects a DB session as its first
        # argument (`_with_fresh_session` provides one); the other two manage
        # their own session internally.
        common = (user_id, user, settings)
        specs: tuple[tuple[str, Any, tuple[Any, ...], bool], ...] = (
            ("calendar", self._fetch_calendar, common, True),
            ("tasks", self._fetch_tasks, common, True),
            ("emails", self._fetch_emails, common, True),
            ("weather", self._fetch_weather_with_changes, common, True),
            ("interests", self._fetch_interests, (user_id,), True),
            ("activity", self._fetch_activity, (user_id,), True),
            ("recent_heartbeats", self._fetch_recent_heartbeats, (user_id, user), True),
            ("recent_interests", self._fetch_recent_interest_notifications, (user_id, user), True),
            ("recent_other", self._fetch_recent_other_notifications, (user_id, user), True),
            ("health_signals", fetch_health_signals, common, False),
            ("birthdays", self._fetch_birthdays, common, False),
            ("open_loops", fetch_open_loops_context, common, True),
            ("habits", fetch_habits_context, (user_id, user, settings), True),
        )
        planned = [
            (name, self._with_fresh_session(fetch, *args) if scoped else fetch(*args))
            for name, fetch, args, scoped in specs
            if is_source_enabled(user, name)
        ]
        results = await asyncio.gather(*(coro for _, coro in planned), return_exceptions=True)

        for (name, _), result in zip(planned, results, strict=True):
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

        # Second pass: fetch journals AND memories with a dynamic query built
        # from the aggregated context (calendar summary, weather, interests).
        # This ensures both are selected based on the actual notification
        # context, not a static generic query. Sequential on purpose — two
        # indexed queries, each on its own session (CLAUDE.md concurrency
        # guidance: a plain sequential pass is fine and simpler here).
        await self._second_pass(context, user_id, user, settings)

        return context

    async def _second_pass(
        self,
        context: HeartbeatContext,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> None:
        """Sources selected from the aggregated context, not from a static query.

        Journals and memories are searched with a query built from what the
        first pass found (P8, ADR-135); departure advice consumes the calendar
        events it fetched. Extracted from ``aggregate`` so the per-source
        gating (ADR-197) does not push it over the complexity ratchet — the
        three blocks are unchanged.
        """
        second_pass_query = self._build_second_pass_query(context)

        if is_source_enabled(user, "journals"):
            try:
                journal_result = await self._fetch_journals(user_id, user, query=second_pass_query)
                if journal_result:
                    self._apply_source_result(context, "journals", journal_result)
            except Exception as e:
                logger.warning(
                    "heartbeat_journals_second_pass_failed",
                    user_id=str(user_id),
                    error=str(e),
                )

        # Departure advice (P6): consumes the calendar events fetched above.
        # Refusing `calendar` therefore leaves nothing to advise on — the
        # switch stays independent because a user may well want the agenda in
        # the decision without traffic-driven nudges about it.
        if is_source_enabled(user, "departure"):
            try:
                departure = await fetch_departure_advice(
                    user_id, user, settings, context.calendar_events
                )
                if departure:
                    context.departure_advice = departure
                    context.available_sources.append("departure")
            except Exception as e:
                logger.warning(
                    "heartbeat_departure_second_pass_failed",
                    user_id=str(user_id),
                    error=str(e),
                )

        if is_source_enabled(user, "memories"):
            try:
                memories_result = await self._fetch_memories(
                    user_id, settings, query=second_pass_query
                )
                if memories_result:
                    self._apply_source_result(context, "memories", memories_result)
            except Exception as e:
                logger.warning(
                    "heartbeat_memories_second_pass_failed",
                    user_id=str(user_id),
                    error=str(e),
                )
                context.failed_sources.append("memories")

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
            weather_current, weather_changes, location_source, city_name = result
            if weather_current:
                context.weather_current = weather_current
                context.available_sources.append("weather")
            if weather_changes:
                context.weather_changes = weather_changes
            if location_source is not None:
                context.weather_location_source = location_source
            if city_name is not None:
                context.weather_location_city = city_name

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

        elif name == "recent_other" and result:
            context.recent_other_notifications = result

        elif name == "journals" and result:
            context.journal_entries = result
            context.available_sources.append("journals")

        elif name == "health_signals" and result:
            context.health_signals = result
            context.available_sources.append("health_signals")

        elif name == "birthdays" and result:
            context.upcoming_birthdays = result
            context.available_sources.append("birthdays")

        elif name == "open_loops" and result:
            context.open_loops = result
            context.available_sources.append("open_loops")

        elif name == "habits" and result:
            context.habits = result
            context.available_sources.append("habits")

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
        db: AsyncSession,
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
        from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
        from src.domains.connectors.provider_resolver import resolve_active_connector

        connector_service = ConnectorService(db)

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
        try:

            # The user's preferred default calendar, through the shared
            # owner-default resolver (falls back to "primary").
            calendar_id = await resolve_owner_calendar_id(
                db=db, client=client, owner_id=user_id, connector_type=resolved_type
            )

            hours = settings.heartbeat_context_calendar_hours
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

            from src.domains.heartbeat.wake_context import merge_wake_events

            events = merge_wake_events(self._wake, list(result.get("items", [])))
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
                    # Raw provider start dict (P6): the departure second pass
                    # needs the real datetime; the prompt renderer ignores it.
                    "start_raw": e.get("start"),
                }
                for e in events
            ]
        finally:
            # Deterministic transport close every cycle (C8 leak class;
            # same doctrine as briefing/fetchers and person_tools).
            await client.close()

    # ------------------------------------------------------------------
    # Tasks source (Google Tasks or Microsoft To Do)
    # ------------------------------------------------------------------

    async def _fetch_tasks(
        self,
        db: AsyncSession,
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
        from src.domains.connectors.preferences.owner_defaults import resolve_owner_task_list_id
        from src.domains.connectors.provider_resolver import resolve_active_connector

        connector_service = ConnectorService(db)

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
        try:

            # Same shared resolver for the user's preferred task list.
            task_list_id = await resolve_owner_task_list_id(
                db=db, client=client, owner_id=user_id, connector_type=resolved_type
            )

            days = settings.heartbeat_context_tasks_days
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
        finally:
            # Deterministic transport close every cycle (C8 leak class;
            # same doctrine as briefing/fetchers and person_tools).
            await client.close()

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
        except ValueError, TypeError:
            return False

    # ------------------------------------------------------------------
    # Weather source + change detection
    # ------------------------------------------------------------------

    async def _fetch_weather_with_changes(
        self,
        db: AsyncSession,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> tuple[dict[str, Any] | None, list[WeatherChange] | None, str | None, str | None] | None:
        """Fetch current weather and detect upcoming transitions.

        Resolves the effective location via the Phase 3 cascade
        (last-known if opted-in, fresh, and far from home — otherwise home),
        reverse-geocodes it to a city name, and emits the appropriate
        observability metric.

        Returns:
            Tuple of ``(current_weather, changes, location_source, city_name)``
            or ``None`` if unavailable.
        """
        # Resolve the active weather provider (lot E, 2026-08): Google
        # Weather (platform key) or OpenWeatherMap (personal key) — both
        # OWM-shaped, so everything below is provider-agnostic.
        from src.domains.connectors.weather_provider import resolve_weather_client

        connector_service = ConnectorService(db)
        client = await resolve_weather_client(user_id, connector_service)
        if client is None:
            return None

        # Resolve effective location via the Phase 3 cascade
        from src.domains.users.user_location_service import (
            NoLocationAvailableError,
            UserLocationService,
        )
        from src.infrastructure.observability.metrics_heartbeat import (
            heartbeat_weather_location_source_total,
        )

        try:
            effective = await UserLocationService(db).get_effective_location_for_proactive(user)
        except NoLocationAvailableError:
            return None

        lat = effective.lat
        lon = effective.lon
        source = effective.source
        heartbeat_weather_location_source_total.labels(source=source).inc()

        # Fetch current + forecast + city (reverse geocode) in parallel
        from src.domains.heartbeat.geocoding import resolve_city_name

        try:
            results = await asyncio.gather(
                client.get_current_weather(lat=lat, lon=lon, units="metric"),
                client.get_forecast(lat=lat, lon=lon, units="metric", cnt=16),
                resolve_city_name(lat=lat, lon=lon, client=client),
                return_exceptions=True,
            )
        finally:
            # Deterministic close of the pooled httpx client (leak fix) —
            # same pattern as briefing/fetchers.py.
            await client.close()
        current_result: dict[str, Any] | BaseException = results[0]
        forecast_result: dict[str, Any] | BaseException = results[1]
        city_result: str | None | BaseException = results[2]

        current = None
        if not isinstance(current_result, BaseException):
            current = current_result

        changes = None
        if not isinstance(forecast_result, BaseException) and current:
            user_tz = _resolve_user_tz(user)

            hourly = forecast_result.get("list", [])
            changes = self._detect_weather_changes(current, hourly, user_tz, settings)

        city: str | None = None
        if isinstance(city_result, str):
            city = city_result

        return current, changes, source, city

    def _detect_weather_changes(
        self,
        current: dict[str, Any],
        hourly: list[dict[str, Any]],
        user_tz: ZoneInfo,
        settings: Any,
    ) -> list[WeatherChange]:
        """Delegate to the extracted pure rules (see ``context_sources``)."""
        return detect_weather_changes(current, hourly, user_tz, settings)

    # ------------------------------------------------------------------
    # Emails source (unread inbox)
    # ------------------------------------------------------------------

    async def _fetch_emails(
        self,
        db: AsyncSession,
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

        connector_service = ConnectorService(db)

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
        try:

            max_emails = settings.heartbeat_context_emails_max

            # Delta fast-path (lot G, 2026-08): Gmail's history.list gives the
            # EXACT new INBOX mail since the last tick (anchored in Redis).
            # None => legacy query path (first run, other provider, expired
            # anchor, Redis down) — always fail-open. Id-only entries: the
            # fetch loop below resolves full messages.
            from src.domains.heartbeat.wake_context import wake_or_delta_messages

            user_tz = _resolve_user_tz(user)
            # ADR-261: a push wake carries the delta the sweep already read.
            messages = await wake_or_delta_messages(self._wake, client, user_id, max_emails)
            if messages is None:
                # Filter to today's unread emails only (user's local date).
                # Gmail-style `after:` uses the date as a lower bound (inclusive).
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
        finally:
            # Deterministic transport close every cycle (C8 leak class;
            # same doctrine as briefing/fetchers and person_tools).
            await client.close()

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
        except ValueError, TypeError, OSError:
            return "?"

    # ------------------------------------------------------------------
    # Interests source
    # ------------------------------------------------------------------

    async def _fetch_interests(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> list[dict[str, str]] | None:
        """Fetch a subject-diverse sample of user interest topics (ADR-135).

        Replaces the historical top-30%-by-weight fetch whose fixed composition
        anchored the decision LLM on the same topics (A24 near-daily in prod).
        Logic lives in `interest_context.fetch_varied_interest_topics`.

        Returns:
            List of {topic} dicts or None if unavailable.
        """
        from src.domains.heartbeat.interest_context import fetch_varied_interest_topics

        return await fetch_varied_interest_topics(db, user_id)

    # ------------------------------------------------------------------
    # Memories source
    # ------------------------------------------------------------------

    async def _fetch_memories(
        self,
        user_id: UUID,
        settings: Any,
        query: str = "",
    ) -> list[str] | None:
        """Fetch relevant user memories from LangGraph Store.

        Second-pass source (P8): the caller passes the dynamic query built
        from the aggregated context so memory selection follows the actual
        notification cycle instead of a fixed anchor. Falls back to the
        historical static query when the aggregated context is empty.

        Args:
            user_id: User UUID.
            settings: App settings (memory limit).
            query: Dynamic semantic search query ("" → static fallback).

        Returns:
            List of memory content strings or None if unavailable.
        """
        limit = settings.heartbeat_context_memory_limit

        # Use centralized embedding cache (text-hash keyed → computed once, then cached)
        from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding

        search_query = query or "important upcoming events preferences routines"
        # An internal retrieval query, not something the user typed.
        query_embedding = await get_or_compute_embedding(
            message=search_query,
            is_conversational=False,
        )

        if not query_embedding:
            return None

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            results = await repo.search_by_relevance(
                user_id=user_id,
                query_embedding=query_embedding,
                limit=limit,
                min_score=0.3,
            )

        if not results:
            return None

        memories = []
        for memory, _score in results:
            content = memory.content or ""
            if content:
                memories.append(content[:200])  # Truncate to save tokens

        return memories if memories else None

    # ------------------------------------------------------------------
    # Activity source
    # ------------------------------------------------------------------

    async def _fetch_activity(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> tuple[datetime, float] | None:
        """Get last user interaction time.

        Returns:
            Tuple of (last_interaction_at, hours_since) or None.
        """
        # Query last user message via Conversation JOIN
        result = await db.execute(
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
        db: AsyncSession,
        user_id: UUID,
        user: Any,
    ) -> list[dict[str, str]] | None:
        """Fetch recent heartbeat notifications for anti-redundancy.

        The window carries CONTENT excerpts (ADR-135): a source-only summary
        let the decision LLM repeat a topic it had already used through a
        different source (memories, journals), which is exactly how the same
        motifs resurfaced day after day.

        Returns:
            List of {sources_used, decision_reason, created_at, content} dicts
            with created_at converted to the user's local timezone.
        """
        settings = get_settings()
        repo = HeartbeatNotificationRepository(db)
        notifications = await repo.get_recent_by_user(
            user_id,
            limit=settings.heartbeat_recent_window_count,
            max_age_days=settings.heartbeat_recent_window_days,
        )

        if not notifications:
            return None

        user_tz = _resolve_user_tz(user)
        return [
            {
                "sources_used": n.sources_used,
                "decision_reason": n.decision_reason or "N/A",
                "created_at": _format_utc_datetime(n.created_at, user_tz),
                "content": (n.content or "")[:HEARTBEAT_CONTENT_EXCERPT_CHARS],
            }
            for n in notifications
        ]

    # ------------------------------------------------------------------
    # Recent interest notifications (cross-type dedup)
    # ------------------------------------------------------------------

    async def _fetch_recent_interest_notifications(
        self,
        db: AsyncSession,
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
        result = await db.execute(
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
    # Birthdays (P7) + other proactive surfaces (P10) — extracted sources
    # ------------------------------------------------------------------

    async def _fetch_birthdays(
        self,
        user_id: UUID,
        user: Any,
        settings: Any,
    ) -> list[dict[str, Any]] | None:
        """Delegate to the extracted source (see ``context_sources``)."""
        return await fetch_birthdays_context(user_id, user, settings)

    async def _fetch_recent_other_notifications(
        self,
        db: AsyncSession,
        user_id: UUID,
        user: Any,
    ) -> list[dict[str, str]] | None:
        """Delegate to the extracted source (see ``context_sources``)."""
        return await fetch_recent_other_notifications(db, user_id, user)

    # ------------------------------------------------------------------
    # Journals (Personal Journals — semantic relevance search)
    # ------------------------------------------------------------------

    def _build_second_pass_query(self, context: HeartbeatContext) -> str:
        """Build a semantic search query from aggregated heartbeat context.

        Combines summaries of available context sources into a query that
        selects the most relevant journal entries AND user memories for
        this specific notification cycle (second-pass sources, P8).

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
        # Check user-level journals flag (fall back to system default)
        from src.core.config import settings as app_settings

        if not getattr(user, "journals_enabled", app_settings.journals_enabled):
            return None

        try:
            from src.domains.journals.constants import (
                JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS,
            )
            from src.domains.journals.embedding import get_journal_embeddings
            from src.domains.journals.repository import JournalEntryRepository

            repo = JournalEntryRepository(self._db)

            # Use the same embedding model as journal creation (OpenAI, 1536 dim)
            embeddings = get_journal_embeddings()
            search_query = query or "user preferences observations patterns priorities"
            query_embedding = await embeddings.aembed_query(search_query)

            if not query_embedding:
                return None

            scored_entries = await repo.search_by_relevance(
                user_id=user_id,
                query_embedding=query_embedding,
                limit=3,  # Keep small for heartbeat budget
                min_score=app_settings.journal_context_min_score,
                # Operational injection carries only L1/L2 directives; L0 (private
                # feedstock) and L3 (carried by the portrait brief) are excluded (ADR-088).
                exclude_levels=JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS,
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
