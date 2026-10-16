"""The Gmail reply and forward a person SENDS, byte for byte (characterization).

Written before the composition left ``GoogleGmailClient`` to be shared with the
mailbox drafts (ADR-344): the sent message must stay exactly what it was — save
the one defect the move fixed, a reply to all that dropped every other
recipient of the original and copied the person on their own reply.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

ORIGINAL_TEXT = "Voici le budget révisé.\nMerci de valider."


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode("ascii")


def _original(*, with_file: bool = False, to: str = "me@example.com") -> dict[str, Any]:
    text_part = {"mimeType": "text/plain", "body": {"data": _b64(ORIGINAL_TEXT)}}
    payload: dict[str, Any] = {
        "headers": [
            {"name": "Subject", "value": "Budget 2027"},
            {"name": "From", "value": "Paul Durand <paul@example.com>"},
            {"name": "To", "value": to},
            {"name": "Cc", "value": "anne@example.com, Moi <me@example.com>"},
            {"name": "Date", "value": "Mon, 12 Oct 2026 10:00:00 +0200"},
            {"name": "Message-ID", "value": "<orig-1@mail.example.com>"},
        ],
    }
    if with_file:
        payload |= {
            "mimeType": "multipart/mixed",
            "parts": [
                text_part,
                {
                    "mimeType": "application/pdf",
                    "filename": "budget.pdf",
                    "body": {"attachmentId": "att-1", "size": 4},
                },
            ],
        }
    else:
        payload |= text_part
    return {"id": "orig-1", "threadId": "thread-1", "payload": payload}


@pytest.fixture
def client() -> GoogleGmailClient:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return GoogleGmailClient(uuid4(), credentials, MagicMock())


def _parse_raw(raw: str) -> EmailMessage:
    padded = raw + "=" * (-len(raw) % 4)
    return BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(padded)
    )


def _text(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    return str(body.get_content())


async def _sent(client: GoogleGmailClient, call: Any, original: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_request(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        if endpoint == "/users/me/profile":
            return {"emailAddress": "me@example.com"}
        captured.update(endpoint=endpoint, **kwargs)
        return {"id": "sent-1", "threadId": "thread-1"}

    with (
        patch.object(client, "get_message", AsyncMock(return_value=original)),
        patch.object(client, "get_attachment", AsyncMock(return_value=b"%PDF")),
        patch.object(client, "_make_request", side_effect=fake_request),
    ):
        await call()
    return captured


class TestReply:
    async def test_a_reply_uses_the_original_reply_to_header(
        self, client: GoogleGmailClient
    ) -> None:
        original = _original()
        original["payload"]["headers"].append(
            {"name": "Reply-To", "value": "Help <help@example.com>"}
        )
        captured = await _sent(client, lambda: client.reply_email("orig-1", "Ok"), original)

        assert _parse_raw(captured["json_data"]["raw"])["To"] == "Help <help@example.com>"

    async def test_a_reply_quotes_the_original_in_its_thread(
        self, client: GoogleGmailClient
    ) -> None:
        captured = await _sent(
            client, lambda: client.reply_email("orig-1", "Validé, merci !"), _original()
        )

        message = _parse_raw(captured["json_data"]["raw"])
        assert captured["json_data"]["threadId"] == "thread-1"
        assert message["To"] == "Paul Durand <paul@example.com>"
        assert message["Cc"] is None
        assert message["Subject"] == "Re: Budget 2027"
        assert message["In-Reply-To"] == "<orig-1@mail.example.com>"
        assert message["References"] == "<orig-1@mail.example.com>"
        assert _text(message) == (
            "Validé, merci !\n\n"
            "On Mon, 12 Oct 2026 10:00:00 +0200, Paul Durand <paul@example.com> wrote:\n"
            "> Voici le budget révisé.\n"
            "> Merci de valider."
        )

    async def test_a_reply_all_answers_every_other_recipient_but_the_person(
        self, client: GoogleGmailClient
    ) -> None:
        original = _original(to="me@example.com, Marie Exemple <marie@example.com>")
        captured = await _sent(
            client, lambda: client.reply_email("orig-1", "Ok", reply_all=True), original
        )

        message = _parse_raw(captured["json_data"]["raw"])
        assert message["To"] == "Paul Durand <paul@example.com>, Marie Exemple <marie@example.com>"
        assert message["Cc"] == "anne@example.com"

    async def test_a_recipient_override_replaces_the_sender(
        self, client: GoogleGmailClient
    ) -> None:
        captured = await _sent(
            client,
            lambda: client.reply_email("orig-1", "Ok", to="marie@example.com"),
            _original(),
        )

        message = _parse_raw(captured["json_data"]["raw"])
        assert message["To"] == "marie@example.com"
        assert message["Cc"] is None


class TestForward:
    @pytest.mark.parametrize("as_draft", [False, True])
    async def test_a_truncated_attachment_refuses_the_forward_before_any_write(
        self, client: GoogleGmailClient, as_draft: bool
    ) -> None:
        request = AsyncMock(side_effect=AssertionError("incomplete file was written"))
        with (
            patch.object(client, "get_message", AsyncMock(return_value=_original(with_file=True))),
            patch.object(client, "get_attachment", AsyncMock(return_value=b"%PD")),
            patch.object(client, "_make_request", request),
            pytest.raises(ConnectorAPIError),
        ):
            if as_draft:
                await client.create_forward_draft("orig-1", "marie@example.com")
            else:
                await client.forward_email("orig-1", "marie@example.com")
        request.assert_not_awaited()

    async def test_an_inline_file_is_carried_without_a_download_request(
        self, client: GoogleGmailClient
    ) -> None:
        original = _original(with_file=True)
        original["payload"]["parts"][1]["body"] = {"data": _b64("%PDF"), "size": 4}
        captured = await _sent(
            client, lambda: client.forward_email("orig-1", "marie@example.com"), original
        )
        message = BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(
            captured["content"]
        )
        assert [(p.get_filename(), p.get_content()) for p in message.iter_attachments()] == [
            ("budget.pdf", b"%PDF")
        ]

    @pytest.mark.parametrize("as_draft", [False, True])
    async def test_a_missing_attachment_refuses_the_forward_before_any_write(
        self, client: GoogleGmailClient, as_draft: bool
    ) -> None:
        request = AsyncMock(
            side_effect=AssertionError("write attempted before files were available")
        )
        with (
            patch.object(client, "get_message", AsyncMock(return_value=_original(with_file=True))),
            patch.object(client, "get_attachment", AsyncMock(side_effect=OSError("unavailable"))),
            patch.object(client, "_make_request", request),
        ):
            with pytest.raises(OSError, match="unavailable"):
                if as_draft:
                    await client.create_forward_draft("orig-1", "marie@example.com")
                else:
                    await client.forward_email("orig-1", "marie@example.com")

        request.assert_not_awaited()

    async def test_a_forward_carries_the_original_below_the_note(
        self, client: GoogleGmailClient
    ) -> None:
        captured = await _sent(
            client,
            lambda: client.forward_email(
                "orig-1", "marie@example.com", body="Pour info.", cc="bob@example.com"
            ),
            _original(),
        )

        message = _parse_raw(captured["json_data"]["raw"])
        assert "threadId" not in captured["json_data"]
        assert message["To"] == "marie@example.com"
        assert message["Cc"] == "bob@example.com"
        assert message["Subject"] == "Fwd: Budget 2027"
        assert _text(message) == (
            "Pour info.\n\n"
            "---------- Forwarded message ---------\n"
            "From: Paul Durand <paul@example.com>\n"
            "Date: Mon, 12 Oct 2026 10:00:00 +0200\n"
            "Subject: Budget 2027\n"
            "To: me@example.com\n\n"
            "Voici le budget révisé.\nMerci de valider."
        )

    async def test_a_forward_with_a_file_leaves_through_the_upload_uri(
        self, client: GoogleGmailClient
    ) -> None:
        captured = await _sent(
            client,
            lambda: client.forward_email("orig-1", "marie@example.com"),
            _original(with_file=True),
        )

        message = BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(
            captured["content"]
        )
        assert captured["params"] == {"uploadType": "media"}
        assert [(p.get_filename(), p.get_content()) for p in message.iter_attachments()] == [
            ("budget.pdf", b"%PDF")
        ]
        assert _text(message).startswith("\n\n---------- Forwarded message ---------\n")
