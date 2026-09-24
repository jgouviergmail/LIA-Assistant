"""Source fetchers — one pure async function per dashboard card.

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
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    GMAIL_FORMAT_METADATA,
    HEALTH_METRICS_USER_TOGGLE_ATTR,
)
from src.core.exceptions import ConnectorAPIError, MaxRetriesExceededError
from src.domains.agents.tools.weather_environment_enrichment import (
    environment_enrichment_active,
    fetch_environment_extras,
)
from src.domains.briefing.constants import (
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
)
from src.domains.briefing.schemas import (
    AgendaData,
    BirthdaysData,
    DocumentItem,
    DocumentsData,
    ForYouAutomationItem,
    ForYouData,
    ForYouLoopItem,
    HealthData,
    MailsData,
    RemindersData,
    TaskItem,
    TasksData,
    WeatherData,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.connectors.weather_provider import resolve_weather_client
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.heartbeat.geocoding import resolve_city_name
from src.domains.reminders.service import ReminderService
from src.domains.users.user_location_service import (
    NoLocationAvailableError,
    UserLocationService,
)
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from src.domains.scheduled_actions.models import ScheduledAction
    from src.domains.users.models import User

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
        ConnectorNotConfiguredError: if no weather provider is active OR no
            usable location. Both providers of the "weather" category (Google
            Weather platform-key, OpenWeatherMap personal key) are OWM-shaped,
            so everything below is provider-agnostic (lot E, 2026-08).
        ConnectorAccessError: on HTTP/network failure (token expired, rate-limit, etc.).
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        client = await resolve_weather_client(user.id, connector_service)
        if client is None:
            raise ConnectorNotConfiguredError("openweathermap")

        try:
            location = await UserLocationService(db).get_effective_location_for_proactive(user)
        except NoLocationAvailableError:
            raise ConnectorNotConfiguredError("location") from None

        # AQ/pollen enrichment (2026-08): whether it runs is READ here; the
        # provider is called below, once this session is closed (ADR-304).
        environment_active = await environment_enrichment_active(user.id, connector_service)

    # Fail-quiet: None and the card renders exactly as before.
    environment = (
        await fetch_environment_extras(user.id, location.lat, location.lon, language)
        if environment_active
        else None
    )

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
            resolve_city_name(lat=location.lat, lon=location.lon, client=client),
            return_exceptions=False,
        )
    except (TimeoutError, httpx.HTTPError, MaxRetriesExceededError, ConnectorAPIError) as exc:
        # MaxRetriesExceededError: retry-exhaustion from the migrated OWM client
        # (BaseAPIKeyClient); classify from the underlying cause when available.
        cause = getattr(exc, "last_error", None) or exc
        raise ConnectorAccessError("openweathermap", _classify_http_error(cause), str(exc)) from exc
    finally:
        await client.close()

    current, forecast, city = results
    return format_weather_data(
        current=current,
        forecast=forecast,
        city=city if isinstance(city, str) else None,
        user_tz=user_tz,
        daily_forecast_days=settings.briefing_weather_daily_forecast_days,
        environment=environment,
    )


# =============================================================================
# Agenda (multi-provider)
# =============================================================================


async def fetch_agenda(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
) -> AgendaData:
    """Fetch the next ~24 h calendar events from the active provider.

    Uses dynamic provider resolution + the user's preferred default calendar
    (mirrors the heartbeat aggregator pattern — users with a non-primary
    default calendar see their actual events). The ``language`` argument is
    forwarded to ``format_agenda_event`` so event times are rendered in the
    user's locale (today / tomorrow / dd-mm-yyyy ordering).

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
        try:
            result = await access.client.list_events(
                time_min=now.isoformat(),
                time_max=(
                    now + timedelta(hours=settings.briefing_agenda_lookahead_hours)
                ).isoformat(),
                max_results=settings.briefing_max_agenda_items,
                calendar_id=access.calendar_id,
                fields=["id", "summary", "start", "end", "location"],
            )
        except (TimeoutError, httpx.HTTPError) as exc:
            raise ConnectorAccessError("calendar", _classify_http_error(exc), str(exc)) from exc

    raw_events = result.get("items", []) or []
    # Drop any event whose end is already past (defensive — Google's timeMin
    # filter is end-time-based but edge cases like all-day events ending at
    # midnight may still slip through).
    upcoming = [e for e in raw_events if not is_event_past(e, now, user_tz)]
    return AgendaData(events=[format_agenda_event(e, user_tz, language) for e in upcoming])


