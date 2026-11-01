"""Read / unread on the three mail providers — one contract (ADR-369, owner decision D2).

Gmail's client could already move the ``UNREAD`` system label, Outlook only read
``isRead`` and IMAP never set ``\\Seen``: a gesture one provider had and the
others lacked. ``mark_read`` gives all three the same contract — each id is
updated or reported (``not_found`` / ``failed``), the rest of a selection
still updated — and the assistant reaches it through one neutral tool.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_read_state import READ_STATE_NOT_FOUND
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_MIXIN = "src.domains.connectors.clients.apple_drafts_mixin"
APPLE_STATE = "src.domains.connectors.clients.apple_mail_state_mixin"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.raw_path.decode(), body))
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


class TestGmail:
    @pytest.fixture
    def client(self) -> Iterator[GoogleGmailClient]:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        # No real Redis: the generation a write moves is the freshness suite's to prove.
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
        ):
            yield client

    @pytest.mark.parametrize(
        ("read", "expected"),
        [(True, {"removeLabelIds": ["UNREAD"]}), (False, {"addLabelIds": ["UNREAD"]})],
    )
    async def test_one_batch_moves_the_unread_label(
        self, client: GoogleGmailClient, read: bool, expected: dict[str, list[str]]
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        result = await _drive(client, recorder, lambda: client.mark_read(["m1", "m2"], read))

        assert result == {"updated": ["m1", "m2"], "failed": []}
        ((method, path, body),) = recorder.calls
        assert (method, path) == ("POST", "/gmail/v1/users/me/messages/batchModify")
        assert body == {"ids": ["m1", "m2"], **expected}

    async def test_a_refused_batch_finds_the_gone_message_one_by_one(
        self, client: GoogleGmailClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("batchModify"):
                return httpx.Response(400, json={"error": {"message": "Invalid id value"}})
            if "/messages/gone/" in request.url.path:
                return httpx.Response(404, json={"error": {"code": 404}})
            return httpx.Response(200, json={"id": "m1", "labelIds": []})

        result = await _drive(
            client, _Recorder(answer), lambda: client.mark_read(["m1", "gone"], True)
        )

        assert result == {
            "updated": ["m1"],
            "failed": [{"id": "gone", "status": READ_STATE_NOT_FOUND}],
        }

    async def test_a_selection_is_deduplicated(self, client: GoogleGmailClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))
        await _drive(client, recorder, lambda: client.mark_read(["m1", "m1"], True))
        assert recorder.calls[0][2]["ids"] == ["m1"]


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    async def test_each_message_is_patched_and_a_gone_one_is_named(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if "gone" in request.url.path:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            return httpx.Response(200, json={"id": "o1", "isRead": True})

        recorder = _Recorder(answer)
        result = await _drive(client, recorder, lambda: client.mark_read(["o1", "gone"], True))

        assert result == {
            "updated": ["o1"],
            "failed": [{"id": "gone", "status": READ_STATE_NOT_FOUND}],
        }
        assert ("PATCH", "/v1.0/me/messages/o1", {"isRead": True}) in recorder.calls

    async def test_an_authorisation_failure_is_raised_as_itself(
        self, client: MicrosoftOutlookClient
    ) -> None:
        """A TaskGroup raises an ExceptionGroup even for one failure: unwrapped, the
        refusal stays classifiable by its type (reconnect), never an opaque group."""
        from src.core.exceptions import ConnectorTokenExpiredError

        async def answer(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            if endpoint.endswith("/o2"):
                raise ConnectorTokenExpiredError("reconnect", "microsoft_outlook")
            return {}

        with (
            patch.object(client, "_make_request", AsyncMock(side_effect=answer)),
            pytest.raises(ConnectorTokenExpiredError),
        ):
            await client.mark_read(["o1", "o2", "o3"], True)

    async def test_an_id_is_quoted_into_the_path(self, client: MicrosoftOutlookClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={}))
        await _drive(client, recorder, lambda: client.mark_read(["AAMk/x+y="], False))
        assert recorder.calls == [("PATCH", "/v1.0/me/messages/AAMk%2Fx%2By%3D", {"isRead": False})]


def _mail(subject: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    message.set_content(f"{subject} body.")
    return message


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


class TestImap:
    @pytest.fixture
    def imap(self) -> FakeImap:
        imap = FakeImap()
        imap.put("INBOX", _mail("Inbox mail"), uid="101")
        imap.put("Sent Messages", _mail("Sent mail"), uid="101", flags=("\\Seen",))
        return imap

    @pytest.fixture
    def client(self, imap: FakeImap) -> Iterator[AppleEmailClient]:
        instance = AppleEmailClient(
            user_id=uuid4(),
            credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
            connector_service=MagicMock(),
        )
        redis = _Redis()
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
        with (
            patch(f"{APPLE}.MailBox", imap),
            patch(f"{APPLE_MIXIN}.MailBox", imap),
            patch(f"{APPLE_STATE}.MailBox", imap),
            patch(f"{APPLE}.get_redis_session", AsyncMock(return_value=redis)),
            patch(f"{APPLE_MIXIN}.get_redis_session", AsyncMock(return_value=redis)),
            patch(f"{APPLE_STATE}.get_redis_session", AsyncMock(return_value=redis)),
            patch.object(instance, "_rate_limit", AsyncMock()),
            patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            yield instance

    async def _ids(self, client: AppleEmailClient) -> tuple[str, str]:
        inbox = (await client.search_emails("in:inbox", max_results=5))["messages"][0]["id"]
        sent = (await client.search_emails("in:sent", max_results=5))["messages"][0]["id"]
        return str(inbox), str(sent)

    async def test_each_folder_is_flagged_in_its_own_selection(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        inbox, sent = await self._ids(client)

        assert await client.mark_read([inbox, sent], True) == {
            "updated": [inbox, sent],
            "failed": [],
        }
        assert "\\Seen" in imap.store["INBOX"]["101"][1]
        assert "\\Seen" in imap.store["Sent Messages"]["101"][1]

        await client.mark_read([sent], False)
        assert "\\Seen" not in imap.store["Sent Messages"]["101"][1]
        assert "\\Seen" in imap.store["INBOX"]["101"][1], "another folder's 101 is untouched"

    async def test_a_gone_or_unreadable_id_is_named_and_the_rest_updated(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        inbox, _sent = await self._ids(client)
        gone = inbox.replace("101.", "999.", 1)

        result = await client.mark_read([inbox, gone, "101"], True)

        assert result["updated"] == [inbox]
        assert result["failed"] == [
            {"id": gone, "status": READ_STATE_NOT_FOUND},
            {"id": "101", "status": READ_STATE_NOT_FOUND},
        ]


class TestGmailIdsNeverShapeAPath:
    """Cold review of L2: trash, restore and delete used the id raw in the URL path —
    an id from a browser or a model must never name another endpoint."""

    @pytest.mark.parametrize("act", ["trash_email", "untrash_email", "delete_email_permanently"])
    async def test_a_malformed_id_names_no_message_and_sends_nothing(self, act: str) -> None:
        from src.core.exceptions import ConnectorAPIError

        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={}))

        with pytest.raises(ConnectorAPIError) as refused:
            await _drive(client, recorder, lambda: getattr(client, act)("x/../../drafts/d1"))

        assert refused.value.upstream_status_code == 404
        assert recorder.calls == [], "nothing reached Gmail"
        assert "drafts" not in str(refused.value.detail)
