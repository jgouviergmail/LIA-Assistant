"""Mailbox drafts on Gmail (ADR-344), against a fake honouring the contract MEASURED
on a real mailbox on 2026-10-13: a draft is a resource holding one message, an
update replaces the message (a new message id, the same draft id), a write through
the upload URI keeps its thread only when the multipart metadata names it, the
trash takes the draft's MESSAGE (recoverable), and an unknown draft id is a 404.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import GOOGLE_GMAIL_UPLOAD_BASE_URL
from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    MailboxDraftNotFoundError,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

ORIGINAL_TEXT = "Voici le budget.\nMerci."


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _parse(raw: bytes) -> EmailMessage:
    parsed = BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(raw)
    assert isinstance(parsed, EmailMessage)
    return parsed


def _payload(message: EmailMessage) -> dict[str, Any]:
    """Gmail's ``full`` payload tree for a stored message."""
    headers = [{"name": k, "value": str(v)} for k, v in message.items()]
    if not message.is_multipart():
        data = message.get_payload(decode=True)
        assert isinstance(data, bytes)
        return {
            "mimeType": message.get_content_type(),
            "headers": headers,
            "body": {"data": _b64(data)},
        }
    parts = []
    for part in message.iter_parts():
        assert isinstance(part, EmailMessage)
        node = _payload(part)
        if part.get_filename():
            node |= {"filename": part.get_filename(), "body": {"attachmentId": "att", "size": 4}}
        parts.append(node)
    return {"mimeType": message.get_content_type(), "headers": headers, "parts": parts}


class FakeGmail:
    """``users.drafts`` and the calls around it, in memory."""

    def __init__(self) -> None:
        self.drafts: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.fail_trash_of: dict[str, Exception] = {}
        self._serial = 0

    def _next(self, prefix: str) -> str:
        self._serial += 1
        return f"{prefix}{self._serial}"

    def seed(self, message: EmailMessage, *, thread_id: str) -> str:
        draft_id = self._next("r-")
        self._store(draft_id, message.as_bytes(), thread_id)
        return draft_id

    def _store(self, draft_id: str, raw: bytes, thread_id: str | None) -> None:
        self.drafts[draft_id] = {
            "message_id": self._next("m"),
            "thread_id": thread_id or self._next("t"),
            "raw": raw,
            "labels": ["DRAFT"],
        }
        if draft_id in self.order:
            self.order.remove(draft_id)
        self.order.insert(0, draft_id)

    @staticmethod
    def missing() -> ConnectorAPIError:
        return ConnectorAPIError(connector_type="google_gmail", status_code=404, detail="nf")

    def _resource(self, draft_id: str, fmt: str) -> dict[str, Any]:
        stored = self.drafts[draft_id]
        message: dict[str, Any] = {
            "id": stored["message_id"],
            "threadId": stored["thread_id"],
            "labelIds": list(stored["labels"]),
        }
        if fmt == "raw":
            message["raw"] = _b64(stored["raw"])
        elif fmt in {"full", "metadata"}:
            payload = _payload(_parse(stored["raw"]))
            if fmt == "metadata":
                payload = {"headers": payload["headers"], "mimeType": payload["mimeType"]}
            message["payload"] = payload
        return {"id": draft_id, "message": message}

    @staticmethod
    def _split_multipart(content: bytes, content_type: str) -> tuple[dict[str, Any], bytes]:
        boundary = content_type.split("boundary=", 1)[1].encode()
        segments = content.split(b"--" + boundary)
        metadata = json.loads(segments[1].split(b"\r\n\r\n", 1)[1].strip())
        raw = segments[2].split(b"\r\n\r\n", 1)[1]
        return metadata, raw.removesuffix(b"\r\n")

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
        *,
        content: bytes | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        params = params or {}
        self.calls.append(
            {
                "method": method,
                "endpoint": endpoint,
                "params": params,
                "max_retries": max_retries,
            }
        )
        if endpoint == "/users/me/profile":
            return {"emailAddress": "me@example.com"}
        if method == "GET" and endpoint == "/users/me/drafts":
            listed = [d for d in self.order if "TRASH" not in self.drafts[d]["labels"]]
            listed = listed[: params.get("maxResults", 100)]
            return {
                "drafts": [{"id": d} for d in listed],
                "resultSizeEstimate": len(listed),
                "nextPageToken": "next-page",
            }
        if method == "GET" and endpoint.startswith("/users/me/drafts/"):
            draft_id = endpoint.rsplit("/", 1)[1]
            if draft_id not in self.drafts:
                raise self.missing()
            return self._resource(draft_id, params.get("format", "full"))
        if method in {"POST", "PUT"} and content is not None:
            assert base_url == GOOGLE_GMAIL_UPLOAD_BASE_URL
            assert params == {"uploadType": "multipart"}
            metadata, raw = self._split_multipart(content, (extra_headers or {})["Content-Type"])
            draft_id = endpoint.rsplit("/", 1)[1] if method == "PUT" else self._next("r-")
            if method == "PUT" and draft_id not in self.drafts:
                raise self.missing()
            self._store(draft_id, raw, metadata["message"].get("threadId"))
            return self._resource(draft_id, "minimal")
        if method == "POST" and endpoint.endswith("/trash"):
            message_id = endpoint.split("/")[-2]
            if message_id in self.fail_trash_of:
                raise self.fail_trash_of[message_id]
            for stored in self.drafts.values():
                if stored["message_id"] == message_id:
                    stored["labels"].append("TRASH")
                    return {"id": message_id}
            raise self.missing()
        if method == "POST" and endpoint == "/users/me/drafts/send":
            draft_id = (json_data or {})["id"]
            if draft_id not in self.drafts:
                raise self.missing()
            stored = self.drafts.pop(draft_id)
            return {"id": "sent-1", "threadId": stored["thread_id"], "labelIds": ["SENT"]}
        raise AssertionError(f"unexpected {method} {endpoint}")