# =============================================================================
# Mails (multi-provider)
# =============================================================================


async def fetch_mails(
    *,
    user: User,
    user_tz: ZoneInfo,
    language: str,
) -> MailsData:
    """Fetch today's unread inbox emails from the active provider.

    All providers normalize email shape to top-level from/subject/snippet/internalDate
    (see context_aggregator._fetch_emails for reference behaviour). The
    ``language`` argument is forwarded to ``format_email_item`` so received
    timestamps are rendered with the user's locale conventions.
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
        full_messages = await _unread_inbox(opened.client, user)

    items = [
        format_email_item(m, user_tz, language)
        for m in full_messages[: settings.briefing_max_mails_items]
    ]
    return MailsData(items=items, total_unread_today=len(full_messages))


async def _unread_inbox(client: Any, user: User) -> list[dict[str, Any]]:
    """Every unread INBOX message of an open client, full metadata.

    Not date-filtered: the reader wants every unread, whenever it arrived.
    Apple returns IDs only; its full bodies are cached in Redis, so each
    ``get_message`` is a cache hit.
    """
    try:
        result = await client.search_emails(
            query="is:unread in:inbox",
            max_results=settings.briefing_max_mails_items,
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
# Birthdays (Google Contacts only — Apple/MS lack a native birthday field)
# =============================================================================


async def fetch_birthdays(*, user: User, user_tz: ZoneInfo) -> BirthdaysData:
    """Fetch upcoming birthdays via the shared connectors fetch (P7).

    The full-scan + computation moved to ``connectors.birthdays`` so the
    heartbeat can reuse them without a briefing import cycle. This wrapper
    only translates the neutral outcomes into the briefing section-status
    contract (NOT_CONFIGURED / ERROR exceptions).

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
        # Classify from the ORIGINAL exception (__cause__) so the section
        # status keeps its historical granularity (401/429/network).
        original = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
        raise ConnectorAccessError(
            "google_contacts", _classify_http_error(original), exc.detail
        ) from exc

    if items is None:
        raise ConnectorNotConfiguredError("google_contacts")

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
# For you (open loops + automations digest — P15, interdomain Lot 4)
# =============================================================================


def _task_to_item(task: dict[str, Any], today_local: date) -> TaskItem | None:
    """Map one provider-normalized task to a TaskItem (None if not pending).

    Due semantics are DATE-ONLY in the user's local frame (birthdays
    doctrine): a task due today is on time — never "overdue" merely because
    00:00 UTC has passed.
    """
    if task.get("status") != "needsAction":
        return None
    due_date_iso: str | None = None
    days_until: int | None = None
    raw_due = task.get("due")
    if raw_due:
        try:
            due_date = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00")).date()
            due_date_iso = due_date.isoformat()
            days_until = (due_date - today_local).days
        except ValueError, TypeError:
            # Provider sent an unparseable due — keep the task, undated.
            logger.debug("briefing_task_due_unparseable", raw_due=str(raw_due)[:40])
    return TaskItem(
        title=task.get("title") or "Untitled",
        due_date_iso=due_date_iso,
        days_until_due=days_until,
        overdue=days_until is not None and days_until < 0,
    )


