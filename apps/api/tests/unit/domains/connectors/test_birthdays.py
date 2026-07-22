"""Tests for the shared birthdays module (P7, interdomain program Lot 1).

The birthday fetch/computation logic moved from ``briefing`` to a neutral
``connectors`` home so the heartbeat can consume it WITHOUT importing the
briefing domain (briefing already imports ``heartbeat.geocoding`` — a
heartbeat→briefing edge would create a domain import cycle, forbidden by
the release contract).
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.connectors.birthdays import (
    BirthdayFetchError,
    BirthdayItem,
    fetch_upcoming_birthdays,
    upcoming_birthdays_from_connections,
)


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


@pytest.mark.unit
class TestFetchUpcomingBirthdays:
    """Provider fetch: silent None when not configured, typed error on failure."""

    async def test_returns_none_when_connector_not_configured(self):
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=None)

        with (
            patch("src.domains.connectors.birthdays.get_db_context") as db_ctx,
            patch(
                "src.domains.connectors.birthdays.ConnectorService",
                return_value=service,
            ),
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_upcoming_birthdays(
                uuid4(),
                ZoneInfo("Europe/Paris"),
                horizon_days=1,
                max_items=5,
            )

        assert result is None

    async def test_http_error_raises_typed_fetch_error(self):
        import httpx

        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        client = MagicMock()
        client.close = AsyncMock()
        client._make_request = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with (
            patch("src.domains.connectors.birthdays.get_db_context") as db_ctx,
            patch(
                "src.domains.connectors.birthdays.ConnectorService",
                return_value=service,
            ),
            patch(
                "src.domains.connectors.birthdays.GooglePeopleClient",
                return_value=client,
            ),
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(BirthdayFetchError):
                await fetch_upcoming_birthdays(
                    uuid4(),
                    ZoneInfo("Europe/Paris"),
                    horizon_days=1,
                    max_items=5,
                )

    async def test_fetch_computes_items_in_user_local_frame(self):
        """Connections are scanned then computed against the USER's local date."""
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        client = MagicMock()
        client.close = AsyncMock()
        client._make_request = AsyncMock(return_value={"connections": [_connection("Zoé", 7, 23)]})

        with (
            patch("src.domains.connectors.birthdays.get_db_context") as db_ctx,
            patch(
                "src.domains.connectors.birthdays.ConnectorService",
                return_value=service,
            ),
            patch(
                "src.domains.connectors.birthdays.GooglePeopleClient",
                return_value=client,
            ),
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_upcoming_birthdays(
                uuid4(),
                ZoneInfo("Europe/Paris"),
                horizon_days=400,
                max_items=5,
            )

        assert result is not None
        assert [i.contact_name for i in result] == ["Zoé"]
        assert isinstance(result[0], BirthdayItem)
        # Single page → exactly one paginated call
        assert client._make_request.await_count == 1

    async def test_client_transport_closed_on_success_and_on_error(self):
        """The People client owns an httpx transport: it must be closed on
        the success path AND when the scan raises (systemic rule)."""
        import httpx

        for side_effect, expectation in (
            (None, None),
            (httpx.ConnectError("boom"), BirthdayFetchError),
        ):
            service = MagicMock()
            service.get_connector_credentials = AsyncMock(return_value=MagicMock())
            client = MagicMock()
            client.close = AsyncMock()
            if side_effect is None:
                client._make_request = AsyncMock(return_value={"connections": []})
            else:
                client._make_request = AsyncMock(side_effect=side_effect)

            with (
                patch("src.domains.connectors.birthdays.get_db_context") as db_ctx,
                patch(
                    "src.domains.connectors.birthdays.ConnectorService",
                    return_value=service,
                ),
                patch(
                    "src.domains.connectors.birthdays.GooglePeopleClient",
                    return_value=client,
                ),
            ):
                db_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                if expectation is None:
                    await fetch_upcoming_birthdays(
                        uuid4(), ZoneInfo("Europe/Paris"), horizon_days=1, max_items=5
                    )
                else:
                    with pytest.raises(expectation):
                        await fetch_upcoming_birthdays(
                            uuid4(), ZoneInfo("Europe/Paris"), horizon_days=1, max_items=5
                        )
            client.close.assert_awaited_once()


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
