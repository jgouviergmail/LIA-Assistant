"""Shared upcoming-birthdays fetch and computation (Google Contacts).

Extracted from the briefing domain (P7, interdomain program Lot 1) so the
heartbeat can consume birthdays WITHOUT importing briefing: ``briefing``
already imports ``heartbeat.geocoding``, so a heartbeat→briefing edge would
create a domain import cycle (forbidden by the release contract). This module
lives in ``connectors`` — the provider-coupled neutral home — and both
consumers import from here:

- ``briefing/fetchers.fetch_birthdays`` — thin wrapper translating the
  neutral outcomes into the briefing section-status exceptions.
- ``heartbeat/context_aggregator._fetch_birthdays`` — silent-None consumer
  with its own Redis cache.

The full-scan pagination intentionally bypasses ``apply_max_items_limit``
(hard cap 50) to use the People API native max page size: with > 50 contacts,
birthdays beyond the first page would never be inspected. See the original
briefing fetcher docstring (moved here verbatim in spirit).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from uuid import UUID
    from zoneinfo import ZoneInfo

from src.domains.connectors.clients.google_people_client import GooglePeopleClient

logger = structlog.get_logger(__name__)

# People API native max page size / pagination cap (moved from briefing
# constants — 5 × 1000 covers more contacts than any real address book).
BIRTHDAY_PAGE_SIZE = 1000
BIRTHDAY_PAGINATION_MAX_PAGES = 5


class BirthdayItem(BaseModel):
    """Upcoming birthday entry — pre-computed days_until + age."""

    model_config = ConfigDict(frozen=True)

    contact_name: str
    date_iso: str = Field(
        ...,
        description="ISO 8601 date: 'YYYY-MM-DD' if year known, '--MM-DD' otherwise",
    )
    days_until: int = Field(..., ge=0, description="Days from today to next occurrence")
    age_at_next: int | None = Field(
        None,
        description="Age the contact will turn at the next birthday. None when birth year unknown.",
    )


class BirthdayFetchError(Exception):
    """Typed failure while scanning contacts for birthdays.

    Carries a short machine ``reason`` (e.g. "timeout", "http_error") and the
    original detail so callers can translate it into their own error contract
    (the briefing wrapper maps it to ``ConnectorAccessError``).
    """

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def upcoming_birthdays_from_connections(
    connections: list[dict[str, Any]],
    *,
    horizon_days: int,
    max_items: int,
    today: date,
) -> list[BirthdayItem]:
    """Extract upcoming birthdays from People API connections.

    Google People birthday format::

        {"birthdays": [{"date": {"month": 3, "day": 15, "year": 1990}, ...}]}

    The ``year`` is optional — many users record month + day only.

    Args:
        connections: ``connections`` array from ``GooglePeopleClient.list_connections``.
        horizon_days: Look-ahead window from today (e.g. 14).
        max_items: Cap on the returned list size.
        today: Reference date, REQUIRED in the **user's local frame**
            (``now_in_timezone(user_tz).date()``) — a ``date.today()`` default
            would be the server's date, which marks yesterday's birthdays as
            "today" for users ahead of UTC (see ``fetch_upcoming_birthdays``).

    Returns:
        List of BirthdayItem sorted ascending by ``days_until``.
        Birthdays today have days_until=0.
    """
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


async def fetch_upcoming_birthdays(
    user_id: UUID,
    user_tz: ZoneInfo,
    *,
    horizon_days: int,
    max_items: int,
) -> list[BirthdayItem] | None:
    """Full-scan Google Contacts and compute upcoming birthdays.

    Opens its own DB session (background/fetcher context). Neutral outcome
    contract so every consumer maps it to its own semantics:

    Returns:
        - ``None`` when the Google Contacts connector is not configured.
        - The (possibly empty) computed list otherwise.

    Raises:
        BirthdayFetchError: On timeout or HTTP failure while scanning.
    """
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            user_id, ConnectorType.GOOGLE_CONTACTS
        )
        if not credentials:
            return None

        client = GooglePeopleClient(user_id, credentials, connector_service)
        all_connections: list[dict[str, Any]] = []
        page_token: str | None = None

        try:
            for _ in range(BIRTHDAY_PAGINATION_MAX_PAGES):
                params: dict[str, Any] = {
                    "personFields": "names,birthdays",
                    "pageSize": BIRTHDAY_PAGE_SIZE,
                }
                if page_token:
                    params["pageToken"] = page_token

                # Direct API call — bypasses apply_max_items_limit on purpose
                # (see module docstring for justification).
                response = await client._make_request(
                    "GET", "/people/me/connections", params=params
                )
                all_connections.extend(response.get("connections", []) or [])
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            else:
                logger.info(
                    "birthdays_pagination_cap_reached",
                    user_id=str(user_id),
                    pages=BIRTHDAY_PAGINATION_MAX_PAGES,
                    contacts=len(all_connections),
                )
        except TimeoutError as exc:
            raise BirthdayFetchError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise BirthdayFetchError("http_error", str(exc)) from exc
        finally:
            # Deterministic close of the per-instance httpx transport on every
            # path (same doctrine as briefing/fetchers.py weather).
            await client.close()

        logger.info(
            "birthdays_fetched",
            user_id=str(user_id),
            total_contacts=len(all_connections),
        )

    # `today` MUST be the user's local date (not the server's UTC date) — at
    # 01:00 in Paris (= 23:00 UTC the previous day), date.today() would still
    # return yesterday and an upcoming-birthday computed against it would mark
    # yesterday's birthday as "today" with days_until=0.
    return upcoming_birthdays_from_connections(
        all_connections,
        horizon_days=horizon_days,
        max_items=max_items,
        today=datetime.now(user_tz).date(),
    )


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
