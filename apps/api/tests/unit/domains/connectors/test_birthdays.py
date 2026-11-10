"""Tests for the shared birthdays module (P7, interdomain program Lot 1).

The birthday fetch/computation logic moved from ``briefing`` to a neutral
``connectors`` home so the heartbeat can consume it WITHOUT importing the
briefing domain (briefing already imports ``heartbeat.geocoding`` — a
heartbeat→briefing edge would create a domain import cycle, forbidden by
the release contract).

Since 2026-11-07 the birthdays come from the ACTIVE contacts provider (Google,
Apple or Microsoft) through the shared directory, read whole through the shared
door — whose own tests hold the no-session and always-closed contract.
"""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.core.constants import CONTACTS_BIRTHDAYS_DIRECTORY_MAX
from src.core.exceptions import MaxRetriesExceededError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.birthdays import (
    BirthdayFetchError,
    BirthdayItem,
    fetch_upcoming_birthdays,
    upcoming_birthdays_from_connections,
)
from src.domains.connectors.clients.contact_directory import ContactDirectory
from src.domains.connectors.models import ConnectorType

PARIS = ZoneInfo("Europe/Paris")


def _connection(name: str, month: int, day: int, year: int | None = None) -> dict:
    """Build a People API connection payload with one birthday."""
    date_field: dict = {"month": month, "day": day}
    if year is not None:
        date_field["year"] = year
    return {
        "names": [{"displayName": name, "metadata": {"primary": True}}],
        "birthdays": [{"date": date_field}],
    }


@pytest.mark.unit
class TestUpcomingBirthdaysComputation:
    """The moved computation keeps its briefing-era semantics."""

    def test_birthday_today_has_days_until_zero(self):
        today = date(2026, 7, 22)
        items = upcoming_birthdays_from_connections(
            [_connection("Marie", 7, 22, 1990)],
            horizon_days=14,
            max_items=5,
            today=today,
        )
        assert len(items) == 1
        assert items[0].contact_name == "Marie"
        assert items[0].days_until == 0
        assert items[0].age_at_next == 36

    def test_horizon_filters_far_birthdays(self):
        today = date(2026, 7, 22)
        items = upcoming_birthdays_from_connections(
            [_connection("Paul", 12, 25)],
            horizon_days=14,
            max_items=5,
            today=today,
        )
        assert items == []

    def test_sorted_by_days_until(self):
        today = date(2026, 7, 22)
        items = upcoming_birthdays_from_connections(
            [_connection("B", 7, 30), _connection("A", 7, 23)],
            horizon_days=14,
            max_items=5,
            today=today,
        )
        assert [i.contact_name for i in items] == ["A", "B"]

    def test_a_birthday_names_its_contact_and_how_to_reach_them(self):
        """The card opens the contact, writes to them, calls them: it needs their id and ways."""
        person = {
            **_connection("Inès", 7, 23),
            "resourceName": "people/c42",
            "emailAddresses": [{"value": ""}, {"value": "ines@example.org"}],
            "phoneNumbers": [{"value": "+33 6 12 34 56 78"}],
        }

        [item] = upcoming_birthdays_from_connections(
            [person], horizon_days=14, max_items=5, today=date(2026, 7, 22)
        )

        assert (item.contact_id, item.email, item.phone) == (
            "people/c42",
            "ines@example.org",
            "+33 6 12 34 56 78",
        )

    def test_a_contact_with_no_way_to_reach_them_still_has_their_birthday(self):
        [item] = upcoming_birthdays_from_connections(
            [_connection("Hugo", 7, 23)], horizon_days=14, max_items=5, today=date(2026, 7, 22)
        )

        assert (item.contact_id, item.email, item.phone) == (None, None, None)

    def test_a_year_written_as_zero_is_an_unknown_year(self):
        """Microsoft's normaliser writes an unknown year as 0: no age, no year in the date."""
        [item] = upcoming_birthdays_from_connections(
            [_connection("Léa", 7, 23, 0)], horizon_days=14, max_items=5, today=date(2026, 7, 22)
        )

        assert (item.date_iso, item.age_at_next) == ("--07-23", None)


def _door(opened: object, asked: list[str] | None = None):
    """The shared door, yielding ``opened`` for the category it is asked."""

    @asynccontextmanager
    async def door(category, user_id, *, container=None, fresh=False):
        if asked is not None:
            asked.append(category)
        yield opened

    return door


