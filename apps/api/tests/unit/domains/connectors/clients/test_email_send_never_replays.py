"""A lost acknowledgement cannot replay a non-idempotent mail send (ADR-344)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = pytest.mark.unit

_ORIGINAL = {
    "id": "m1",
    "threadId": "t1",
    "payload": {
        "headers": [
            {"name": "From", "value": "bob@example.com"},
            {"name": "To", "value": "me@example.com"},
            {"name": "Subject", "value": "S"},
        ]
    },
}


@pytest.mark.parametrize("provider", [GoogleGmailClient, MicrosoftOutlookClient])
@pytest.mark.parametrize(
    "action", ["send", "send_with_file", "send_legacy_false", "reply", "forward"]
)
async def test_oauth_sends_make_one_http_attempt_when_the_provider_loses_its_answer(
    provider, action: str
) -> None:
    client = provider(
        uuid4(),
        ConnectorCredentials(
            access_token="test-token",
            refresh_token="test-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        MagicMock(),
    )
    attempts = []

    def lost_acknowledgement(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ReadTimeout(
            "provider accepted the send but its answer was lost", request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(lost_acknowledgement)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch.object(client, "get_message", AsyncMock(return_value=_ORIGINAL)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            with pytest.raises(Exception):
                if action == "send":
                    await client.send_email("bob@example.com", "S", "B")
                elif action == "send_with_file":
                    await client.send_email(
                        "bob@example.com",
                        "S",
                        "B",
                        attachments=[OutgoingAttachment("file.md", "text/markdown", b"facts")],
                    )
                elif action == "send_legacy_false":
                    await client.send_email("bob@example.com", "S", "B", single_attempt=False)
                elif action == "reply":
                    await client.reply_email("m1", "B")
                else:
                    await client.forward_email("m1", "bob@example.com", include_attachments=False)

    assert len(attempts) == 1
    assert attempts[0].method == "POST"


@pytest.mark.parametrize("action", ["send", "reply", "forward"])
async def test_smtp_sends_do_not_repeat_an_operation_after_an_uncertain_acknowledgement(
    action: str,
) -> None:
    client = AppleEmailClient(
        uuid4(),
        AppleCredentials(apple_id="me@icloud.com", app_password="test-password"),
        MagicMock(),
    )
    effect = AsyncMock(side_effect=TimeoutError("send accepted but acknowledgement lost"))
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch.object(client, f"_{action}_email_impl", effect),
        patch("asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(TimeoutError):
            if action == "send":
                await client.send_email("bob@example.com", "S", "B")
            elif action == "reply":
                await client.reply_email("m1", "B")
            else:
                await client.forward_email("m1", "bob@example.com")

    assert effect.await_count == 1
