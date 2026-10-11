"""A native email send never retries an ambiguous transport side effect."""

import smtplib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.gmail_send_mixin import GmailSendMixin
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient

pytestmark = pytest.mark.unit


async def test_apple_native_send_performs_one_ambiguous_smtp_attempt(monkeypatch):
    client = object.__new__(AppleEmailClient)
    client.user_id = "controlled-user"
    client._rate_limit = AsyncMock()
    breaker = SimpleNamespace(
        check=AsyncMock(), record_failure=AsyncMock(), record_success=AsyncMock()
    )
    monkeypatch.setattr(client, "_get_circuit_breaker", lambda: breaker)
    sender = AsyncMock(side_effect=smtplib.SMTPServerDisconnected("Lost after send"))
    monkeypatch.setattr(client, "_send_email_impl", sender)
    with pytest.raises(smtplib.SMTPServerDisconnected):
        await client.send_email("recipient@example.test", "Subject", "Body", single_attempt=True)
    assert sender.await_count == 1
    breaker.record_failure.assert_awaited_once()


async def test_outlook_native_send_limits_the_actual_request_to_one_attempt():
    client = object.__new__(MicrosoftOutlookClient)
    client._make_request = AsyncMock(side_effect=OSError("Lost after send"))
    with pytest.raises(OSError):
        await client.send_email("recipient@example.test", "Subject", "Body", single_attempt=True)
    assert client._make_request.await_count == 1
    assert client._make_request.await_args.kwargs["max_retries"] == 1


@pytest.mark.parametrize("files", [False, True])
async def test_gmail_native_send_limits_both_send_doors_to_one_attempt(files):
    from email.message import EmailMessage

    host = SimpleNamespace(
        _make_request=AsyncMock(side_effect=OSError("Lost after send")),
        _encode_base64url=lambda value: value,
    )
    with pytest.raises(OSError):
        await GmailSendMixin._send_message(
            host, EmailMessage(), with_files=files, single_attempt=True
        )
    assert host._make_request.await_count == 1
    assert host._make_request.await_args.kwargs["max_retries"] == 1


@pytest.mark.parametrize("mismatch", [False, True])
async def test_original_email_share_port_passes_single_attempt_and_refuses_retargeting(
    monkeypatch, mismatch
):
    from contextlib import asynccontextmanager

    from src.core.exceptions import BaseAPIException
    from src.domains.connectors.models import ConnectorType
    from src.domains.email_share import service
    from src.infrastructure.email.outgoing import OutgoingAttachment

    attachment = OutgoingAttachment("answer.md", "text/markdown", b"exact approved bytes")
    actual = ConnectorType.MICROSOFT_OUTLOOK if mismatch else ConnectorType.GOOGLE_GMAIL
    client = SimpleNamespace(send_email=AsyncMock(return_value={"id": "controlled-ack"}))

    @asynccontextmanager
    async def opened(*args):
        yield SimpleNamespace(connector_type=actual, client=client)

    monkeypatch.setattr(service, "open_active_client", opened)
    prepared = service.PreparedShare(
        service.ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=1024),
        ["recipient@example.test"],
        "Subject",
        None,
        service.InlineFile(attachment),
        single_attempt=True,
    )
    if mismatch:
        with pytest.raises(BaseAPIException):
            await service._send_from_mailbox("controlled-user", prepared, attachment)
        client.send_email.assert_not_awaited()
    else:
        await service._send_from_mailbox("controlled-user", prepared, attachment)
        assert client.send_email.await_args.kwargs["single_attempt"] is True
