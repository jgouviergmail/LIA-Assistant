"""What the connector health and listing tell the grouped « reconnect » button.

The health alert (a banner and a modal on every dashboard page) and the
settings list both offer « reconnect my Google services » once two of them
expired. The button needs three facts per row, and the server states each one
rather than letting a client guess: whether the grouped consent would accept
the row (``bulk_reconnect_provider``), the account it belongs to
(``oauth_grant_id``) and that account's address, for the dialog that asks
which account to use when two are known.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.schemas import ConnectorResponse
from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.unit


def _row(kind: ConnectorType, status: ConnectorStatus, **extra: object) -> Connector:
    now = datetime.now(UTC)
    row = Connector(
        id=uuid4(),
        user_id=uuid4(),
        connector_type=kind,
        status=status,
        scopes=[],
        credentials_encrypted="not-a-fernet-token",
        created_at=now,
        updated_at=now,
    )
    for name, value in extra.items():
        setattr(row, name, value)
    return row


async def _health(rows: list[Connector]) -> dict[ConnectorType, dict[str, object]]:
    service = ConnectorService(MagicMock())
    with patch.object(service.repository, "get_all_by_user", AsyncMock(return_value=rows)):
        response = await service.check_connector_health(uuid4())
    return {item.connector_type: item.model_dump() for item in response.connectors}


async def test_an_expired_google_row_names_its_provider_its_account_and_its_address() -> None:
    grant = uuid4()
    rows = [
        _row(
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorStatus.ERROR,
            oauth_grant_id=grant,
            connector_metadata={"oauth_account_email": "someone@example.org"},
        )
    ]

    item = (await _health(rows))[ConnectorType.GOOGLE_CALENDAR]

    assert item["bulk_reconnect_provider"] == "google"
    assert item["oauth_grant_id"] == grant
    assert item["oauth_account_email"] == "someone@example.org"


async def test_a_row_broken_only_by_its_credentials_is_not_offered_to_the_group() -> None:
    """Reported broken (it cannot be read) but still ACTIVE: the plan refuses it."""
    rows = [_row(ConnectorType.GOOGLE_DRIVE, ConnectorStatus.ACTIVE)]

    item = (await _health(rows))[ConnectorType.GOOGLE_DRIVE]

    assert item["health_status"] == "error"
    assert item["bulk_reconnect_provider"] is None


async def test_a_legacy_mailbox_row_and_an_apple_row_are_never_grouped() -> None:
    rows = [
        _row(ConnectorType.GMAIL, ConnectorStatus.ERROR),
        _row(ConnectorType.APPLE_CALENDAR, ConnectorStatus.ERROR),
    ]

    items = await _health(rows)

    assert items[ConnectorType.GMAIL]["bulk_reconnect_provider"] is None
    assert items[ConnectorType.APPLE_CALENDAR]["bulk_reconnect_provider"] is None
    assert items[ConnectorType.APPLE_CALENDAR]["oauth_account_email"] is None


@pytest.mark.parametrize(
    ("kind", "status", "expected"),
    [
        (ConnectorType.MICROSOFT_OUTLOOK, ConnectorStatus.ERROR, "microsoft"),
        (ConnectorType.MICROSOFT_OUTLOOK, ConnectorStatus.ACTIVE, None),
        (ConnectorType.GMAIL, ConnectorStatus.ERROR, None),
    ],
)
def test_the_settings_listing_carries_the_same_verdict(
    kind: ConnectorType, status: ConnectorStatus, expected: str | None
) -> None:
    response = ConnectorResponse.model_validate(_row(kind, status))

    assert response.bulk_reconnect_provider == expected
