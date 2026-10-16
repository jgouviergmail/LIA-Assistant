"""A lost edit acknowledgement must not overwrite a later edit on a retry."""

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ExternalServiceError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("provider", [GoogleGmailClient, MicrosoftOutlookClient])
async def test_an_edit_does_not_replay_after_a_lost_acknowledgement(provider) -> None:
    client = provider(
        uuid4(),
        ConnectorCredentials(
            access_token="test-token",
            refresh_token="test-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        MagicMock(),
    )
    live = {
        "id": "m1",
        FIELD_MAILBOX_DRAFT_ID: "r-1",
        FIELD_MAILBOX_DRAFT_REVISION: "before",
        "changeKey": "before",
        "raw": base64.urlsafe_b64encode(b"Subject: Budget\n\nText").decode(),
    }
    attempts: list[httpx.Request] = []
    stored = {"subject": "Before"}

    def accepted_without_answer(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        stored["subject"] = "LIA edit"
        if len(attempts) == 1:
            stored["subject"] = "A later edit in the mailbox"
        raise httpx.ReadTimeout("accepted, answer lost", request=request)

    read_name = "_read_draft" if provider is GoogleGmailClient else "_live_draft"
    async with httpx.AsyncClient(transport=httpx.MockTransport(accepted_without_answer)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch.object(client, read_name, AsyncMock(return_value=live)),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(ExternalServiceError),
        ):
            await client.update_draft("r-1", subject="LIA edit", expected_revision="before")

    assert len(attempts) == 1
    assert stored["subject"] == "A later edit in the mailbox"