def _original() -> dict[str, Any]:
    return {
        "id": "orig-1",
        "threadId": "thread-9",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Budget 2027"},
                {"name": "From", "value": "Paul Durand <paul@example.com>"},
                {"name": "To", "value": "me@example.com, marie@example.com"},
                {"name": "Date", "value": "Mon, 12 Oct 2026 10:00:00 +0200"},
                {"name": "Message-ID", "value": "<orig-1@mail.example.com>"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64(ORIGINAL_TEXT.encode())}},
                {
                    "mimeType": "application/pdf",
                    "filename": "budget.pdf",
                    "body": {"attachmentId": "att-1", "size": 4},
                },
            ],
        },
    }


@pytest.fixture
def gmail() -> FakeGmail:
    return FakeGmail()


@pytest.fixture
def client(gmail: FakeGmail) -> Iterator[GoogleGmailClient]:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    instance = GoogleGmailClient(uuid4(), credentials, MagicMock())
    with (
        patch.object(instance, "_make_request", side_effect=gmail.request),
        patch.object(instance, "get_message", AsyncMock(return_value=_original())),
        patch.object(instance, "get_attachment", AsyncMock(return_value=b"%PDF")),
    ):
        yield instance


def _stored(gmail: FakeGmail, draft_id: str) -> EmailMessage:
    return _parse(gmail.drafts[draft_id]["raw"])


def _text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain",))
    assert part is not None
    return str(part.get_content())


def _seeded(gmail: FakeGmail, *, with_file: bool = False) -> str:
    message = EmailMessage()
    message["To"] = "Paul <paul@example.com>"
    message["Cc"] = "anne@example.com"
    message["Subject"] = "Re: Budget"
    message["In-Reply-To"] = "<orig-1@example.com>"
    message.set_content("Old words.\n\nOn Mon, Paul wrote:\n> Budget?")
    if with_file:
        message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="b.pdf")
    return gmail.seed(message, thread_id="thread-1")


