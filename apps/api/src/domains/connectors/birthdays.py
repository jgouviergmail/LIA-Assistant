"""Shared upcoming-birthdays fetch and computation, from the active contacts provider.

Extracted from the briefing domain (P7, interdomain program Lot 1) so the
heartbeat can consume birthdays WITHOUT importing briefing: ``briefing``
already imports ``heartbeat.geocoding``, so a heartbeat→briefing edge would
create a domain import cycle (forbidden by the release contract). This module
lives in ``connectors`` — the provider-coupled neutral home — and both
consumers import from here:

- ``briefing/fetchers.fetch_birthdays`` — thin wrapper translating the
  neutral outcomes into the briefing section-status exceptions.
- ``heartbeat/context_sources.fetch_birthdays_context`` — silent-None consumer
  with its own Redis cache.

**Whichever provider holds the contacts** (2026-11-07): the book is the shared
directory (``clients/contact_directory``) of the account's ACTIVE contacts
provider — Google, Apple or Microsoft, each normalised to the People shape —
opened through the shared door (``open_active_client``, ADR-304: nothing held
while the provider answers, the transport closed on every path). It was a
Google-only scan; « Apple and Microsoft lack a birthday field » was never true
(vCard ``BDAY``, Graph ``birthday``). The book is read whole up to
``CONTACTS_BIRTHDAYS_DIRECTORY_MAX`` — never the agents' item ceiling, under
which birthdays past the first page would never be seen — and a cut is logged.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import CONTACTS_BIRTHDAYS_DIRECTORY_MAX
from src.core.exceptions import MaxRetriesExceededError
from src.domains.connectors.active_client import (
    ActiveClient,
    ClientUnavailable,
    open_active_client,
)

if TYPE_CHECKING:
    from uuid import UUID
    from zoneinfo import ZoneInfo

    from src.domains.connectors.clients.contact_directory import ContactDirectory

logger = structlog.get_logger(__name__)

#: The functional category whose active provider holds the book.
_CONTACTS_CATEGORY = "contacts"


class BirthdayItem(BaseModel):
    """Upcoming birthday entry — pre-computed days_until + age, and how to reach the person."""

    model_config = ConfigDict(frozen=True)

    contact_name: str = Field(..., description="The contact's display name")
    date_iso: str = Field(
        ...,
        description="ISO 8601 date: 'YYYY-MM-DD' if year known, '--MM-DD' otherwise",
    )
    days_until: int = Field(..., ge=0, description="Days from today to next occurrence")
    age_at_next: int | None = Field(
        None,
        description="Age the contact will turn at the next birthday. None when birth year unknown.",
    )
    contact_id: str | None = Field(
        None,
        description="The contact's id in its provider's book (People ``resourceName`` shape), "
        "which opens it in the Tools; None when the provider gave none.",
    )
    email: str | None = Field(None, description="The contact's first address, to write to them")
    phone: str | None = Field(None, description="The contact's first number, to call them")


class BirthdayFetchError(Exception):
    """Typed failure while reading the contacts for birthdays.

    Carries a short machine ``reason`` (``no_credentials``, ``timeout``,
    ``http_error``, ``retries_exhausted``) and the original detail so callers
    can translate it into their own error contract (the briefing wrapper maps
    it to ``ConnectorAccessError``); the original exception is its ``__cause__``.
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
    """Extract upcoming birthdays from People-shape persons.

    People birthday format (every provider's normaliser writes it)::

        {"birthdays": [{"date": {"month": 3, "day": 15, "year": 1990}, ...}]}

    The ``year`` is optional — many users record month + day only — and an
    unknown year written as 0 (Microsoft's normaliser) reads as none.

    Args:
        connections: People-shape persons (the contact directory's ``persons``).
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
                except ValueError, TypeError:
                    age_at_next = None
            else:
                date_iso = f"--{int(month):02d}-{int(day):02d}"
            resource = connection.get("resourceName")
            candidates.append(
                BirthdayItem(
                    contact_name=name,
                    date_iso=date_iso,
                    days_until=days_until,
                    age_at_next=age_at_next,
                    contact_id=resource if isinstance(resource, str) and resource else None,
                    email=_first_value(connection, "emailAddresses"),
                    phone=_first_value(connection, "phoneNumbers"),
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
    """Read the active contacts provider's book and compute upcoming birthdays.

    Neutral outcome contract so every consumer maps it to its own semantics.

    Args:
        user_id: Whose contacts.
        user_tz: The person's zone: « today » is their day, never the server's.
        horizon_days: Look-ahead window from today.
        max_items: Cap on the returned list size.

    Returns:
        ``None`` when the account has no contacts provider; the (possibly
        empty) computed list otherwise.

    Raises:
        BirthdayFetchError: When the provider's credentials cannot be read, or
            on timeout, HTTP failure or exhausted retries while reading.
    """
    async with open_active_client(_CONTACTS_CATEGORY, user_id) as opened:
        if opened is ClientUnavailable.NO_CREDENTIALS:
            raise BirthdayFetchError("no_credentials", "Credentials missing or refresh failed")
        if not isinstance(opened, ActiveClient):
            return None
        directory = await _read_book(opened.client)

    if directory.truncated:
        logger.info(
            "birthdays_directory_truncated",
            user_id=str(user_id),
            contacts=len(directory.persons),
            cap=CONTACTS_BIRTHDAYS_DIRECTORY_MAX,
        )
    logger.info(
        "birthdays_fetched",
        user_id=str(user_id),
        provider=opened.connector_type.value,
        total_contacts=len(directory.persons),
        from_cache=directory.from_cache,
    )

    # `today` MUST be the user's local date (not the server's UTC date) — at
    # 01:00 in Paris (= 23:00 UTC the previous day), date.today() would still
    # return yesterday and an upcoming-birthday computed against it would mark
    # yesterday's birthday as "today" with days_until=0.
    return upcoming_birthdays_from_connections(
        directory.persons,
        horizon_days=horizon_days,
        max_items=max_items,
        today=datetime.now(user_tz).date(),
    )


async def _read_book(client: Any) -> ContactDirectory:
    """The whole book under the birthdays cap, a failure typed with its cause kept."""
    try:
        directory: ContactDirectory = await client.list_email_directory(
            CONTACTS_BIRTHDAYS_DIRECTORY_MAX
        )
    except TimeoutError as exc:
        raise BirthdayFetchError("timeout", str(exc)) from exc
    except httpx.HTTPError as exc:
        raise BirthdayFetchError("http_error", str(exc)) from exc
    except MaxRetriesExceededError as exc:
        raise BirthdayFetchError("retries_exhausted", str(exc)) from exc
    return directory


def _first_value(person: dict[str, Any], field: str) -> str | None:
    """The first non-empty ``value`` of a People list field (an address, a number)."""
    for item in person.get(field) or []:
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_primary_name(connection: dict[str, Any]) -> str | None:
    """Return the contact's display name from a People-shape person.

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
