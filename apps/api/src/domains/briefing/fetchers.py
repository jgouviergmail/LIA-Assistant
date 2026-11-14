"""Source fetchers — one pure async function per dashboard card.

The Workboard card's fetcher lives in ``workboard_card.py``, the SMS card's in
``sms_context.py``.

Contract per fetcher:
- Returns a populated *Data pydantic model on success (may have empty items list).
- Raises ConnectorNotConfiguredError if the user has no active connector for the source.
- Raises ConnectorAccessError on a recoverable connector failure (token expired, etc.).
- Any other exception is caught upstream by BriefingService._section() and mapped to ERROR.

CRITICAL — DB SESSIONS:
SQLAlchemy AsyncSession does NOT allow concurrent operations on a single session
(`InvalidRequestError: concurrent operations are not permitted`). Since the
BriefingService runs 9 fetchers in parallel via asyncio.gather, each fetcher
MUST acquire its own session via `get_db_context()` and never share the
request-scoped session injected by FastAPI Depends.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, NoReturn
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    GMAIL_FORMAT_METADATA,
    HEALTH_METRICS_USER_TOGGLE_ATTR,
    TASK_LISTS_READ_MAX,
)
from src.core.exceptions import ConnectorAPIError, MaxRetriesExceededError
from src.core.time_utils import now_utc
from src.domains.agents.services.qualification.publication import source_binding
from src.domains.agents.tools.weather_environment_enrichment import (
    environment_enrichment_active,
    extras_when_active,
)
from src.domains.briefing.classification import classify_briefing_items
from src.domains.briefing.constants import (
    BRIEFING_WEATHER_ALERT_SLOTS,
    BRIEFING_WEATHER_FORECAST_CNT,
    EDITORIAL_MAIL_SCAN_MAX,
    ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
)
from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
    LocationNotConfiguredError,
)
from src.domains.briefing.exceptions import (
    classify_http_error as _classify_http_error,
)
from src.domains.briefing.formatters import (
    ForecastAlertRule,
    daily_average_from_breakdown,
    detect_forecast_alert,
    extract_today_value_from_summary,
    format_agenda_event,
    format_email_item,
    format_reminder_item,
    format_weather_data,
    is_event_past,
    make_health_summary_item,
)
from src.domains.briefing.schemas import (
    AgendaData,
    BirthdaysData,
    DocumentItem,
    DocumentsData,
    ForecastAlert,
    ForYouAutomationItem,
    ForYouData,
    ForYouLoopItem,
    HealthData,
    MailsData,
    RemindersData,
    TasksData,
    WeatherData,
)
from src.domains.briefing.tasks_card import card_items
from src.domains.connectors.clients.normalizers.calendar_links import CONFERENCE_FIELDS
from src.domains.connectors.clients.task_lists import TaskListing, read_every_task_list
from src.domains.connectors.companion_weather import publish_companion_weather
from src.domains.connectors.mail_reply_states import attach_reply_states
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.weather_provider import (
    open_platform_weather_client,
    resolve_weather_client,
)
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.heartbeat.geocoding import resolve_city_name
from src.domains.reminders.service import ReminderService
from src.domains.shared.commercial_content import commercial_mail
from src.domains.users.user_location_service import (
    NoLocationAvailableError,
    UserLocationService,
)
from src.infrastructure.async_utils import settled_or_raise
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from src.domains.scheduled_actions.models import ScheduledAction
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)


# =============================================================================
# Internal HTTP error classification
# =============================================================================


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
        ConnectorNotConfiguredError: if no weather provider is active OR no
            usable location. Both providers of the "weather" category (Google
            Weather platform-key, OpenWeatherMap personal key) are OWM-shaped,
            so everything below is provider-agnostic (lot E, 2026-08).
        ConnectorAccessError: on HTTP/network failure (token expired, rate-limit, etc.).
    """
    client, location, environment_active = await _open_weather(
        user,
        open_client=resolve_weather_client,
        source=_CARD_WEATHER_SOURCE,
        with_environment=True,
    )
    # A provider serving its own daily summaries (W1b) is read for the alert's 24 hours
    # plus ONE daily request; the others keep their five days of slots (one OWM call).
    native_daily = getattr(client, "native_daily_summaries", False) is True
    days = settings.briefing_weather_daily_forecast_days

    try:
        settled = await asyncio.gather(
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
                cnt=BRIEFING_WEATHER_ALERT_SLOTS if native_daily else BRIEFING_WEATHER_FORECAST_CNT,
            ),
            (
                client.get_daily_summaries(location.lat, location.lon, lang=language, days=days)
                if native_daily
                else _no_daily_summaries()
            ),
            resolve_city_name(lat=location.lat, lon=location.lon, client=client),
            # AQ/pollen beside the weather calls, not before them (fail-quiet).
            extras_when_active(environment_active, user.id, location.lat, location.lon, language),
            # Every sibling settles before the card fails: one left running billed its
            # provider after the act's spend was filed, on a client closed under it
            # (fresh review B3).
            return_exceptions=True,
        )
        current, forecast, daily, city, environment = settled_or_raise(settled, quiet={4})
    except (
        TimeoutError,
        httpx.HTTPError,
        MaxRetriesExceededError,
        ConnectorAPIError,
    ) as exc:
        # MaxRetriesExceededError: retry-exhaustion from the migrated OWM client
        # (BaseAPIKeyClient); classify from the underlying cause when available.
        cause = getattr(exc, "last_error", None) or exc
        raise ConnectorAccessError(
            _CARD_WEATHER_SOURCE, _classify_http_error(cause), str(exc)
        ) from exc
    finally:
        await client.close()
    # The person's place, read now: the companion shows it too (ADR-294, 2026-11-13).
    await publish_companion_weather(user.id, current)

    return format_weather_data(
        current=current,
        forecast=forecast,
        city=city if isinstance(city, str) else None,
        user_tz=user_tz,
        daily_forecast_days=days,
        now=now_utc(),
        environment=environment,
        daily_summaries=daily,
    )


