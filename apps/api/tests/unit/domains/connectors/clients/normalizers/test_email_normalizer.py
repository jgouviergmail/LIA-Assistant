"""Unit tests for IMAP email normalizer."""

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.domains.connectors.clients.normalizers.email_normalizer import (
    convert_imap_query,
    normalize_imap_folder,
    normalize_imap_message,
)


def _make_mail_message(
    uid: int = 42,
    from_: str = "sender@example.com",
    to: tuple[str, ...] = ("recipient@example.com",),
    cc: tuple[str, ...] = (),
    subject: str = "Test Subject",
    date_obj: datetime | None = None,
    date_str: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    text: str = "Hello, world!",
    html: str = "",
    attachments: list | None = None,
    flags: tuple[str, ...] = ("\\Seen",),
) -> MagicMock:
    """Build a mock imap_tools MailMessage."""
    msg = MagicMock()
    msg.uid = uid
    msg.from_ = from_
    msg.to = to
    msg.cc = cc
    msg.subject = subject
    msg.date = date_obj or datetime(2024, 1, 1, 12, 0, 0)
    msg.date_str = date_str
    msg.text = text
    msg.html = html
    msg.attachments = attachments or []
    msg.flags = flags
    return msg


@pytest.mark.unit
class TestNormalizeImapMessage:
    """Tests for normalize_imap_message()."""

    def test_basic_message(self) -> None:
        """Normalize a simple text message with standard fields."""
        msg = _make_mail_message()
        result = normalize_imap_message(msg, "INBOX")

        assert result["id"] == "42"
        assert result["threadId"] == "42"
        assert result["labelIds"] == ["INBOX"]
        assert result["snippet"] == "Hello, world!"

        headers = {h["name"]: h["value"] for h in result["payload"]["headers"]}
        assert headers["From"] == "sender@example.com"
        assert headers["To"] == "recipient@example.com"
        assert headers["Subject"] == "Test Subject"

    def test_html_only_snippet(self) -> None:
        """When no text body exists, snippet is derived from stripped HTML."""
        msg = _make_mail_message(text="", html="<p>HTML &amp; content</p>")
        result = normalize_imap_message(msg, "INBOX")

        assert "HTML & content" in result["snippet"]
        assert "<p>" not in result["snippet"]

    def test_attachments_included(self) -> None:
        """Attachment metadata is present in the normalized output."""
        att = MagicMock()
        att.filename = "report.pdf"
        att.content_type = "application/pdf"
        att.payload = b"fake-bytes"

        msg = _make_mail_message(attachments=[att])
        result = normalize_imap_message(msg, "Sent")

        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "report.pdf"
        assert result["attachments"][0]["mimeType"] == "application/pdf"
        assert result["attachments"][0]["size"] == len(b"fake-bytes")
        assert result["payload"]["filename"] == "report.pdf"

    def test_internal_date_epoch_ms(self) -> None:
        """internalDate is epoch milliseconds string."""
        dt = datetime(2024, 6, 15, 10, 30, 0)
        msg = _make_mail_message(date_obj=dt)
        result = normalize_imap_message(msg, "INBOX")

        expected_ms = str(int(dt.timestamp() * 1000))
        assert result["internalDate"] == expected_ms

    def test_date_only_internal_date(self) -> None:
        """When msg.date is a date (not datetime), internalDate still works."""
        msg = _make_mail_message()
        msg.date = date(2024, 3, 15)
        result = normalize_imap_message(msg, "INBOX")

        assert result["internalDate"] is not None


@pytest.mark.unit
class TestNormalizeImapFolder:
    """Tests for normalize_imap_folder()."""

    def test_system_folder(self) -> None:
        """System folders get type 'system'."""
        result = normalize_imap_folder("INBOX")
        assert result == {"id": "INBOX", "name": "INBOX", "type": "system"}

    def test_user_folder(self) -> None:
        """Custom folders get type 'user'."""
        result = normalize_imap_folder("My Custom Folder")
        assert result["type"] == "user"
        assert result["id"] == "My Custom Folder"

    def test_all_system_folders_recognized(self) -> None:
        """Known IMAP system folders are recognized."""
        for folder in (
            "INBOX",
            "Sent",
            "Sent Messages",
            "Drafts",
            "Trash",
            "Junk",
            "Spam",
            "Archive",
        ):
            assert normalize_imap_folder(folder)["type"] == "system"


@pytest.mark.unit
class TestConvertImapQuery:
    """Tests for convert_imap_query()."""

    def test_from_operator(self) -> None:
        """from: operator maps to from_ criterion."""
        criteria, folder = convert_imap_query("from:alice@example.com")
        assert folder is None
        # AND object should have been built with from_="alice@example.com"
        assert "alice@example.com" in str(criteria)

    def test_subject_and_unread(self) -> None:
        """subject: and is:unread produce correct criteria."""
        criteria, folder = convert_imap_query("subject:meeting is:unread")
        criteria_str = str(criteria)
        assert "meeting" in criteria_str

    def test_label_sets_target_folder(self) -> None:
        """label: operator sets the target_folder return value."""
        _, folder = convert_imap_query("label:Important")
        assert folder == "Important"

    def test_date_range(self) -> None:
        """after: and before: parse dates correctly."""
        criteria, _ = convert_imap_query("after:2024/01/01 before:2024-12-31")
        criteria_str = str(criteria)
        assert "2024" in criteria_str

    def test_bare_text(self) -> None:
        """Bare text (no operator) becomes full-text search."""
        criteria, folder = convert_imap_query("important documents")
        assert folder is None
        assert "important documents" in str(criteria)
