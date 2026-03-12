"""
Unit tests for provider_resolver.resolve_active_connector().

Tests the resolution logic for functional categories (email, calendar, contacts)
based on connector status and conflict handling.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.provider_resolver import resolve_active_connector

USER_ID = uuid4()


def _make_connector(
    connector_type: ConnectorType,
    status: ConnectorStatus = ConnectorStatus.ACTIVE,
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    """Create a mock connector with the required attributes."""
    return SimpleNamespace(
        connector_type=connector_type,
        status=status,
        updated_at=updated_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_service(connectors: list) -> AsyncMock:
    """Create a mock connector service returning the given connectors."""
    service = AsyncMock()
    service.get_user_connectors.return_value = SimpleNamespace(connectors=connectors)
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_connectors_returns_none():
    """When no connectors exist, resolve returns None."""
    service = _make_service([])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_google_active_returns_google():
    """When Google connector is ACTIVE, returns the Google type."""
    connector = _make_connector(ConnectorType.GOOGLE_GMAIL)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result == ConnectorType.GOOGLE_GMAIL


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apple_active_returns_apple():
    """When Apple connector is ACTIVE, returns the Apple type."""
    connector = _make_connector(ConnectorType.APPLE_EMAIL)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result == ConnectorType.APPLE_EMAIL


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apple_calendar_active_returns_apple_calendar():
    """When Apple Calendar connector is ACTIVE, returns Apple Calendar type."""
    connector = _make_connector(ConnectorType.APPLE_CALENDAR)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "calendar", service)

    assert result == ConnectorType.APPLE_CALENDAR


@pytest.mark.unit
@pytest.mark.asyncio
async def test_google_contacts_active_returns_google_contacts():
    """When Google Contacts connector is ACTIVE, returns Google Contacts type."""
    connector = _make_connector(ConnectorType.GOOGLE_CONTACTS)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "contacts", service)

    assert result == ConnectorType.GOOGLE_CONTACTS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_both_active_returns_most_recently_updated():
    """When both Google and Apple are ACTIVE (conflict), returns the most recently updated."""
    older = _make_connector(
        ConnectorType.GOOGLE_GMAIL,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = _make_connector(
        ConnectorType.APPLE_EMAIL,
        updated_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    service = _make_service([older, newer])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result == ConnectorType.APPLE_EMAIL


@pytest.mark.unit
@pytest.mark.asyncio
async def test_both_active_reverse_order():
    """Conflict resolution is independent of list order."""
    newer = _make_connector(
        ConnectorType.GOOGLE_CALENDAR,
        updated_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    older = _make_connector(
        ConnectorType.APPLE_CALENDAR,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # newer is first in list, but should still win by updated_at
    service = _make_service([newer, older])

    result = await resolve_active_connector(USER_ID, "calendar", service)

    assert result == ConnectorType.GOOGLE_CALENDAR


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inactive_connector_returns_none():
    """When the only connector is INACTIVE, returns None."""
    connector = _make_connector(ConnectorType.GOOGLE_GMAIL, status=ConnectorStatus.INACTIVE)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revoked_connector_returns_none():
    """When the only connector is REVOKED, returns None."""
    connector = _make_connector(ConnectorType.APPLE_CONTACTS, status=ConnectorStatus.REVOKED)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "contacts", service)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_connector_returns_none():
    """When the only connector is in ERROR status, returns None."""
    connector = _make_connector(ConnectorType.GOOGLE_GMAIL, status=ConnectorStatus.ERROR)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_category_returns_none():
    """When the category does not exist, returns None."""
    service = _make_service([])

    result = await resolve_active_connector(USER_ID, "nonexistent_category", service)

    assert result is None
    # Service should not even be called for unknown categories
    service.get_user_connectors.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_active_connector_in_different_category_ignored():
    """An ACTIVE connector from a different category is not returned."""
    # Google Calendar is ACTIVE but we query "email"
    connector = _make_connector(ConnectorType.GOOGLE_CALENDAR)
    service = _make_service([connector])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mixed_statuses_returns_active_only():
    """When one connector is INACTIVE and the other ACTIVE, returns the ACTIVE one."""
    inactive = _make_connector(ConnectorType.GOOGLE_GMAIL, status=ConnectorStatus.INACTIVE)
    active = _make_connector(ConnectorType.APPLE_EMAIL, status=ConnectorStatus.ACTIVE)
    service = _make_service([inactive, active])

    result = await resolve_active_connector(USER_ID, "email", service)

    assert result == ConnectorType.APPLE_EMAIL