async def _no_daily_summaries() -> None:
    """The daily strip of a provider without its own summaries: aggregated from its slots."""
    return None


#: The source name the card's refusals carry — whichever provider serves it.
_CARD_WEATHER_SOURCE = "openweathermap"
#: The one source a weather routine reads (ADR-322 amendment 2026-09-29).
_ROUTINE_WEATHER_SOURCE = ConnectorType.GOOGLE_WEATHER.value

#: How a reader obtains its weather client: the person's provider, or the platform's.
WeatherClientOpener = Callable[[UUID, ConnectorService], Awaitable[Any | None]]


async def _open_weather(
    user: User, *, open_client: WeatherClientOpener, source: str, with_environment: bool
) -> tuple[Any, Any, bool]:
    """The weather client, the effective location, and whether AQ/pollen runs.

    Read in ONE session, closed before any provider is called (ADR-304). The
    client is closed here when a later read refuses — it used to leak on the
    « no location » path.

    Args:
        user: Whose weather.
        open_client: Which client serves this reader.
        source: The source name a refusal carries.
        with_environment: Whether to read the air-quality/pollen switch at all.

    Returns:
        ``(client, location, environment_active)`` — the caller closes the client.

    Raises:
        ConnectorNotConfiguredError: No weather provider.
        LocationNotConfiguredError: A provider, but no usable location.
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        client = await open_client(user.id, connector_service)
        if client is None:
            raise ConnectorNotConfiguredError(source)
        try:
            try:
                location = await UserLocationService(db).get_effective_location_for_proactive(user)
            except NoLocationAvailableError:
                raise LocationNotConfiguredError() from None
            # AQ/pollen enrichment (2026-08): whether it runs is READ here; the
            # provider is called by the caller, once this session is closed.
            environment_active = with_environment and await environment_enrichment_active(
                user.id, connector_service
            )
        except BaseException:
            await client.close()
            raise
    return client, location, environment_active


async def fetch_forecast_alert(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
    now: datetime,
    rule: ForecastAlertRule,
) -> ForecastAlert | None:
    """The first change the rule accepts, from Google Weather — what a weather routine checks.

    ALWAYS the instance's Google Weather, whatever provider the person chose:
    what fires a routine is the source the platform guarantees (ADR-322
    amendment 2026-09-29). Two billed calls: the current conditions and ONE
    page of the hourly forecast — every hour of the horizon plus the hour under
    way, never the card's five days of 3-hour samples, between which a change
    due within the hour falls. No city name, no air quality, no pollen.

    Args:
        user: Whose weather.
        user_tz: Their zone, for the alert's local time.
        language: Their language, for the provider's labels.
        now: The check's instant.
        rule: What counts as a change, and how far ahead.

    Returns:
        The alert, or ``None`` when no accepted change is coming.

    Raises:
        ConnectorNotConfiguredError: The instance withholds Google Weather, or
            no usable location.
        ConnectorAccessError: On HTTP/network failure.
    """
    client, location, _ = await _open_weather(
        user,
        open_client=open_platform_weather_client,
        source=_ROUTINE_WEATHER_SOURCE,
        with_environment=False,
    )
    hours = math.ceil(rule.horizon.total_seconds() / 3600) + 1
    try:
        current, forecast = await asyncio.gather(
            client.get_current_weather(
                lat=location.lat, lon=location.lon, units="metric", lang=language
            ),
            client.get_hourly_forecast(
                lat=location.lat, lon=location.lon, lang=language, hours=hours
            ),
        )
    except (
        TimeoutError,
        httpx.HTTPError,
        MaxRetriesExceededError,
        ConnectorAPIError,
    ) as exc:
        cause = getattr(exc, "last_error", None) or exc
        raise ConnectorAccessError(
            _ROUTINE_WEATHER_SOURCE, _classify_http_error(cause), str(exc)
        ) from exc
    finally:
        await client.close()
    await publish_companion_weather(user.id, current)
    return detect_forecast_alert(
        current=current, forecast=forecast, user_tz=user_tz, now=now, rule=rule
    )


# =============================================================================
# Agenda (multi-provider)
# =============================================================================


async def fetch_agenda(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
    lookahead_hours: int | None = None,
    qualify_items: bool = True,
) -> AgendaData:
    """Fetch the next ~24 h calendar events from the active provider.

    Uses dynamic provider resolution + the user's preferred default calendar
    (mirrors the heartbeat aggregator pattern — users with a non-primary
    default calendar see their actual events). The ``language`` argument is
    forwarded to ``format_agenda_event`` so event times are rendered in the
    user's locale (today / tomorrow / dd-mm-yyyy ordering).

    ``lookahead_hours`` narrows or widens the window for a reader with its own
    — a calendar routine asking « within the next N hours » (ADR-322) — and
    defaults to the card's ``briefing_agenda_lookahead_hours``.

    Raises:
        ConnectorNotConfiguredError: if no active calendar connector for the user.
        ConnectorAccessError: on credential resolution failure or HTTP error.
    """
    from src.domains.connectors.calendar_access import (
        CalendarUnavailable,
        open_active_calendar,
    )

    async with open_active_calendar(user.id) as access:
        # The refusal is NAMED, so the two sentences a reader may need stay
        # distinct: "connect a calendar" and "your connection expired".
        if access is CalendarUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "calendar",
                ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
                "Credentials missing or refresh failed",
            )
        if isinstance(access, CalendarUnavailable):
            raise ConnectorNotConfiguredError("calendar")

        now = datetime.now(UTC)
        window = timedelta(hours=lookahead_hours or settings.briefing_agenda_lookahead_hours)
        try:
            result = await access.client.list_events(
                time_min=now.isoformat(),
                time_max=(now + window).isoformat(),
                max_results=settings.briefing_max_agenda_items,
                calendar_id=access.calendar_id,
                fields=["id", "summary", "start", "end", "location", *CONFERENCE_FIELDS],
            )
        except (TimeoutError, httpx.HTTPError) as exc:
            raise ConnectorAccessError("calendar", _classify_http_error(exc), str(exc)) from exc

        binding = source_binding(access.client)
        provider = getattr(access.connector_type, "value", "")
        calendar_id = access.calendar_id

    raw_events = result.get("items", []) or []
    # Drop any event whose end is already past (defensive — Google's timeMin
    # filter is end-time-based but edge cases like all-day events ending at
    # midnight may still slip through).
    upcoming = [e for e in raw_events if not is_event_past(e, now, user_tz)]
    upcoming = await classify_briefing_items(
        upcoming,
        kind="event",
        user_id=user.id,
        provider=provider,
        binding=binding if qualify_items else "",
        timezone=str(user_tz),
        container=calendar_id,
    )
    return AgendaData(
        events=[
            format_agenda_event(e, user_tz, language, calendar_id=calendar_id) for e in upcoming
        ]
    )


# =============================================================================
# Mails (multi-provider)
# =============================================================================


async def fetch_mails(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
    exclude_commercial_mails: bool = False,
    qualify_items: bool = True,
    situate_items: bool = True,
) -> MailsData:
    """Fetch the unread inbox emails from the active provider.

    All providers normalize email shape to top-level from/subject/snippet/internalDate.
    The ``language`` argument is forwarded to ``format_email_item`` so received
    timestamps are rendered with the user's locale conventions.

    Unread is not unanswered (ADR-379): each listed mail says where it stands in its
    conversation, read through the one door while the mailbox is open. A reader that
    only MATCHES the listing (a routine's condition) passes ``situate_items=False``.
    """
    from src.domains.connectors.active_client import (
        ActiveClient,
        ClientUnavailable,
        open_active_client,
    )

    # The shared door: no session held while the mailbox answers, and the
    # transport closed on every path (it was never closed here) — ADR-304.
    async with open_active_client("email", user.id) as opened:
        if opened is ClientUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "email",
                ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
                "Credentials missing or refresh failed",
            )
        if not isinstance(opened, ActiveClient):
            raise ConnectorNotConfiguredError("email")
        full_messages = await _unread_inbox(
            opened.client,
            user,
            scan_max=(
                max(settings.briefing_max_mails_items, EDITORIAL_MAIL_SCAN_MAX)
                if exclude_commercial_mails
                else None
            ),
        )
        eligible = (
            [m for m in full_messages if not commercial_mail(m)]
            if exclude_commercial_mails
            else full_messages
        )
        listed = eligible[: settings.briefing_max_mails_items]
        if situate_items:
            await attach_reply_states(opened.client, listed, user_timezone=str(user_tz))
        binding = source_binding(opened.client)
        provider = getattr(opened.connector_type, "value", "")

    selected = await classify_briefing_items(
        listed,
        kind="email",
        user_id=user.id,
        provider=provider,
        binding=binding if qualify_items else "",
        timezone=str(user_tz),
    )
    items = [format_email_item(m, user_tz, language) for m in selected]
    return MailsData(items=items, total_unread_today=len(full_messages))


async def _unread_inbox(
    client: Any, user: User, *, scan_max: int | None = None
) -> list[dict[str, Any]]:
    """Every unread INBOX message of an open client, full metadata.

    Not date-filtered: the reader wants every unread, whenever it arrived.
    Apple returns IDs only; its full bodies are cached in Redis, so each
    ``get_message`` is a cache hit.
    """
    try:
        result = await client.search_emails(
            query="is:unread in:inbox",
            max_results=(scan_max if scan_max is not None else settings.briefing_max_mails_items),
            use_cache=True,
        )
    except (TimeoutError, httpx.HTTPError) as exc:
        raise ConnectorAccessError("email", _classify_http_error(exc), str(exc)) from exc

    full_messages: list[dict[str, Any]] = []
    for msg in result.get("messages", []) or []:
        if not set(msg.keys()) <= {"id", "threadId"}:
            full_messages.append(msg)
            continue
        try:
            full = await client.get_message(msg["id"], format=GMAIL_FORMAT_METADATA, use_cache=True)
        except (TimeoutError, httpx.HTTPError) as exc:
            logger.debug(
                "briefing_mail_fetch_skipped",
                user_id=str(user.id),
                message_id=msg.get("id"),
                error=str(exc),
            )
            continue
        if full:
            full_messages.append(full)
    return full_messages


# =============================================================================
# Birthdays (the active contacts provider: Google, Apple or Microsoft)
# =============================================================================

#: The card's source: the contacts category, whichever provider serves it.
_BIRTHDAYS_SOURCE = "contacts"


async def fetch_birthdays(*, user: User, user_tz: ZoneInfo) -> BirthdaysData:
    """Fetch upcoming birthdays via the shared connectors fetch (P7).

    The book read + computation live in ``connectors.birthdays`` so the
    heartbeat can reuse them without a briefing import cycle. This wrapper
    only translates the neutral outcomes into the briefing section-status
    contract (NOT_CONFIGURED / ERROR exceptions): an active provider whose
    credentials cannot be read asks to reconnect (as the mails card does),
    exhausted retries are classified on the error they last met.

    Cache TTL = seconds until next local midnight (computed by the service
    layer). The contact list is quasi-static, but `days_until` on each
    BirthdayItem is pre-computed against `today` — caching it for several
    days would freeze yesterday's "1 day" into today's display. Expiring at
    local midnight keeps the relative-day arithmetic correct without any
    manual refresh. Force-refresh rebuilds the cache immediately.
    """
    from src.domains.connectors.birthdays import (
        BirthdayFetchError,
        fetch_upcoming_birthdays,
    )

    try:
        items = await fetch_upcoming_birthdays(
            user.id,
            user_tz,
            horizon_days=settings.briefing_max_birthdays_horizon_days,
            max_items=settings.briefing_max_birthdays_items,
        )
    except BirthdayFetchError as exc:
        if exc.reason == "no_credentials":
            raise ConnectorAccessError(
                _BIRTHDAYS_SOURCE, ERROR_CODE_CONNECTOR_OAUTH_EXPIRED, exc.detail
            ) from exc
        # Classify from the ORIGINAL exception (__cause__, or what exhausted
        # retries last met) so the section status keeps its granularity
        # (401/429/network).
        original = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
        cause = getattr(original, "last_error", None) or original
        raise ConnectorAccessError(
            _BIRTHDAYS_SOURCE, _classify_http_error(cause), exc.detail
        ) from exc

    if items is None:
        raise ConnectorNotConfiguredError(_BIRTHDAYS_SOURCE)

    return BirthdaysData(items=items)


# =============================================================================
# Reminders (always available — local DB)
# =============================================================================


async def fetch_reminders(
    *,
    user_id: UUID,
    user_tz: ZoneInfo,
    language: str | None = None,
) -> RemindersData:
    """Fetch active (pending) reminders for the user.

    Always succeeds — this fetcher does not raise ConnectorNotConfiguredError.
    The card is always visible (empty state when no reminder).

    The user's `language` drives the date / "tomorrow" formatting in
    `format_reminder_item` so a French user sees ``08:00 24/04/2026`` /
    ``08:00 demain`` rather than the English defaults.
    """
    async with get_db_context() as db:
        service = ReminderService(db)
        pending = await service.list_pending_for_user(user_id)
    items = [
        format_reminder_item(r, user_tz, language)
        for r in pending[: settings.briefing_max_reminders_items]
    ]
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
                user.id, kind, days=settings.briefing_health_window_days
            )
            per_kind_data.append((kind, today_summary, window_breakdown))

    items = []
    for kind, today_summary, breakdown in per_kind_data:
        if kind not in ("steps", "heart_rate"):
            continue
        value_today = extract_today_value_from_summary(today_summary, kind=kind)
        avg_window, days_count = daily_average_from_breakdown(
            breakdown, window_days=settings.briefing_health_window_days
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
                window_days=settings.briefing_health_window_days,
                days_with_data=days_count,
            )
        )

    if not items:
        raise ConnectorNotConfiguredError("health")
    return HealthData(items=items)


# =============================================================================
# Tasks & documents (the active tasks provider, the account's drive — P15)
# =============================================================================

#: A provider that could not be reached: what a card answers with a classified access error.
_TRANSPORT_FAILURES: tuple[type[Exception], ...] = (
    TimeoutError,
    httpx.HTTPError,
    MaxRetriesExceededError,
)
#: What one read among several may fail on while the card keeps the rest.
_READ_FAILURES: tuple[type[Exception], ...] = (*_TRANSPORT_FAILURES, ConnectorAPIError)


async def fetch_tasks(*, user: User, user_tz: ZoneInfo, whole_page: bool = False) -> TasksData:
    """Fetch strictly pending/overdue tasks of EVERY list of the active tasks provider.

    Scope (2026-07-22 arbitration): open items only, overdue (unbounded past)
    + due within ``briefing_tasks_horizon_days``; undated tasks are outside
    the card's temporal scope (the provider ``due_max`` filter excludes
    them). ``days_until_due`` renders client-side.

    Every list is read (owner, 2026-11-10), a few at a time through the one
    walk (``connectors/clients/task_lists``), and assembled by ``tasks_card``:
    each task names its own list by its real id, where the Tools open it. A list
    that fails leaves the others
    on the card, which then says it is partial; with nothing left to show the
    failure is the card's, « nothing to do » never being told on a list nobody
    read (ADR-303).

    ``whole_page`` keeps every task read instead of the card's first
    ``briefing_max_tasks_items``. A task routine (ADR-322) waits for the NEWEST
    overdue task, which the card's oldest-first cut drops as soon as the person
    has that many older ones.

    Raises:
        ConnectorNotConfiguredError: if no active tasks connector.
        ConnectorAccessError: on credential or HTTP failure.
    """
    from src.domains.connectors.active_client import ActiveClient, open_active_client

    due_max = (datetime.now(UTC) + timedelta(days=settings.briefing_tasks_horizon_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # Same door as the heartbeat: provider and credentials in one short
    # session; nothing held while Tasks answers.
    async with open_active_client("tasks", user.id) as opened:
        if not isinstance(opened, ActiveClient):
            raise ConnectorNotConfiguredError("tasks")
        listing = TaskListing(max_results=settings.briefing_max_tasks_items * 4, due_max=due_max)
        try:
            every = await read_every_task_list(
                opened.client,
                listing,
                lists_max=TASK_LISTS_READ_MAX,
                failures=_READ_FAILURES,
            )
        except _TRANSPORT_FAILURES as exc:
            raise _tasks_access_error(exc) from exc

    items = card_items(every.tasks(), today=datetime.now(user_tz).date(), zone=user_tz)
    failure = every.first_failure
    if failure is not None and not items:
        _raise_tasks_failure(failure)
    if not whole_page:
        items = items[: settings.briefing_max_tasks_items]
    return TasksData(
        items=items,
        overdue_count=sum(1 for t in items if t.overdue),
        partial=every.partial,
    )


def _raise_tasks_failure(failure: Exception) -> NoReturn:
    """The card's failure when no list gave anything: a provider's refusal stays what it is."""
    if isinstance(failure, ConnectorAPIError):
        raise failure
    raise _tasks_access_error(failure) from failure


def _tasks_access_error(exc: Exception) -> ConnectorAccessError:
    """The classified access error a transport failure of the tasks provider amounts to."""
    cause = getattr(exc, "last_error", None) or exc
    return ConnectorAccessError("tasks", _classify_http_error(cause), str(exc))


async def _document_path(client: Any, file: dict[str, Any], known: dict[str, Any]) -> str | None:
    """Where a file lives; a path that cannot be read leaves the file on the card."""
    try:
        path: str | None = await client.folder_path(file, known)
        return path
    except _READ_FAILURES as exc:
        logger.debug("briefing_document_path_unreadable", error_type=type(exc).__name__)
        return None


async def fetch_documents(
    *, user: User, user_tz: ZoneInfo, language: str | None = None
) -> DocumentsData:
    """Fetch the most recently modified files of the account's drive.

    Google Drive or OneDrive, whichever the account connected: the shared door
    reads it in a session of its own, closed before the provider is called
    (ADR-304). ``modified_local`` is pre-formatted with the profile timezone +
    language (reminders doctrine).

    Raises:
        ConnectorNotConfiguredError: if no drive is connected.
        ConnectorAccessError: on HTTP/network failure.
    """
    from src.domains.briefing.formatters import _format_trigger_at_local
    from src.domains.connectors.active_client import ActiveClient, open_active_client

    async with open_active_client("files", user.id) as opened:
        if not isinstance(opened, ActiveClient):
            raise ConnectorNotConfiguredError("drive")
        try:
            result = await opened.client.recent_files(settings.briefing_max_documents_items)
        except _TRANSPORT_FAILURES as exc:
            cause = getattr(exc, "last_error", None) or exc
            raise ConnectorAccessError("drive", _classify_http_error(cause), str(exc)) from exc
        files = (result.get("files", []) or [])[: settings.briefing_max_documents_items]
        known: dict[str, Any] = {}
        paths = [await _document_path(opened.client, file, known) for file in files]

    items: list[DocumentItem] = []
    for f, path in zip(files, paths, strict=True):
        modified_local = "?"
        raw_modified = f.get("modifiedTime")
        if raw_modified:
            try:
                modified_dt = datetime.fromisoformat(str(raw_modified).replace("Z", "+00:00"))
                modified_local = _format_trigger_at_local(modified_dt, user_tz, language)
            except ValueError, TypeError:
                # Unparseable Drive timestamp — the '?' placeholder renders.
                logger.debug("briefing_document_modified_unparseable")
        file_id = f.get("id")
        items.append(
            DocumentItem(
                name=f.get("name") or "Untitled",
                modified_local=modified_local,
                web_view_link=f.get("webViewLink"),
                mime_type=f.get("mimeType"),
                id=str(file_id) if file_id else None,
                path=path,
            )
        )
    return DocumentsData(items=items, provider=opened.connector_type.value)


# =============================================================================
# For you (open loops + automations digest — P15, interdomain Lot 4)
# =============================================================================


def _soonest_upcoming(
    actions: Sequence[ScheduledAction], now: datetime
) -> tuple[ScheduledAction, datetime] | None:
    """The next routine to fire, with the instant it fires at.

    The instant travels WITH the row rather than being read back from it:
    ``next_trigger_at`` is nullable since the recurrence rework (NULL = the
    series is over), and a filter narrows a VALUE, never an attribute — so
    ``min(..., key=lambda a: a.next_trigger_at)`` would still be typed
    ``datetime | None`` and would compare against None on an unlucky row.

    A condition routine never counts (ADR-322): its trigger is the system's next
    CHECK, minutes away, and « next automation in 6 min » would announce a run
    that only happens if the awaited fact does.

    Args:
        actions: The account's routines, paused ones included.
        now: Reference instant (UTC).

    Returns:
        The soonest enabled scheduled routine and its instant, or ``None`` when
        none is armed.
    """
    from src.domains.scheduled_actions.models import TriggerKind

    dated = [
        (action, action.next_trigger_at)
        for action in actions
        if action.is_enabled
        # Only a schedule announces a run: a condition's trigger is a check, a
        # webhook routine's a look at its calls (ADR-322, ADR-386).
        and action.trigger_kind == TriggerKind.TIME.value
        and action.next_trigger_at is not None
        and action.next_trigger_at >= now
    ]
    return min(dated, key=lambda pair: pair[1]) if dated else None


async def fetch_for_you(
    *, user_id: UUID, user_tz: ZoneInfo, language: str | None = None
) -> ForYouData:
    """Aggregate the LLM-free « For you » card (P15).

    - Open loops (ADR-139): top OPEN loops, earliest deadline first. Gated by
      ``OPEN_LOOPS_ENABLED`` — when off the sub-block is simply empty.
    - Automations digest (ADR-140): executions in the last 24 h + the next
      upcoming enabled automation, whose ``next_trigger_local`` is
      pre-formatted here (``language`` drives the "tomorrow"/date wording,
      same doctrine as the reminders card).

    Own DB session (briefing pattern). Never raises for the loops sub-block
    beyond the shared session errors — the card is a composition of local
    tables (fast, no external connector).
    """
    now = datetime.now(UTC)
    loops: list[ForYouLoopItem] = []
    recent: list[ForYouAutomationItem] = []
    next_automation: ForYouAutomationItem | None = None

    async with get_db_context() as db:
        if settings.open_loops_enabled:
            from src.domains.open_loops.repository import OpenLoopRepository

            open_rows = await OpenLoopRepository(db).list_open_for_user(
                user_id, limit=settings.briefing_max_open_loops_items
            )
            loops = [
                ForYouLoopItem(
                    id=str(row.id),
                    subject=row.subject,
                    counterparty=row.counterparty,
                    direction=row.direction,
                    due_hint=row.due_hint,
                    days_open=max(0, (now - row.created_at).days),
                )
                for row in open_rows
            ]

        from src.domains.scheduled_actions.service import ScheduledActionService

        actions = await ScheduledActionService(db).list_for_user(user_id)

    day_ago = now - timedelta(hours=24)
    recent = [
        ForYouAutomationItem(id=str(a.id), title=a.title, executed_at=a.last_executed_at)
        for a in actions
        if a.last_executed_at is not None and a.last_executed_at >= day_ago
    ]
    soonest = _soonest_upcoming(actions, now)
    if soonest is not None:
        from src.domains.briefing.formatters import _format_trigger_at_local

        action, soonest_at = soonest
        next_automation = ForYouAutomationItem(
            id=str(action.id),
            title=action.title,
            next_trigger_at=soonest_at,
            next_trigger_local=_format_trigger_at_local(soonest_at, user_tz, language),
        )

    return ForYouData(
        open_loops=loops,
        recent_automations=recent,
        next_automation=next_automation,
    )
