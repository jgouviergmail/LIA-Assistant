"""Downloading ONE attachment of a message, whatever the provider.

The tool layer asks « the attachment of this message called X » or « the one
with this handle »; the three clients answer with one shape — the file name,
the MIME type as sent, the bytes. The selection is ONE helper the three
clients share, so a name that matches two parts is refused the same way
everywhere, and a handle nobody listed is told apart from a name.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentContent,
    EmailAttachmentNotFoundError,
    select_attachment,
)

pytestmark = pytest.mark.unit


# ============================================================================
# select_attachment — one rule for the three providers
# ============================================================================

LISTED = [
    {"attachmentId": "a1", "filename": "Invoice.pdf", "mimeType": "application/pdf", "size": 10},
    {"attachment_id": "a2", "filename": "photo.jpg", "mime_type": "image/jpeg", "size": 20},
    {"attachmentId": "a3", "filename": "photo.jpg", "mimeType": "image/jpeg", "size": 30},
]


def test_select_by_handle_reads_both_spellings() -> None:
    assert select_attachment(LISTED, attachment_id="a1")["filename"] == "Invoice.pdf"
    assert select_attachment(LISTED, attachment_id="a2")["size"] == 20


def test_select_by_name_is_case_insensitive_and_unique() -> None:
    assert select_attachment(LISTED, filename="invoice.PDF")["size"] == 10


def test_select_refuses_an_ambiguous_name_with_its_candidates() -> None:
    with pytest.raises(EmailAttachmentAmbiguousError) as exc_info:
        select_attachment(LISTED, filename="photo.jpg")
    assert [c["size"] for c in exc_info.value.candidates] == [20, 30]


def test_a_missing_name_is_not_found() -> None:
    with pytest.raises(EmailAttachmentNotFoundError):
        select_attachment(LISTED, filename="nope.txt")


def test_a_stale_handle_falls_back_on_the_name_then_on_uniqueness() -> None:
    # Gmail handles change between two reads of a message (measured on a real
    # mailbox 2026-09-17): a handle nobody lists is stale, never a lie.
    assert select_attachment(LISTED, attachment_id="stale", filename="Invoice.pdf")["size"] == 10
    only = [LISTED[0]]
    assert select_attachment(only, attachment_id="stale")["size"] == 10


def test_a_stale_handle_among_several_parts_publishes_the_current_handles() -> None:
    with pytest.raises(EmailAttachmentAmbiguousError) as exc_info:
        select_attachment(LISTED, attachment_id="stale")
    assert [c.get("attachmentId") or c.get("attachment_id") for c in exc_info.value.candidates] == [
        "a1",
        "a2",
        "a3",
    ]


def test_select_needs_a_handle_or_a_name() -> None:
    with pytest.raises(ValueError):
        select_attachment(LISTED)


def test_a_handle_wins_over_a_name_when_both_are_given() -> None:
    assert select_attachment(LISTED, attachment_id="a3", filename="Invoice.pdf")["size"] == 30


# ============================================================================
# Gmail
# ============================================================================


@pytest.fixture
def gmail_client():
    from datetime import UTC, datetime, timedelta

    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
    from src.domains.connectors.schemas import ConnectorCredentials

    return GoogleGmailClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )


GMAIL_PAYLOAD = {
    "id": "m1",
    "payload": {
        "parts": [
            {"mimeType": "text/plain", "filename": "", "body": {"size": 5}},
            {
                "mimeType": "application/pdf",
                "filename": "Invoice.pdf",
                "body": {"attachmentId": "att-9", "size": 3},
            },
        ]
    },
}


async def test_gmail_downloads_by_handle_and_names_the_part(gmail_client) -> None:
    gmail_client.get_message = AsyncMock(return_value=GMAIL_PAYLOAD)
    gmail_client.get_attachment = AsyncMock(return_value=b"%PDF")
    content = await gmail_client.download_attachment("m1", attachment_id="att-9")
    assert content == EmailAttachmentContent("Invoice.pdf", "application/pdf", b"%PDF")
    gmail_client.get_attachment.assert_awaited_once_with("m1", "att-9")


async def test_gmail_downloads_by_name(gmail_client) -> None:
    gmail_client.get_message = AsyncMock(return_value=GMAIL_PAYLOAD)
    gmail_client.get_attachment = AsyncMock(return_value=b"%PDF")
    content = await gmail_client.download_attachment("m1", filename="invoice.pdf")
    assert content.filename == "Invoice.pdf"


async def test_gmail_serves_the_only_part_when_the_handle_went_stale(gmail_client) -> None:
    gmail_client.get_message = AsyncMock(return_value=GMAIL_PAYLOAD)
    gmail_client.get_attachment = AsyncMock(return_value=b"%PDF")
    content = await gmail_client.download_attachment("m1", attachment_id="stale-from-a-listing")
    assert content.filename == "Invoice.pdf"
    # The bytes are asked with the CURRENT handle, never the stale one.
    gmail_client.get_attachment.assert_awaited_once_with("m1", "att-9")


# ============================================================================
# Microsoft Graph
# ============================================================================


@pytest.fixture
def outlook_client():
    from datetime import UTC, datetime, timedelta

    from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
    from src.domains.connectors.schemas import ConnectorCredentials

    return MicrosoftOutlookClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )


async def test_outlook_lists_then_downloads_content_bytes(outlook_client) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_request(method, endpoint, params=None, json_data=None):
        calls.append((method, endpoint))
        if endpoint.endswith("/attachments"):
            return {
                "value": [
                    {
                        "id": "att-1",
                        "name": "Invoice.pdf",
                        "contentType": "application/pdf",
                        "size": 3,
                    }
                ]
            }
        return {
            "id": "att-1",
            "name": "Invoice.pdf",
            "contentType": "application/pdf",
            "contentBytes": base64.b64encode(b"%PDF").decode(),
        }

    outlook_client._make_request = AsyncMock(side_effect=fake_request)
    content = await outlook_client.download_attachment("AAMk-1", filename="invoice.pdf")
    assert content == EmailAttachmentContent("Invoice.pdf", "application/pdf", b"%PDF")
    assert calls == [
        ("GET", "/me/messages/AAMk-1/attachments"),
        ("GET", "/me/messages/AAMk-1/attachments/att-1"),
    ]


# ============================================================================
# Apple (IMAP)
# ============================================================================


APPLE_MODULE = "src.domains.connectors.clients.apple_email_client"


class _FakeMailBox:
    def __init__(self, messages):
        self.messages = messages

    def __call__(self, *args, **kwargs):
        return self

    def login(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def fetch(self, criteria=None, limit=None, mark_seen=False, reverse=False, headers_only=False):
        return list(self.messages)


def _imap_message(attachments):
    return SimpleNamespace(
        uid="42",
        subject="s",
        from_="bob@example.com",
        to=["jane@icloud.com"],
        cc=[],
        date_str="Mon, 20 Jul 2026 09:00:00 +0000",
        date=None,
        text="body",
        html="",
        flags=(),
        size=4,
        attachments=attachments,
        headers={},
    )


@pytest.fixture
def apple_client():
    from src.domains.connectors.clients.apple_email_client import AppleEmailClient
    from src.domains.connectors.schemas import AppleCredentials

    return AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(
            apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl-mnop"
        ),
        connector_service=MagicMock(),
    )


async def test_apple_downloads_by_name_from_the_imap_parts(apple_client) -> None:
    parts = [
        SimpleNamespace(filename="Invoice.pdf", content_type="application/pdf", payload=b"%PDF"),
        SimpleNamespace(filename="photo.jpg", content_type="image/jpeg", payload=b"JPG"),
    ]
    with patch(f"{APPLE_MODULE}.MailBox", _FakeMailBox([_imap_message(parts)])):
        content = await apple_client.download_attachment("42", filename="invoice.pdf")
    assert content == EmailAttachmentContent("Invoice.pdf", "application/pdf", b"%PDF")


async def test_apple_downloads_by_the_index_handle_its_listing_publishes(apple_client) -> None:
    from src.domains.connectors.clients.normalizers.email_normalizer import normalize_imap_message

    parts = [
        SimpleNamespace(filename="Invoice.pdf", content_type="application/pdf", payload=b"%PDF"),
        SimpleNamespace(filename="photo.jpg", content_type="image/jpeg", payload=b"JPG"),
    ]
    listed = normalize_imap_message(_imap_message(parts), "INBOX")["attachments"]
    assert [a["attachmentId"] for a in listed] == ["0", "1"]
    with patch(f"{APPLE_MODULE}.MailBox", _FakeMailBox([_imap_message(parts)])):
        content = await apple_client.download_attachment("42", attachment_id="1")
    assert content.filename == "photo.jpg"


async def test_apple_refuses_an_unknown_message(apple_client) -> None:
    with (
        patch(f"{APPLE_MODULE}.MailBox", _FakeMailBox([])),
        pytest.raises(EmailAttachmentNotFoundError),
    ):
        await apple_client.download_attachment("42", filename="x.pdf")


# ============================================================================
# The size the listing publishes bounds the download BEFORE the bytes move
# ============================================================================


def test_a_listed_part_over_the_bound_is_refused_before_any_download() -> None:
    from src.domains.connectors.clients.email_attachments import (
        EmailAttachmentTooLargeError,
        ensure_within_bound,
    )

    with pytest.raises(EmailAttachmentTooLargeError) as raised:
        ensure_within_bound({"filename": "big.iso", "size": 30_000_000}, max_bytes=20_000_000)
    assert raised.value.size == 30_000_000 and raised.value.max_bytes == 20_000_000
    # No bound, or a listing that knows no size: nothing to refuse on.
    ensure_within_bound({"filename": "big.iso", "size": 30_000_000}, max_bytes=None)
    ensure_within_bound({"filename": "x.pdf"}, max_bytes=1)


async def test_gmail_does_not_fetch_a_part_the_listing_says_is_too_large(gmail_client) -> None:
    from src.domains.connectors.clients.email_attachments import EmailAttachmentTooLargeError

    gmail_client.get_message = AsyncMock(return_value=GMAIL_PAYLOAD)
    gmail_client.get_attachment = AsyncMock(return_value=b"%PDF")
    with pytest.raises(EmailAttachmentTooLargeError):
        await gmail_client.download_attachment("m1", attachment_id="att-9", max_bytes=2)
    gmail_client.get_attachment.assert_not_awaited()
