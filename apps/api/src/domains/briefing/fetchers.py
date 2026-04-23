"""Source fetchers — one pure async function per dashboard card.

Contract per fetcher:
- Returns a populated *Data pydantic model on success (may have empty items list).
- Raises ConnectorNotConfiguredError if the user has no active connector for the source.
- Raises ConnectorAccessError on a recoverable connector failure (token expired, etc.).
- Any other exception is caught upstream by BriefingService._section() and mapped to ERROR.

CRITICAL — DB SESSIONS:
SQLAlchemy AsyncSession does NOT allow concurrent operations on a single session
(`InvalidRequestError: concurrent operations are not permitted`). Since the
BriefingService runs 6 fetchers in parallel via asyncio.gather, each fetcher
MUST acquire its own session via `get_db_context()` and never share the
request-scoped session injected by FastAPI Depends.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog

from src.core.constants import (
    GMAIL_FORMAT_METADATA,
    HEALTH_METRICS_USER_TOGGLE_ATTR,
)
from src.domains.auth.models import User
from src.domains.auth.user_location_service import (
    NoLocationAvailableError,
    UserLocationService,
)
from src.domains.briefing.constants import (
    BRIEFING_AGENDA_LOOKAHEAD_HOURS,
    BRIEFING_BIRTHDAY_PAGE_SIZE,
    BRIEFING_BIRTHDAY_PAGINATION_MAX_PAGES,
    BRIEFING_HEALTH_WINDOW_DAYS,
    BRIEFING_MAX_AGENDA_ITEMS,
    BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS,
    BRIEFING_MAX_BIRTHDAYS_ITEMS,
    BRIEFING_MAX_MAILS_ITEMS,
    BRIEFING_MAX_REMINDERS_ITEMS,
    BRIEFING_WEATHER_FORECAST_CNT,
    ERROR_CODE_CONNECTOR_NETWORK,
    ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
    ERROR_CODE_CONNECTOR_RATE_LIMIT,
)
from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
)
from src.domains.briefing.formatters import (
    daily_average_from_breakdown,
    extract_today_value_from_summary,
    format_agenda_event,
    format_email_item,
    format_reminder_item,
    format_weather_data,
    is_event_past,
    make_health_summary_item,
    upcoming_birthdays_from_connections,
)
from src.domains.briefing.schemas import (
    AgendaData,
    BirthdaysData,
    HealthData,
    MailsData,
    RemindersData,
    WeatherData,
)
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.service import ConnectorService
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.heartbeat.geocoding import resolve_city_name
from src.domains.reminders.service import ReminderService
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


# =============================================================================
# Internal HTTP error classification
# =============================================================================


def _classify_http_error(exc: Exception) -> str:
    """Map an HTTP/network exception to a stable error_code."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
        if status == 429:
            return ERROR_CODE_CONNECTOR_RATE_LIMIT
    return ERROR_CODE_CONNECTOR_NETWORK


# =============================================================================
# Weather
# =============================================================================


