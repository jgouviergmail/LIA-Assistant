"""A message's HTML on the three mail providers — one display contract (ADR-369, D3).

The model reads the clean text (ADR-287); the person's own reader shows the
message as its author laid it out. ``get_message_html`` answers the message's
HTML body, or None when it carries none — then the text reader shows instead.
A file someone attached, even an ``.html`` one, is never the body, and neither
is a message forwarded as an attachment. Reading it marks nothing read.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage, Message
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import ImapMessageNotFoundError
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_HTML = "src.domains.connectors.clients.apple_mail_html"
HTML = "<html><body><p>Le budget est prêt.</p></body></html>"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def _drive(
    client: Any, answer: Callable[[httpx.Request], httpx.Response], call: Callable[[], Any]
) -> tuple[Any, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call(), seen


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _part(mime: str, data: bytes, *, charset: str = "utf-8", filename: str = "") -> dict[str, Any]:
    return {
        "mimeType": mime,
        "filename": filename,
        "headers": [{"name": "Content-Type", "value": f'{mime}; charset="{charset}"'}],
        "body": {"size": len(data), "data": _b64(data)},
    }


def _multipart(mime: str, *parts: dict[str, Any]) -> dict[str, Any]:
    return {"mimeType": mime, "filename": "", "headers": [], "body": {"size": 0}, "parts": parts}


class TestGmail:
    @pytest.fixture
    def client(self) -> Iterator[GoogleGmailClient]:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
        ):
            yield client

    async def _html(self, client: GoogleGmailClient, payload: dict[str, Any]) -> str | None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "m1", "threadId": "t1", "payload": payload})

        html, _seen = await _drive(client, answer, lambda: client.get_message_html("m1"))
        return html

    async def test_the_html_alternative_is_read_in_its_own_charset(
        self, client: GoogleGmailClient
    ) -> None:
        payload = _multipart(
            "multipart/alternative",
            _part("text/plain", "Le budget est prêt.".encode()),
            _part("text/html", HTML.encode("iso-8859-1"), charset="iso-8859-1"),
        )

        assert await self._html(client, payload) == HTML

    async def test_a_message_that_is_only_html(self, client: GoogleGmailClient) -> None:
        assert await self._html(client, _part("text/html", HTML.encode())) == HTML

    async def test_a_text_only_message_has_none(self, client: GoogleGmailClient) -> None:
        assert await self._html(client, _part("text/plain", b"Plain words.")) is None

    async def test_an_attached_html_file_is_not_the_body(self, client: GoogleGmailClient) -> None:
        payload = _multipart(
            "multipart/mixed",
            _part("text/plain", b"See the page attached."),
            _part("text/html", b"<p>a page someone saved</p>", filename="page.html"),
        )

        assert await self._html(client, payload) is None

    async def test_a_message_forwarded_as_an_attachment_is_not_the_body(
        self, client: GoogleGmailClient
    ) -> None:
        forwarded = _multipart("message/rfc822", _part("text/html", b"<p>the other message</p>"))
        payload = _multipart("multipart/mixed", _part("text/plain", b"FYI"), forwarded)

        assert await self._html(client, payload) is None

    async def test_an_html_part_too_large_to_travel_inline_is_read_by_its_handle(
        self, client: GoogleGmailClient
    ) -> None:
        data = HTML.encode()
        part = {
            "mimeType": "text/html",
            "filename": "",
            "headers": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}],
            "body": {"size": len(data), "attachmentId": "big1"},
        }
        payload = _multipart("multipart/alternative", _part("text/plain", b"text"), part)

        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/attachments/big1"):
                return httpx.Response(200, json={"size": len(data), "data": _b64(data)})
            return httpx.Response(200, json={"id": "m1", "payload": payload})

        html, seen = await _drive(client, answer, lambda: client.get_message_html("m1"))

        assert html == HTML
        assert [request.url.path for request in seen] == [
            "/gmail/v1/users/me/messages/m1",
            "/gmail/v1/users/me/messages/m1/attachments/big1",
        ]

    async def test_a_body_split_around_an_inline_image_is_joined_in_document_order(
        self, client: GoogleGmailClient
    ) -> None:
        image = {
            "mimeType": "image/png",
            "filename": "chart.png",
            "headers": [],
            "body": {"size": 3, "attachmentId": "img"},
        }
        payload = _multipart(
            "multipart/mixed",
            _part("text/html", b"<p>before</p>"),
            image,
            _part("text/html", b"<p>after</p>"),
        )

        assert await self._html(client, payload) == "<p>before</p><p>after</p>"

    async def test_an_empty_html_part_costs_the_others_nothing(
        self, client: GoogleGmailClient
    ) -> None:
        empty = {"mimeType": "text/html", "filename": "", "headers": [], "body": {"size": 0}}
        payload = _multipart("multipart/mixed", empty, _part("text/html", b"<p>kept</p>"))

        assert await self._html(client, payload) == "<p>kept</p>"

    async def test_an_unknown_charset_reads_as_utf8(self, client: GoogleGmailClient) -> None:
        payload = _part("text/html", HTML.encode(), charset="x-no-such-charset")

        assert await self._html(client, payload) == HTML


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    async def test_the_body_is_asked_for_as_html_and_only_the_body(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"body": {"contentType": "html", "content": HTML}})

        html, seen = await _drive(client, answer, lambda: client.get_message_html("AAMk/x="))

        assert html == HTML
        (request,) = seen
        assert request.url.raw_path.decode().startswith("/v1.0/me/messages/AAMk%2Fx%3D?")
        assert request.url.params["$select"] == "body"
        assert request.headers["Prefer"] == 'outlook.body-content-type="html"'

    @pytest.mark.parametrize(
        "body",
        [
            {"contentType": "text", "content": "Plain words."},
            {"contentType": "html", "content": ""},
        ],
    )
    async def test_a_body_still_answered_as_text_or_empty_has_none(
        self, client: MicrosoftOutlookClient, body: dict[str, str]
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"body": body})

        html, _seen = await _drive(client, answer, lambda: client.get_message_html("o1"))

        assert html is None


def _headed(message: Message, subject: str) -> Message:
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    return message


def _mail(subject: str, *, html: str | None, charset: str = "utf-8") -> EmailMessage:
    message = EmailMessage()
    message.set_content(f"{subject} body.")
    if html is not None:
        message.add_alternative(html.encode(charset), "text", "html", params={"charset": charset})
    _headed(message, subject)
    return message


def _segmented(subject: str) -> Message:
    """A body split around an inline image, the way Apple Mail writes one."""
    message = MIMEMultipart("mixed")
    message.attach(MIMEText("<p>before</p>", "html"))
    image = MIMEImage(b"\x89PNG\r\n\x1a\n", "png")
    image.add_header("Content-Disposition", "inline", filename="chart.png")
    message.attach(image)
    message.attach(MIMEText("<p>after</p>", "html"))
    return _headed(message, subject)


def _with_files(subject: str) -> EmailMessage:
    """A text body, an ``.html`` page attached, and a message forwarded as an attachment."""
    message = _mail(subject, html=None)
    message.add_attachment(b"<p>a saved page</p>", "text", "html", filename="page.html")
    message.add_attachment(_mail("Forwarded", html="<p>another message</p>"))
    return message


class TestImap:
    @pytest.fixture
    def imap(self) -> FakeImap:
        imap = FakeImap()
        imap.put("INBOX", _mail("Html mail", html=HTML, charset="iso-8859-1"), uid="101")
        imap.put("INBOX", _mail("Text mail", html=None), uid="102")
        imap.put("INBOX", _segmented("Segmented mail"), uid="103")
        imap.put("INBOX", _with_files("Mail with files"), uid="104")
        return imap

    @pytest.fixture
    def client(self, imap: FakeImap) -> Iterator[AppleEmailClient]:
        instance = AppleEmailClient(
            user_id=uuid4(),
            credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
            connector_service=MagicMock(),
        )
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
        with (
            patch(f"{APPLE}.MailBox", imap),
            patch(f"{APPLE_HTML}.MailBox", imap),
            patch(f"{APPLE}.get_redis_session", AsyncMock(side_effect=ConnectionError("none"))),
            patch.object(instance, "_rate_limit", AsyncMock()),
            patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            yield instance

    async def _id(self, client: AppleEmailClient, subject: str) -> str:
        page = await client.search_emails("in:inbox", max_results=5)
        return next(str(hit["id"]) for hit in page["messages"] if hit["subject"] == subject)

    async def test_the_html_alternative_is_read_and_nothing_is_marked_read(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        message_id = await self._id(client, "Html mail")

        with patch.object(imap, "fetch", wraps=imap.fetch) as fetch:
            html = await client.get_message_html(message_id)

        assert html is not None and html.strip() == HTML
        assert fetch.call_args.kwargs["mark_seen"] is False

    async def test_a_text_only_message_has_none(self, client: AppleEmailClient) -> None:
        assert await client.get_message_html(await self._id(client, "Text mail")) is None

    async def test_a_body_split_around_an_inline_image_is_joined_in_document_order(
        self, client: AppleEmailClient
    ) -> None:
        html = await client.get_message_html(await self._id(client, "Segmented mail"))

        assert html == "<p>before</p><p>after</p>"

    async def test_an_attached_page_or_a_forwarded_message_is_not_the_body(
        self, client: AppleEmailClient
    ) -> None:
        assert await client.get_message_html(await self._id(client, "Mail with files")) is None

    async def test_a_message_gone_or_an_unreadable_id_is_named_not_found(
        self, client: AppleEmailClient
    ) -> None:
        gone = (await self._id(client, "Html mail")).replace("101.", "999.", 1)

        for message_id in (gone, "101"):
            with pytest.raises(ImapMessageNotFoundError):
                await client.get_message_html(message_id)

    def test_not_found_is_still_a_value_error_for_the_assistant_s_readers(self) -> None:
        assert issubclass(ImapMessageNotFoundError, ValueError)