async def fetch_tasks(*, user: User, user_tz: ZoneInfo) -> TasksData:
    """Fetch strictly pending/overdue tasks from the active tasks provider.

    Scope (2026-07-22 arbitration): open items only, overdue (unbounded past)
    + due within ``briefing_tasks_horizon_days``; undated tasks are outside
    the card's temporal scope (the provider ``due_max`` filter excludes
    them). ``days_until_due`` renders client-side.

    Raises:
        ConnectorNotConfiguredError: if no active tasks connector.
        ConnectorAccessError: on credential or HTTP failure.
    """
    from src.domains.connectors.active_client import ActiveClient, open_active_client
    from src.domains.connectors.preferences.owner_defaults import (
        TASK_LIST,
        resolve_owner_container_id,
    )

    today_local = datetime.now(user_tz).date()
    due_max = (datetime.now(UTC) + timedelta(days=settings.briefing_tasks_horizon_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # Same door as the heartbeat: provider, credentials and the preferred
    # list's NAME in one short session; nothing held while Tasks answers.
    async with open_active_client("tasks", user.id, container=TASK_LIST) as opened:
        if not isinstance(opened, ActiveClient):
            raise ConnectorNotConfiguredError("tasks")
        try:
            task_list_id = await resolve_owner_container_id(
                client=opened.client,
                name=opened.preferred_name,
                owner_id=user.id,
                container=TASK_LIST,
            )
            result = await opened.client.list_tasks(
                task_list_id=task_list_id,
                max_results=settings.briefing_max_tasks_items * 4,
                show_completed=False,
                due_max=due_max,
            )
        except (TimeoutError, httpx.HTTPError, MaxRetriesExceededError) as exc:
            cause = getattr(exc, "last_error", None) or exc
            raise ConnectorAccessError("tasks", _classify_http_error(cause), str(exc)) from exc

    raw_items = result.get("items", []) or []
    items = [item for task in raw_items if (item := _task_to_item(task, today_local)) is not None]
    # Overdue first (oldest due first), then due ascending; undated last.
    items.sort(key=lambda t: (t.days_until_due is None, t.days_until_due or 0))
    items = items[: settings.briefing_max_tasks_items]
    return TasksData(items=items, overdue_count=sum(1 for t in items if t.overdue))


async def fetch_documents(
    *, user: User, user_tz: ZoneInfo, language: str | None = None
) -> DocumentsData:
    """Fetch the user's most recently modified Google Drive files.

    Drive-only source (2026-07-22 arbitration) — there is no multi-provider
    "file" functional category today; same single-provider stance as the
    birthdays fetch. ``modified_local`` is pre-formatted with the profile
    timezone + language (reminders doctrine).

    Raises:
        ConnectorNotConfiguredError: if Google Drive is not connected.
        ConnectorAccessError: on HTTP/network failure.
    """
    from src.domains.briefing.formatters import _format_trigger_at_local

    # Read in a session of its own, closed before Drive is called; the client
    # refreshes its token through a detached service (ADR-304) — it used to
    # outlive the session it had borrowed.
    connectors = DetachedConnectorService()
    async with connectors.unit_of_work() as service:
        credentials = await service.get_connector_credentials(user.id, ConnectorType.GOOGLE_DRIVE)
    if not credentials:
        raise ConnectorNotConfiguredError("drive")
    client = GoogleDriveClient(user.id, credentials, connectors)

    try:
        # Empty query + files_only → all non-trashed files, modifiedTime desc.
        result = await client.search_files(
            query="",
            max_results=settings.briefing_max_documents_items,
            fields=["id", "name", "mimeType", "modifiedTime", "webViewLink"],
        )
    except (TimeoutError, httpx.HTTPError, MaxRetriesExceededError) as exc:
        cause = getattr(exc, "last_error", None) or exc
        raise ConnectorAccessError("drive", _classify_http_error(cause), str(exc)) from exc
    finally:
        await client.close()

    items: list[DocumentItem] = []
    for f in (result.get("files", []) or [])[: settings.briefing_max_documents_items]:
        modified_local = "?"
        raw_modified = f.get("modifiedTime")
        if raw_modified:
            try:
                modified_dt = datetime.fromisoformat(str(raw_modified).replace("Z", "+00:00"))
                modified_local = _format_trigger_at_local(modified_dt, user_tz, language)
            except ValueError, TypeError:
                # Unparseable Drive timestamp — the '?' placeholder renders.
                logger.debug("briefing_document_modified_unparseable")
        items.append(
            DocumentItem(
                name=f.get("name") or "Untitled",
                modified_local=modified_local,
                web_view_link=f.get("webViewLink"),
                mime_type=f.get("mimeType"),
            )
        )
    return DocumentsData(items=items)


def _soonest_upcoming(
    actions: Sequence[ScheduledAction], now: datetime
) -> tuple[ScheduledAction, datetime] | None:
    """The next routine to fire, with the instant it fires at.

    The instant travels WITH the row rather than being read back from it:
    ``next_trigger_at`` is nullable since the recurrence rework (NULL = the
    series is over), and a filter narrows a VALUE, never an attribute — so
    ``min(..., key=lambda a: a.next_trigger_at)`` would still be typed
    ``datetime | None`` and would compare against None on an unlucky row.

    Args:
        actions: The account's routines, paused ones included.
        now: Reference instant (UTC).

    Returns:
        The soonest enabled routine and its instant, or ``None`` when none is
        armed.
    """
    dated = [
        (action, action.next_trigger_at)
        for action in actions
        if action.is_enabled
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