class TestCreate:
    async def test_a_new_draft_is_saved_and_read_back(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.create_draft(
            "Marie <marie@example.com>",
            "Budget",
            "Bonjour",
            cc="anne@example.com",
            bcc="boss@example.com",
        )

        stored = _stored(gmail, draft[FIELD_MAILBOX_DRAFT_ID])
        assert (stored["To"], stored["Cc"], stored["Bcc"]) == (
            "Marie <marie@example.com>",
            "anne@example.com",
            "boss@example.com",
        )
        assert draft["id"] == gmail.drafts[draft[FIELD_MAILBOX_DRAFT_ID]]["message_id"]
        assert (draft["to"], draft["subject"], draft["bcc"]) == (
            "Marie <marie@example.com>",
            "Budget",
            "boss@example.com",
        )
        assert draft["body"].strip() == "Bonjour"

    async def test_a_draft_may_have_no_recipient_yet(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.create_draft("", "Idée", "À compléter")

        assert _stored(gmail, draft[FIELD_MAILBOX_DRAFT_ID])["To"] is None

    async def test_a_creation_is_attempted_once(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        await client.create_draft("marie@example.com", "Budget", "Bonjour")

        assert [c["max_retries"] for c in gmail.calls if c["method"] == "POST"] == [1]

    async def test_a_reply_draft_stays_in_the_thread_and_keeps_the_quote(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.create_reply_draft("orig-1", "Validé.", reply_all=True)

        stored = _stored(gmail, draft[FIELD_MAILBOX_DRAFT_ID])
        assert draft["threadId"] == "thread-9"
        assert stored["In-Reply-To"] == "<orig-1@mail.example.com>"
        assert stored["To"] == "Paul Durand <paul@example.com>, marie@example.com"
        assert draft["subject"] == "Re: Budget 2027"
        assert "> Voici le budget." in draft["body"]

    async def test_a_forward_draft_carries_the_files(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.create_forward_draft("orig-1", "marie@example.com", body="Pour info.")

        stored = _stored(gmail, draft[FIELD_MAILBOX_DRAFT_ID])
        assert [p.get_filename() for p in stored.iter_attachments()] == ["budget.pdf"]
        assert stored["Subject"] == "Fwd: Budget 2027"
        assert _text(stored).startswith("Pour info.")


class TestUpdate:
    async def test_a_current_revision_can_replace_the_message(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)
        revision = (await client.get_draft(draft_id))["mailbox_draft_revision"]
        result = await client.update_draft(
            draft_id, body="Current words", expected_revision=revision
        )

        assert result["body"].strip() == "Current words"

    async def test_a_stale_revision_refuses_before_replacing_the_message(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)
        before = gmail.drafts[draft_id]["raw"]
        with pytest.raises(LookupError):
            await client.update_draft(draft_id, body="Stale words", expected_revision="old-version")

        assert gmail.drafts[draft_id]["raw"] == before
        assert not any(c["method"] == "PUT" for c in gmail.calls)

    async def test_the_fields_given_change_and_the_rest_stays(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail, with_file=True)
        before = gmail.drafts[draft_id]["message_id"]

        draft = await client.update_draft(draft_id, to="Marie <marie@example.com>", cc="")

        stored = _stored(gmail, draft_id)
        assert draft[FIELD_MAILBOX_DRAFT_ID] == draft_id
        assert draft["id"] != before
        assert gmail.drafts[draft_id]["thread_id"] == "thread-1"
        assert (stored["To"], stored["Cc"]) == ("Marie <marie@example.com>", None)
        assert stored["In-Reply-To"] == "<orig-1@example.com>"
        assert [p.get_filename() for p in stored.iter_attachments()] == ["b.pdf"]
        assert _text(stored).startswith("Old words.")

    async def test_a_new_body_replaces_the_text(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.update_draft(_seeded(gmail), body="New words.")

        assert draft["body"].strip() == "New words."

    async def test_an_invalid_address_is_refused_before_anything_is_saved(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)
        raw = gmail.drafts[draft_id]["raw"]

        with pytest.raises(ValueError):
            await client.update_draft(draft_id, to="marie@")

        assert gmail.drafts[draft_id]["raw"] == raw

    async def test_a_draft_in_the_trash_cannot_be_edited(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)
        gmail.drafts[draft_id]["labels"].append("TRASH")

        with pytest.raises(MailboxDraftNotFoundError):
            await client.update_draft(draft_id, subject="x")


class TestRead:
    async def test_replacing_only_an_attachment_changes_the_confirmation_fingerprint(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        from src.domains.agents.tools.mailbox_draft_send_tools import live_digest

        handle = _seeded(gmail, with_file=True)
        before = await client.get_draft(handle)
        message = _stored(gmail, handle)
        attachment = next(message.iter_attachments())
        attachment.set_payload(_b64(b"other file bytes"))
        gmail._store(handle, message.as_bytes(), "thread-1")

        after = await client.get_draft(handle)

        assert before["body"] == after["body"]
        assert live_digest(before) != live_digest(after)

    async def test_an_unknown_draft_is_not_found(self, client: GoogleGmailClient) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.get_draft("r-404")

    @pytest.mark.parametrize("handle", ["", "../messages/m1", "r 1", "r-1/trash"])
    async def test_a_handle_that_cannot_be_a_draft_reaches_no_endpoint(
        self, client: GoogleGmailClient, gmail: FakeGmail, handle: str
    ) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.get_draft(handle)

        assert gmail.calls == []

    async def test_the_listing_is_the_mailboxs_order_with_each_handle(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        first, second = _seeded(gmail), _seeded(gmail)

        listing = await client.list_drafts("to:paul", max_results=5)

        assert [d[FIELD_MAILBOX_DRAFT_ID] for d in listing["messages"]] == [second, first]
        assert listing["resultSizeEstimate"] == 2
        assert listing["next_page_token"] == "next-page"
        assert gmail.calls[0]["params"] == {"q": "to:paul", "maxResults": 5}
        assert {c["params"].get("format") for c in gmail.calls[1:]} == {"metadata"}

    async def test_a_draft_gone_between_listing_and_reading_is_skipped(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        kept, gone = _seeded(gmail), _seeded(gmail)

        async def vanishing(method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
            if endpoint == f"/users/me/drafts/{gone}":
                raise gmail.missing()
            return await gmail.request(method, endpoint, **kwargs)

        with patch.object(client, "_make_request", side_effect=vanishing):
            listing = await client.list_drafts(headers_only=False)

        assert [d[FIELD_MAILBOX_DRAFT_ID] for d in listing["messages"]] == [kept]

    async def test_a_full_draft_keeps_its_quoted_history(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft = await client.get_draft(_seeded(gmail))

        assert "> Budget?" in draft["body"]


class TestTrashAndSend:
    async def test_drafts_go_to_the_trash_through_their_message(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        already, trashed = _seeded(gmail), _seeded(gmail)
        gmail.drafts[already]["labels"].append("TRASH")

        result = await client.trash_drafts([trashed, already, "r-404"])

        assert result["trashed"] == [trashed]
        assert result["failed"] == [
            {FIELD_MAILBOX_DRAFT_ID: already, "status": TRASH_NOT_FOUND},
            {FIELD_MAILBOX_DRAFT_ID: "r-404", "status": TRASH_NOT_FOUND},
        ]
        assert "TRASH" in gmail.drafts[trashed]["labels"]

    async def test_a_mailbox_outage_before_any_trash_is_raised(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)
        gmail.fail_trash_of[gmail.drafts[draft_id]["message_id"]] = ExternalServiceError(
            service_name="google_gmail"
        )

        with pytest.raises(ExternalServiceError):
            await client.trash_drafts([draft_id])

    async def test_a_draft_is_sent_once_as_stored(
        self, client: GoogleGmailClient, gmail: FakeGmail
    ) -> None:
        draft_id = _seeded(gmail)

        result = await client.send_draft(draft_id)

        send = [c for c in gmail.calls if c["endpoint"] == "/users/me/drafts/send"]
        assert [c["max_retries"] for c in send] == [1]
        assert result == {
            "id": "sent-1",
            "threadId": "thread-1",
            FIELD_MAILBOX_DRAFT_ID: draft_id,
            "draft_kept": False,
        }
        assert draft_id not in gmail.drafts

    async def test_sending_an_unknown_draft_is_not_found(self, client: GoogleGmailClient) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.send_draft("r-404")