async def fetch_weather(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
) -> WeatherData:
    """Fetch current weather + short-term forecast for the user's effective location.

    Raises:
        ConnectorNotConfiguredError: if OpenWeatherMap key is missing OR no usable location.
        ConnectorAccessError: on HTTP/network failure (token expired, rate-limit, etc.).
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_api_key_credentials(
            user.id, ConnectorType.OPENWEATHERMAP
        )
        if not credentials:
            raise ConnectorNotConfiguredError("openweathermap")

        try:
            location = await UserLocationService(db).get_effective_location_for_proactive(user)
        except NoLocationAvailableError:
            raise ConnectorNotConfiguredError("location") from None

    client = OpenWeatherMapClient(api_key=credentials.api_key, user_id=user.id)
    try:
        results = await asyncio.gather(
            client.get_current_weather(
                lat=location.lat,
                lon=location.lon,
                units="metric",
                lang=language,
            ),
            client.get_forecast(
                lat=location.lat,
                lon=location.lon,
                units="metric",
                lang=language,
                cnt=BRIEFING_WEATHER_FORECAST_CNT,
            ),
            resolve_city_name(lat=location.lat, lon=location.lon, api_key=credentials.api_key),
            return_exceptions=False,
        )
    except (TimeoutError, httpx.HTTPError) as exc:
        raise ConnectorAccessError("openweathermap", _classify_http_error(exc), str(exc)) from exc
    finally:
        await client.close()

    current, forecast, city = results
    return format_weather_data(
        current=current,
        forecast=forecast,
        city=city if isinstance(city, str) else None,
        user_tz=user_tz,
    )


# =============================================================================
# Agenda (multi-provider)
# =============================================================================


async def fetch_agenda(
    *,
    user: User,
    user_tz: ZoneInfo,
) -> AgendaData:
    """Fetch the next ~24 h calendar events from the active provider.

    Uses dynamic provider resolution + the user's preferred default calendar
    (mirrors the heartbeat aggregator pattern — users with a non-primary
    default calendar see their actual events).

    Raises:
        ConnectorNotConfiguredError: if no active calendar connector for the user.
        ConnectorAccessError: on credential resolution failure or HTTP error.
    """
    from src.domains.connectors.preferences import ConnectorPreferencesService
    from src.domains.connectors.preferences.resolver import resolve_calendar_name
    from src.domains.connectors.repository import ConnectorRepository

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(user.id, "calendar", connector_service)
        if resolved_type is None:
            raise ConnectorNotConfiguredError("calendar")

        credentials: Any = (
            await connector_service.get_apple_credentials(user.id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user.id, resolved_type)
        )
        if not credentials:
            raise ConnectorAccessError(
                "calendar",
                ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
                "Credentials missing or refresh failed",
            )

        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            raise ConnectorNotConfiguredError("calendar")
        client = client_class(user.id, credentials, connector_service)

        # Resolve the user's preferred default calendar (falls back to "primary").
        # Mirrors the proven heartbeat ContextAggregator._fetch_calendar pattern.
        calendar_id: str = "primary"
        try:
            repo = ConnectorRepository(db)
            connector = await repo.get_by_user_and_type(user.id, resolved_type)
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
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            logger.warning(
                "briefing_calendar_preference_resolution_failed",
                user_id=str(user.id),
                error=str(exc),
            )

        now = datetime.now(UTC)
        try:
            result = await client.list_events(
                time_min=now.isoformat(),
                time_max=(now + timedelta(hours=BRIEFING_AGENDA_LOOKAHEAD_HOURS)).isoformat(),
                max_results=BRIEFING_MAX_AGENDA_ITEMS,
                calendar_id=calendar_id,
                fields=["id", "summary", "start", "end", "location"],
            )
        except (TimeoutError, httpx.HTTPError) as exc:
            raise ConnectorAccessError("calendar", _classify_http_error(exc), str(exc)) from exc

    raw_events = result.get("items", []) or []
    # Drop any event whose end is already past (defensive — Google's timeMin
    # filter is end-time-based but edge cases like all-day events ending at
    # midnight may still slip through).
    upcoming = [e for e in raw_events if not is_event_past(e, now, user_tz)]
    return AgendaData(events=[format_agenda_event(e, user_tz) for e in upcoming])


# =============================================================================
# Mails (multi-provider)
# =============================================================================


async def fetch_mails(
    *,
    user: User,
    user_tz: ZoneInfo,
) -> MailsData:
    """Fetch today's unread inbox emails from the active provider.

    All providers normalize email shape to top-level from/subject/snippet/internalDate
    (see context_aggregator._fetch_emails for reference behaviour).
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        resolved_type = await resolve_active_connector(user.id, "email", connector_service)
        if resolved_type is None:
            raise ConnectorNotConfiguredError("email")

        credentials: Any = (
            await connector_service.get_apple_credentials(user.id, resolved_type)
            if resolved_type.is_apple
            else await connector_service.get_connector_credentials(user.id, resolved_type)
        )
        if not credentials:
            raise ConnectorAccessError(
                "email",
                ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
                "Credentials missing or refresh failed",
            )

        client_class = ClientRegistry.get_client_class(resolved_type)
        if client_class is None:
            raise ConnectorNotConfiguredError("email")
        client = client_class(user.id, credentials, connector_service)

        # All unread emails in INBOX (not date-filtered — the user wants every
        # unread, regardless of when it arrived).
        try:
            result = await client.search_emails(
                query="is:unread in:inbox",
                max_results=BRIEFING_MAX_MAILS_ITEMS,
                use_cache=True,
            )
        except (TimeoutError, httpx.HTTPError) as exc:
            raise ConnectorAccessError("email", _classify_http_error(exc), str(exc)) from exc

        messages = result.get("messages", []) or []
        full_messages = []
        for msg in messages:
            # Apple returns IDs-only; full bodies are cached in Redis — get_message is a hit.
            if set(msg.keys()) <= {"id", "threadId"}:
                try:
                    full = await client.get_message(
                        msg["id"], format=GMAIL_FORMAT_METADATA, use_cache=True
                    )
                    if full:
                        full_messages.append(full)
                except (TimeoutError, httpx.HTTPError) as exc:
                    logger.debug(
                        "briefing_mail_fetch_skipped",
                        user_id=str(user.id),
                        message_id=msg.get("id"),
                        error=str(exc),
                    )
            else:
                full_messages.append(msg)

    items = [format_email_item(m, user_tz) for m in full_messages[:BRIEFING_MAX_MAILS_ITEMS]]
    return MailsData(items=items, total_unread_today=len(full_messages))


# =============================================================================
# Birthdays (Google Contacts only — Apple/MS lack a native birthday field)
# =============================================================================


