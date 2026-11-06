"""A message's own images and its way out, on the three mail providers (ADR-369, lot 3).

The same contract on three shapes of a message: an image the HTML names is read
into the budget, a name it does not use is left, a part of a message forwarded as
an attachment is another message's; a sender's ``List-Unsubscribe`` is read through
one rule. Reading marks nothing read.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_inline_images import InlineBudget
from src.domains.connectors.clients.mail_unsubscribe import Unsubscribe
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_HTML = "src.domains.connectors.clients.apple_mail_html"
PNG = b"\x89PNG\r\n\x1a\n"
PNG_URL = f"data:image/png;base64,{base64.b64encode(PNG).decode()}"
LEAVE = "<https://example.org/leave>, <mailto:leave@example.org>"
ONE_CLICK = "List-Unsubscribe=One-Click"


def _budget(**bounds: int) -> InlineBudget:
    return InlineBudget(
        each_max=bounds.get("each_max", 1000),
        total_max=bounds.get("total_max", 1000),
        count_max=bounds.get("count_max", 10),
    )


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


def _image_part(cid: str, *, handle: str | None = None, data: bytes = PNG) -> dict[str, Any]:
    body: dict[str, Any] = {"size": len(data)}
    if handle:
        body["attachmentId"] = handle
    else:
        body["data"] = _b64(data)
    return {
        "mimeType": "image/png",
        "filename": f"{cid}.png",
        "headers": [{"name": "Content-ID", "value": f"<{cid}>"}],
        "body": body,
    }


def _tree(*parts: dict[str, Any], headers: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "mimeType": "multipart/related",
        "filename": "",
        "headers": headers or [],
        "body": {"size": 0},
        "parts": list(parts),
    }


class TestGmail:
    @pytest.fixture
    def client(self) -> Iterator[GoogleGmailClient]:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
        ):
            yield client

    async def _inline(
        self, client: GoogleGmailClient, payload: dict[str, Any], cids: set[str], budget: Any
    ) -> list[httpx.Request]:
        def answer(request: httpx.Request) -> httpx.Response:
            if "/attachments/" in request.url.path:
                return httpx.Response(200, json={"data": _b64(PNG), "size": len(PNG)})
            return httpx.Response(200, json={"id": "m1", "threadId": "t1", "payload": payload})

        _, seen = await _drive(
            client, answer, lambda: client.read_inline_images("m1", cids, budget)
        )
        return seen

    async def test_an_image_the_html_names_is_read(self, client: GoogleGmailClient) -> None:
        budget = _budget()

        await self._inline(client, _tree(_image_part("logo@x")), {"logo@x"}, budget)

        assert [(image.cid, image.data_url) for image in budget.images] == [("logo@x", PNG_URL)]

    async def test_a_part_too_large_to_travel_inline_is_read_by_its_handle(
        self, client: GoogleGmailClient
    ) -> None:
        budget = _budget()

        seen = await self._inline(
            client, _tree(_image_part("logo@x", handle="h1")), {"logo@x"}, budget
        )

        assert budget.images[0].data_url == PNG_URL
        assert any(request.url.path.endswith("/attachments/h1") for request in seen)

    async def test_a_name_the_html_does_not_use_is_left(self, client: GoogleGmailClient) -> None:
        budget = _budget()

        seen = await self._inline(
            client, _tree(_image_part("other", handle="h1")), {"logo@x"}, budget
        )

        assert budget.images == []
        assert budget.skipped == 0
        assert not any("/attachments/" in request.url.path for request in seen)

    async def test_a_part_past_the_budget_is_counted_and_never_read(
        self, client: GoogleGmailClient
    ) -> None:
        budget = _budget(each_max=2)

        seen = await self._inline(
            client, _tree(_image_part("logo@x", handle="h1")), {"logo@x"}, budget
        )

        assert budget.skipped == 1
        assert not any("/attachments/" in request.url.path for request in seen)

    async def test_a_forwarded_message_keeps_its_images(self, client: GoogleGmailClient) -> None:
        forwarded = {
            "mimeType": "message/rfc822",
            "filename": "",
            "headers": [],
            "body": {"size": 0},
            "parts": [_image_part("logo@x")],
        }
        budget = _budget()

        await self._inline(client, _tree(forwarded), {"logo@x"}, budget)

        assert budget.images == []

    async def test_the_way_out_is_read_from_the_message_s_headers(
        self, client: GoogleGmailClient
    ) -> None:
        payload = _tree(
            headers=[
                {"name": "List-Unsubscribe", "value": LEAVE},
                {"name": "list-unsubscribe-post", "value": ONE_CLICK},
            ]
        )

        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "m1", "threadId": "t1", "payload": payload})

        found, _ = await _drive(client, answer, lambda: client.read_unsubscribe("m1"))

        assert found == Unsubscribe(
            web_url="https://example.org/leave", mail_to="leave@example.org", one_click=True
        )

    async def test_no_header_is_no_way_out(self, client: GoogleGmailClient) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "m1", "threadId": "t1", "payload": _tree()})

        found, _ = await _drive(client, answer, lambda: client.read_unsubscribe("m1"))

        assert found is None


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    @staticmethod
    def _listing(*items: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/attachments"):
                return httpx.Response(200, json={"value": list(items)})
            return httpx.Response(
                200, json={"contentBytes": base64.b64encode(PNG).decode(), "name": "logo.png"}
            )

        return answer

    @staticmethod
    def _item(cid: str, *, size: int = len(PNG), inline: bool = True) -> dict[str, Any]:
        return {
            "id": f"a-{cid}",
            "contentType": "image/png",
            "size": size,
            "isInline": inline,
            "contentId": cid,
        }

    async def test_an_image_the_html_names_is_read(self, client: MicrosoftOutlookClient) -> None:
        budget = _budget()

        _, seen = await _drive(
            client,
            self._listing(self._item("logo@x")),
            lambda: client.read_inline_images("m1", {"logo@x"}, budget),
        )

        assert [(image.cid, image.data_url) for image in budget.images] == [("logo@x", PNG_URL)]
        assert "contentId" in seen[0].url.params["$select"]

    async def test_a_name_the_html_does_not_use_is_left(
        self, client: MicrosoftOutlookClient
    ) -> None:
        budget = _budget()

        _, seen = await _drive(
            client,
            self._listing(self._item("other")),
            lambda: client.read_inline_images("m1", {"logo@x"}, budget),
        )

        assert budget.images == []
        assert len(seen) == 1

    async def test_a_listed_size_past_the_budget_is_counted_and_never_read(
        self, client: MicrosoftOutlookClient
    ) -> None:
        budget = _budget(each_max=2)

        _, seen = await _drive(
            client,
            self._listing(self._item("logo@x")),
            lambda: client.read_inline_images("m1", {"logo@x"}, budget),
        )

        assert budget.skipped == 1
        assert len(seen) == 1

    async def test_a_message_s_id_is_one_segment(self, client: MicrosoftOutlookClient) -> None:
        _, seen = await _drive(
            client,
            self._listing(),
            lambda: client.read_inline_images("a/b", {"logo@x"}, _budget()),
        )

        assert "a%2Fb" in str(seen[0].url)

    async def test_the_way_out_is_asked_of_the_message_s_headers(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "internetMessageHeaders": [
                        {"name": "List-Unsubscribe", "value": LEAVE},
                        {"name": "List-Unsubscribe-Post", "value": ONE_CLICK},
                    ]
                },
            )

        found, seen = await _drive(client, answer, lambda: client.read_unsubscribe("m1"))

        assert seen[0].url.params["$select"] == "internetMessageHeaders"
        assert found == Unsubscribe(
            web_url="https://example.org/leave", mail_to="leave@example.org", one_click=True
        )

    async def test_a_message_with_no_headers_has_no_way_out(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        found, _ = await _drive(client, answer, lambda: client.read_unsubscribe("m1"))

        assert found is None


def _headed(message: Any, subject: str) -> Any:
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    return message


def _with_image(subject: str, cid: str = "logo@x", size: int = 0) -> Any:
    message = MIMEMultipart("related")
    message.attach(MIMEText(f'<img src="cid:{cid}">', "html"))
    image = MIMEImage(PNG + b"\0" * size, "png")
    image.add_header("Content-ID", f"<{cid}>")
    message.attach(image)
    return _headed(message, subject)


def _forwarded_image(subject: str) -> EmailMessage:
    message = EmailMessage()
    message.set_content("See below.")
    message.add_attachment(_with_image("Forwarded"))
    return _headed(message, subject)


def _leaving(subject: str) -> EmailMessage:
    message = EmailMessage()
    message.set_content("News.")
    message["List-Unsubscribe"] = LEAVE
    message["List-Unsubscribe-Post"] = ONE_CLICK
    return _headed(message, subject)


class TestImap:
    @pytest.fixture
    def imap(self) -> FakeImap:
        imap = FakeImap()
        imap.put("INBOX", _with_image("Image mail"), uid="101")
        imap.put("INBOX", _forwarded_image("Forwarded mail"), uid="102")
        imap.put("INBOX", _leaving("News mail"), uid="103")
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

    async def test_an_image_the_html_names_is_read_and_nothing_is_marked_read(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        budget = _budget()
        message_id = await self._id(client, "Image mail")

        with patch.object(imap, "fetch", wraps=imap.fetch) as fetch:
            await client.read_inline_images(message_id, {"logo@x"}, budget)

        assert [(image.cid, image.data_url) for image in budget.images] == [("logo@x", PNG_URL)]
        assert fetch.call_args.kwargs["mark_seen"] is False

    async def test_a_name_the_html_does_not_use_is_left(self, client: AppleEmailClient) -> None:
        budget = _budget()

        await client.read_inline_images(await self._id(client, "Image mail"), {"other"}, budget)

        assert budget.images == []

    async def test_a_part_past_the_budget_is_counted(self, client: AppleEmailClient) -> None:
        budget = _budget(each_max=2)

        await client.read_inline_images(await self._id(client, "Image mail"), {"logo@x"}, budget)

        assert budget.images == []
        assert budget.skipped == 1

    async def test_a_forwarded_message_keeps_its_images(self, client: AppleEmailClient) -> None:
        budget = _budget()

        await client.read_inline_images(
            await self._id(client, "Forwarded mail"), {"logo@x"}, budget
        )

        assert budget.images == []

    async def test_the_way_out_is_read_from_the_headers_alone(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        message_id = await self._id(client, "News mail")

        with patch.object(imap, "fetch", wraps=imap.fetch) as fetch:
            found = await client.read_unsubscribe(message_id)

        assert found == Unsubscribe(
            web_url="https://example.org/leave", mail_to="leave@example.org", one_click=True
        )
        assert fetch.call_args.kwargs["headers_only"] is True
        assert fetch.call_args.kwargs["mark_seen"] is False

    async def test_no_header_is_no_way_out(self, client: AppleEmailClient) -> None:
        assert await client.read_unsubscribe(await self._id(client, "Image mail")) is None