def _active(client: object) -> ActiveClient:
    return ActiveClient(
        client=client, connector_type=ConnectorType.MICROSOFT_CONTACTS, preferred_name=None
    )


async def _fetch(**overrides) -> list[BirthdayItem] | None:
    return await fetch_upcoming_birthdays(
        uuid4(), PARIS, horizon_days=overrides.get("horizon_days", 400), max_items=5
    )


@pytest.mark.unit
class TestFetchUpcomingBirthdays:
    """The active provider's book: None when there is none, a typed error when it fails."""

    @pytest.mark.parametrize(
        "absent", [ClientUnavailable.NO_CONNECTOR, ClientUnavailable.NO_CLIENT]
    )
    async def test_no_contacts_provider_reads_as_not_configured(self, absent):
        with patch("src.domains.connectors.birthdays.open_active_client", _door(absent)):
            assert await _fetch() is None

    async def test_unreadable_credentials_are_a_failure_not_an_absence(self):
        """An active provider whose token cannot be read is « reconnect », never « connect »."""
        with patch(
            "src.domains.connectors.birthdays.open_active_client",
            _door(ClientUnavailable.NO_CREDENTIALS),
        ):
            with pytest.raises(BirthdayFetchError) as raised:
                await _fetch()

        assert raised.value.reason == "no_credentials"

    async def test_the_active_provider_book_is_read_whole_under_the_birthdays_cap(self):
        client = MagicMock()
        client.list_email_directory = AsyncMock(
            return_value=ContactDirectory(
                persons=[{**_connection("Zoé", 7, 23), "resourceName": "people/z"}],
                truncated=False,
                from_cache=False,
            )
        )
        asked: list[str] = []

        with patch(
            "src.domains.connectors.birthdays.open_active_client", _door(_active(client), asked)
        ):
            result = await _fetch()

        assert asked == ["contacts"]
        client.list_email_directory.assert_awaited_once_with(CONTACTS_BIRTHDAYS_DIRECTORY_MAX)
        assert result is not None
        assert [(item.contact_name, item.contact_id) for item in result] == [("Zoé", "people/z")]

    async def test_the_days_are_counted_in_the_person_s_own_day(self):
        """At 00:30 in Paris on the 23rd, a birthday on the 23rd is today, whatever UTC says."""
        client = MagicMock()
        client.list_email_directory = AsyncMock(
            return_value=ContactDirectory(
                persons=[_connection("Zoé", 7, 23)], truncated=False, from_cache=True
            )
        )

        class _Clock:
            @staticmethod
            def now(tz):
                from datetime import datetime

                return datetime(2026, 7, 23, 0, 30, tzinfo=tz)

        with (
            patch("src.domains.connectors.birthdays.open_active_client", _door(_active(client))),
            patch("src.domains.connectors.birthdays.datetime", _Clock),
        ):
            result = await _fetch(horizon_days=14)

        assert result is not None
        assert [item.days_until for item in result] == [0]

    @pytest.mark.parametrize(
        ("failure", "reason"),
        [
            (TimeoutError("slow"), "timeout"),
            (httpx.ConnectError("boom"), "http_error"),
            (MaxRetriesExceededError("list_email_directory", 3), "retries_exhausted"),
        ],
    )
    async def test_a_provider_failure_is_typed_and_keeps_its_cause(self, failure, reason):
        client = MagicMock()
        client.list_email_directory = AsyncMock(side_effect=failure)

        with patch("src.domains.connectors.birthdays.open_active_client", _door(_active(client))):
            with pytest.raises(BirthdayFetchError) as raised:
                await _fetch()

        assert raised.value.reason == reason
        assert raised.value.__cause__ is failure


@pytest.mark.unit
class TestBriefingReExports:
    """Briefing keeps its historical import surface (schemas + formatters)."""

    def test_briefing_schemas_reexports_birthday_item(self):
        from src.domains.briefing.schemas import BirthdayItem as BriefingBirthdayItem

        assert BriefingBirthdayItem is BirthdayItem

    def test_briefing_formatters_reexports_computation(self):
        from src.domains.briefing.formatters import (
            upcoming_birthdays_from_connections as briefing_fn,
        )

        assert briefing_fn is upcoming_birthdays_from_connections
