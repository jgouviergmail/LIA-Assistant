"""A reply and a forward carry files and chosen copies, on the three providers (ADR-369, lot 7).

Gmail keeps a reply in its thread only if it says so: a file takes the upload door, whose bare
form holds a message and nothing else, so a reply with a file goes through its multipart form, the
thread beside the message. Graph carries files on the reply's own ``message``. iCloud builds the
message, as for a new one. A copy the person chose replaces the ones computed; an empty one means
nobody is copied, and nothing said keeps what the provider would have done.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.message import Message
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.constants import GOOGLE_GMAIL_UPLOAD_BASE_URL
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.email_compose import reply_recipients
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = pytest.mark.unit

FILE = OutgoingAttachment("report.pdf", "application/pdf", b"%PDF-1.7")
GRAPH = "https://graph.microsoft.com/v1.0"
GMAIL_ORIGINAL = {
    "id": "m1",
    "threadId": "t1",
    "labelIds": ["INBOX"],
    "payload": {
        "headers": [
            {"name": "From", "value": "bob@example.com"},
            {"name": "To", "value": "me@example.com, ann@example.com"},
            {"name": "Cc", "value": "carl@example.com"},
            {"name": "Subject", "value": "Budget"},
            {"name": "Message-ID", "value": "<m1@example.com>"},
        ],
        "mimeType": "text/plain",
        "body": {"data": "aGVsbG8="},
    },
}


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(202 if "graph" in str(request.url) else 200, json={"id": "sent"})


async def _through(client: Any, call: Callable[[], Any], **patched: Any) -> _Recorder:
    recorder = _Recorder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch.object(client, "get_message", AsyncMock(return_value=GMAIL_ORIGINAL)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await call()
    return recorder


def _rfc822_of(content: bytes) -> tuple[dict[str, Any], Message]:
    """The metadata and the message of a ``multipart/related`` upload."""
    boundary = content.split(b"\r\n", 1)[0]
    parts = [part for part in content.split(boundary) if part.strip(b"-\r\n")]
    metadata = json.loads(parts[0].split(b"\r\n\r\n", 1)[1])
    return metadata, message_from_bytes(parts[1].split(b"\r\n\r\n", 1)[1])


def _filenames(message: Message) -> list[str | None]:
    return [part.get_filename() for part in message.walk() if part.get_filename()]


class TestReplyRecipients:
    def test_a_chosen_copy_replaces_the_computed_ones(self) -> None:
        to, cc = reply_recipients(
            "bob@x.org",
            "me@x.org",
            "carl@x.org",
            own_address="me@x.org",
            reply_all=True,
            override_cc="dora@x.org",
        )

        assert to == "bob@x.org"
        assert cc == "dora@x.org"

    def test_an_empty_copy_copies_nobody(self) -> None:
        _to, cc = reply_recipients(
            "bob@x.org",
            "me@x.org",
            "carl@x.org",
            own_address="me@x.org",
            reply_all=True,
            override_cc="",
        )

        assert cc == ""

    def test_nothing_said_keeps_the_computed_ones(self) -> None:
        _to, cc = reply_recipients(
            "bob@x.org", "me@x.org", "carl@x.org", own_address="me@x.org", reply_all=True
        )

        assert cc == "carl@x.org"


class TestGmail:
    @pytest.fixture
    def client(self) -> GoogleGmailClient:
        return GoogleGmailClient(uuid4(), _credentials(), MagicMock())

    async def test_a_reply_with_a_file_stays_in_its_thread(self, client: GoogleGmailClient) -> None:
        recorder = await _through(
            client, lambda: client.reply_email("m1", "Hi", attachments=[FILE])
        )

        request = recorder.requests[-1]
        assert str(request.url).startswith(f"{GOOGLE_GMAIL_UPLOAD_BASE_URL}/users/me/messages/send")
        assert "uploadType=multipart" in str(request.url)
        assert request.headers["content-type"].startswith("multipart/related")
        metadata, message = _rfc822_of(request.content)
        assert metadata == {"threadId": "t1"}
        assert _filenames(message) == ["report.pdf"]
        assert message["In-Reply-To"] == "<m1@example.com>"
        assert message["To"] == "bob@example.com"

    async def test_a_reply_with_no_file_leaves_as_before(self, client: GoogleGmailClient) -> None:
        recorder = await _through(client, lambda: client.reply_email("m1", "Hi"))

        body = json.loads(recorder.requests[-1].content)
        assert body["threadId"] == "t1"
        assert "raw" in body

    async def test_a_chosen_copy_reaches_the_message(self, client: GoogleGmailClient) -> None:
        recorder = await _through(
            client,
            lambda: client.reply_email("m1", "Hi", cc="dora@example.com", attachments=[FILE]),
        )

        _metadata, message = _rfc822_of(recorder.requests[-1].content)
        assert message["Cc"] == "dora@example.com"

    async def test_a_forward_carries_the_person_s_files_too(
        self, client: GoogleGmailClient
    ) -> None:
        recorder = await _through(
            client,
            lambda: client.forward_email(
                "m1", "ann@example.com", include_attachments=False, attachments=[FILE]
            ),
        )

        request = recorder.requests[-1]
        assert "uploadType=media" in str(request.url)
        assert _filenames(message_from_bytes(request.content)) == ["report.pdf"]


def _html_of(message: Message) -> str:
    for part in message.walk():
        if part.get_content_type() == "text/html":
            return str(part.get_payload(decode=True).decode("utf-8"))
    raise AssertionError("no HTML part")


class TestFormattedAnswers:
    """A formatted answer keeps the message it answers, quoted as the same rule quotes it."""

    ORIGINAL = {
        "id": "m1",
        "from": "Bob <bob@example.com>",
        "to": "me@example.com",
        "subject": "Budget",
        "body": "Hello <there>",
        "date": "Mon, 2 Nov 2026 09:00:00 +0000",
    }

    async def test_gmail_quotes_a_formatted_reply(self) -> None:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())

        recorder = await _through(
            client, lambda: client.reply_email("m1", "<b>Hi</b>", is_html=True, attachments=[FILE])
        )

        _metadata, message = _rfc822_of(recorder.requests[-1].content)
        html = _html_of(message)
        assert html.startswith("<b>Hi</b>")
        assert "<blockquote>" in html

    async def _outlook(self, call: Callable[[MicrosoftOutlookClient], Any]) -> dict[str, Any]:
        client = MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())
        recorder = _Recorder()
        async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
            client._http_client = http
            with (
                patch.object(client, "_rate_limit", AsyncMock()),
                patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
                patch.object(client, "get_message", AsyncMock(return_value=self.ORIGINAL)),
            ):
                await call(client)
        return json.loads(recorder.requests[-1].content)

    async def test_graph_takes_a_formatted_reply_on_its_message_with_no_comment(self) -> None:
        body = await self._outlook(lambda c: c.reply_email("m1", "<b>Hi</b>", is_html=True))

        assert "comment" not in body
        written = body["message"]["body"]
        assert written["contentType"] == "HTML"
        assert written["content"].startswith("<b>Hi</b>")
        assert "Hello &lt;there&gt;" in written["content"]

    async def test_graph_forwards_formatted_words_above_the_original(self) -> None:
        body = await self._outlook(
            lambda c: c.forward_email("m1", "ann@example.com", body="<b>Fyi</b>", is_html=True)
        )

        assert "comment" not in body
        written = body["message"]["body"]
        assert written["contentType"] == "HTML"
        assert written["content"].startswith("<b>Fyi</b>")
        assert "Hello &lt;there&gt;" in written["content"]

    async def test_graph_keeps_a_plain_reply_on_its_comment(self) -> None:
        body = await self._outlook(lambda c: c.reply_email("m1", "Hi"))

        assert body == {"comment": "Hi"}


class TestGmailAlias:
    """The address a message leaves from, the one header every road of Gmail stamps."""

    @pytest.fixture
    def client(self) -> GoogleGmailClient:
        instance = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        instance.send_from("Ana <alias@example.com>")
        return instance

    async def test_a_message_of_words_leaves_from_it(self, client: GoogleGmailClient) -> None:
        recorder = await _through(client, lambda: client.send_email("a@example.com", "S", "B"))

        raw = json.loads(recorder.requests[-1].content)["raw"]
        message = message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        assert message["From"] == "Ana <alias@example.com>"

    async def test_a_message_with_a_file_leaves_from_it(self, client: GoogleGmailClient) -> None:
        recorder = await _through(
            client, lambda: client.send_email("a@example.com", "S", "B", attachments=[FILE])
        )

        assert message_from_bytes(recorder.requests[-1].content)["From"] == (
            "Ana <alias@example.com>"
        )

    async def test_a_reply_in_its_thread_leaves_from_it(self, client: GoogleGmailClient) -> None:
        recorder = await _through(
            client, lambda: client.reply_email("m1", "Hi", attachments=[FILE])
        )

        _metadata, message = _rfc822_of(recorder.requests[-1].content)
        assert message["From"] == "Ana <alias@example.com>"

    async def test_no_alias_chosen_names_no_sender(self) -> None:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())

        recorder = await _through(
            client, lambda: client.send_email("a@example.com", "S", "B", attachments=[FILE])
        )

        assert message_from_bytes(recorder.requests[-1].content)["From"] is None


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    async def test_a_reply_carries_its_files_on_its_message(
        self, client: MicrosoftOutlookClient
    ) -> None:
        recorder = await _through(
            client, lambda: client.reply_email("m1", "Hi", attachments=[FILE])
        )

        request = recorder.requests[-1]
        assert str(request.url) == f"{GRAPH}/me/messages/m1/reply"
        body = json.loads(request.content)
        assert body["comment"] == "Hi"
        assert [item["name"] for item in body["message"]["attachments"]] == ["report.pdf"]

    async def test_a_reply_with_nothing_more_names_no_message(
        self, client: MicrosoftOutlookClient
    ) -> None:
        recorder = await _through(client, lambda: client.reply_email("m1", "Hi"))

        assert json.loads(recorder.requests[-1].content) == {"comment": "Hi"}

    async def test_a_chosen_copy_replaces_graph_s(self, client: MicrosoftOutlookClient) -> None:
        recorder = await _through(
            client, lambda: client.reply_email("m1", "Hi", reply_all=True, cc="dora@example.com")
        )

        body = json.loads(recorder.requests[-1].content)
        addresses = [item["emailAddress"]["address"] for item in body["message"]["ccRecipients"]]
        assert addresses == ["dora@example.com"]

    async def test_an_empty_copy_copies_nobody(self, client: MicrosoftOutlookClient) -> None:
        recorder = await _through(
            client, lambda: client.reply_email("m1", "Hi", reply_all=True, cc="")
        )

        assert json.loads(recorder.requests[-1].content)["message"]["ccRecipients"] == []

    async def test_a_forward_carries_its_files_on_its_message(
        self, client: MicrosoftOutlookClient
    ) -> None:
        recorder = await _through(
            client, lambda: client.forward_email("m1", "ann@example.com", attachments=[FILE])
        )

        body = json.loads(recorder.requests[-1].content)
        assert [item["name"] for item in body["message"]["attachments"]] == ["report.pdf"]
        assert body["toRecipients"][0]["emailAddress"]["address"] == "ann@example.com"

    async def test_a_forward_s_copies_ride_on_its_message(
        self, client: MicrosoftOutlookClient
    ) -> None:
        # Measured on a real mailbox: beside ``toRecipients``, Graph answers 202 and
        # copies nobody. Only the message's own field reaches the copies.
        recorder = await _through(
            client, lambda: client.forward_email("m1", "ann@example.com", cc="dora@example.com")
        )

        body = json.loads(recorder.requests[-1].content)
        assert "ccRecipients" not in body
        addresses = [item["emailAddress"]["address"] for item in body["message"]["ccRecipients"]]
        assert addresses == ["dora@example.com"]


class TestApple:
    ORIGINAL = {
        "from": "bob@example.com",
        "to": "me@icloud.com, ann@example.com",
        "cc": "carl@example.com",
        "subject": "Budget",
        "body": "Hello",
        "rfc_message_id": "<m1@example.com>",
    }

    @pytest.fixture
    def client(self) -> AppleEmailClient:
        return AppleEmailClient(
            uuid4(),
            AppleCredentials(apple_id="me@icloud.com", app_password="test-password"),
            MagicMock(),
        )

    async def _sent(self, client: AppleEmailClient, call: Callable[[], Any]) -> Any:
        captured: dict[str, Any] = {}

        async def smtp(recipients: Any, message: Any) -> None:
            captured["message"] = message

        with (
            patch.object(client, "get_message", AsyncMock(return_value=self.ORIGINAL)),
            patch.object(
                client,
                "_original_with_files",
                AsyncMock(return_value=(self.ORIGINAL, [])),
            ),
            patch.object(client, "_smtp_send", AsyncMock(side_effect=smtp)),
        ):
            await call()
        return captured["message"]

    async def test_a_reply_carries_its_files(self, client: AppleEmailClient) -> None:
        message = await self._sent(
            client,
            lambda: client._reply_email_impl("42", "Hi", False, False, attachments=[FILE]),
        )

        assert _filenames(message) == ["report.pdf"]
        assert message["In-Reply-To"] == "<m1@example.com>"

    async def test_a_chosen_copy_replaces_the_computed_ones(self, client: AppleEmailClient) -> None:
        message = await self._sent(
            client, lambda: client._reply_email_impl("42", "Hi", True, False, cc="dora@example.com")
        )

        assert message["Cc"] == "dora@example.com"

    async def test_an_empty_copy_copies_nobody(self, client: AppleEmailClient) -> None:
        message = await self._sent(
            client, lambda: client._reply_email_impl("42", "Hi", True, False, cc="")
        )

        assert message["Cc"] is None

    async def test_a_forward_carries_the_person_s_files_too(self, client: AppleEmailClient) -> None:
        message = await self._sent(
            client,
            lambda: client._forward_email_impl(
                "42", "ann@example.com", None, None, False, False, attachments=[FILE]
            ),
        )

        assert _filenames(message) == ["report.pdf"]