async def fetch_birthdays(*, user: User) -> BirthdaysData:
    """Fetch upcoming birthdays from Google Contacts (full-scan, bypassed cap).

    Bypasses the global ``apply_max_items_limit`` (= ``api_max_items_per_request``,
    hard cap 50) to use the People API's native max page size of 1000. This is
    critical for users with > 50 contacts — without bypass, contacts beyond
    the first page wouldn't be inspected.

    Cache TTL = 7 days (see SECTION_BIRTHDAYS_TTL_SECONDS): birthdays are
    quasi-static and a full-scan is costly. Force-refresh rebuilds the cache.

    The bypass is implemented by calling ``client._make_request`` directly
    (skips the public ``list_connections`` wrapper and its security limit).
    """
    from src.domains.connectors.clients.google_people_client import GooglePeopleClient

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            user.id, ConnectorType.GOOGLE_CONTACTS
        )
        if not credentials:
            raise ConnectorNotConfiguredError("google_contacts")

        client = GooglePeopleClient(user.id, credentials, connector_service)
        all_connections: list[dict[str, Any]] = []
        page_token: str | None = None

        try:
            for _ in range(BRIEFING_BIRTHDAY_PAGINATION_MAX_PAGES):
                params: dict[str, Any] = {
                    "personFields": "names,birthdays",
                    "pageSize": BRIEFING_BIRTHDAY_PAGE_SIZE,
                }
                if page_token:
                    params["pageToken"] = page_token

                # Direct API call — bypasses apply_max_items_limit on purpose
                # (see fetcher docstring for justification).
                response = await client._make_request(
                    "GET", "/people/me/connections", params=params
                )
                all_connections.extend(response.get("connections", []) or [])
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            else:
                logger.info(
                    "briefing_birthdays_pagination_cap_reached",
                    user_id=str(user.id),
                    pages=BRIEFING_BIRTHDAY_PAGINATION_MAX_PAGES,
                    contacts=len(all_connections),
                )
        except (TimeoutError, httpx.HTTPError) as exc:
            raise ConnectorAccessError(
                "google_contacts", _classify_http_error(exc), str(exc)
            ) from exc

        logger.info(
            "briefing_birthdays_fetched",
            user_id=str(user.id),
            total_contacts=len(all_connections),
        )

    items = upcoming_birthdays_from_connections(
        all_connections,
        horizon_days=BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS,
        max_items=BRIEFING_MAX_BIRTHDAYS_ITEMS,
    )
    return BirthdaysData(items=items)


# =============================================================================
# Reminders (always available — local DB)
# =============================================================================


async def fetch_reminders(
    *,
    user_id: UUID,
    user_tz: ZoneInfo,
) -> RemindersData:
    """Fetch active (pending) reminders for the user.

    Always succeeds — this fetcher does not raise ConnectorNotConfiguredError.
    The card is always visible (empty state when no reminder).
    """
    async with get_db_context() as db:
        service = ReminderService(db)
        pending = await service.list_pending_for_user(user_id)
    items = [format_reminder_item(r, user_tz) for r in pending[:BRIEFING_MAX_REMINDERS_ITEMS]]
    return RemindersData(items=items)


# =============================================================================
# Health metrics (masked when no fresh data — by design)
# =============================================================================


async def fetch_health(*, user: User) -> HealthData:
    """Fetch today's value + 14-day rolling average per health kind.

    For each registered kind (steps, heart_rate):
    - ``compute_kind_summary`` (default time_min = today midnight UTC)
      → today's aggregate (SUM for steps, AVG for heart_rate)
    - ``compute_kind_daily_breakdown(days=14)`` → list of daily values
      → averaged to produce the per-day mean over the rolling window

    Sequential calls (no asyncio.gather): SQLAlchemy AsyncSession is not
    concurrent-safe, and each call is a fast local DB query.
    """
    from src.core.config import settings as app_settings
    from src.domains.health_metrics.kinds import HEALTH_KINDS

    if not getattr(app_settings, "health_metrics_enabled", False):
        raise ConnectorNotConfiguredError("health")
    if not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
        raise ConnectorNotConfiguredError("health")

    async with get_db_context() as db:
        service = HealthMetricsService(db)
        # Sequential — same session, no concurrent ops allowed.
        per_kind_data: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
        for kind in HEALTH_KINDS:
            today_summary = await service.compute_kind_summary(user.id, kind)
            window_breakdown = await service.compute_kind_daily_breakdown(
                user.id, kind, days=BRIEFING_HEALTH_WINDOW_DAYS
            )
            per_kind_data.append((kind, today_summary, window_breakdown))

    items = []
    for kind, today_summary, breakdown in per_kind_data:
        if kind not in ("steps", "heart_rate"):
            continue
        value_today = extract_today_value_from_summary(today_summary, kind=kind)
        avg_window, days_count = daily_average_from_breakdown(
            breakdown, window_days=BRIEFING_HEALTH_WINDOW_DAYS
        )
        # Skip the kind only when BOTH values are missing (no data anywhere).
        if value_today is None and avg_window is None:
            continue
        spec = HEALTH_KINDS[kind]
        items.append(
            make_health_summary_item(
                kind=kind,
                value_today=value_today,
                value_avg_window=avg_window,
                unit=spec.unit,
                window_days=BRIEFING_HEALTH_WINDOW_DAYS,
                days_with_data=days_count,
            )
        )

    if not items:
        raise ConnectorNotConfiguredError("health")
    return HealthData(items=items)
