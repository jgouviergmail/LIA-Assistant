"""Unit tests for MicrosoftCalendarClient OData query building.

Regression coverage for the 2026-07 codebase audit (wave 1):
- The free-text ``query`` was interpolated into the OData ``$filter`` string
  without escaping single quotes, so any apostrophe (e.g. "l'anniversaire")
  produced a malformed filter and a Graph API 400 error.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.microsoft_calendar_client import (
    MicrosoftCalendarClient,
)


@pytest.fixture
def client():
    """MicrosoftCalendarClient with mocked credentials and service (no network)."""
    return MicrosoftCalendarClient(
        user_id=uuid4(),
        credentials=MagicMock(),
        connector_service=MagicMock(),
    )


@pytest.mark.unit
async def test_list_events_escapes_apostrophe_in_odata_filter(client):
    """A query containing an apostrophe must double it in the OData literal."""
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": []})
    ) as make_request:
        await client.list_events(query="l'anniversaire")

    params = make_request.await_args.args[2]
    assert params["$filter"] == "contains(subject, 'l''anniversaire')"


@pytest.mark.unit
async def test_list_events_plain_query_filter_unchanged(client):
    """A query without apostrophes keeps the same filter as before."""
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": []})
    ) as make_request:
        await client.list_events(query="standup")

    params = make_request.await_args.args[2]
    assert params["$filter"] == "contains(subject, 'standup')"
