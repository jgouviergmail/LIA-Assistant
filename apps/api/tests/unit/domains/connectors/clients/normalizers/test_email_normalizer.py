"""Unit tests for IMAP email normalizer."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from src.domains.connectors.clients.normalizers.email_normalizer import (
    convert_imap_query,
    normalize_imap_folder,
    normalize_imap_message,
    parse_imap_query,
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
    msg.bcc = ()
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

        # The vocabulary is flat (ADR-287): no fabricated Gmail tree.
        assert "payload" not in result
        assert result["from"] == "sender@example.com"
        assert result["to"] == "recipient@example.com"
        assert result["subject"] == "Test Subject"

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

    def test_internal_date_epoch_ms(self) -> None:
        """internalDate is epoch milliseconds string."""
        dt = datetime(2024, 6, 15, 10, 30, 0)
        msg = _make_mail_message(date_obj=dt)
        result = normalize_imap_message(msg, "INBOX")

        expected_ms = str(int(dt.replace(tzinfo=UTC).timestamp() * 1000))
        assert result["internalDate"] == expected_ms

    def test_a_date_with_unknown_original_zone_still_represents_utc(self) -> None:
        # Python's mail-date parser returns a naive datetime for -0000: its
        # instant is UTC, although the sender's original zone is unknown.
        msg = _make_mail_message(
            date_obj=datetime(1970, 1, 1), date_str="Thu, 1 Jan 1970 00:00:00 -0000"
        )
        assert normalize_imap_message(msg, "INBOX")["internalDate"] == "0"

    def test_date_only_internal_date(self) -> None:
        """When msg.date is a date (not datetime), internalDate still works."""
        msg = _make_mail_message()
        msg.date = date(2024, 3, 15)
        result = normalize_imap_message(msg, "INBOX")

        assert result["internalDate"] is not None


@pytest.mark.unit
class TestNormalizeImapDraft:
    """A mailbox draft keeps what it quotes and says it is a draft (ADR-344)."""

    OWN = "My answer to your question, with the figures."
    REPLY = f"{OWN}\n\nOn Mon, 1 Jan 2024, Paul wrote:\n> The question?"

    def test_a_draft_keeps_its_quoted_history(self) -> None:
        msg = _make_mail_message(text=self.REPLY, flags=("\\Seen", "\\Draft"))

        assert normalize_imap_message(msg, "Drafts", keep_quoted=True)["body"] == self.REPLY
        assert normalize_imap_message(msg, "Drafts")["body"] == self.OWN

    def test_the_draft_flag_becomes_the_draft_label(self) -> None:
        msg = _make_mail_message(flags=("\\Seen", "\\Draft"))

        assert "DRAFT" in normalize_imap_message(msg, "Drafts")["labelIds"]

    def test_the_blind_copies_are_exposed(self) -> None:
        msg = _make_mail_message()
        msg.bcc = ("boss@example.com", "audit@example.com")

        assert normalize_imap_message(msg, "Drafts")["bcc"] == (
            "boss@example.com, audit@example.com"
        )


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

    def test_cc_operator_maps_to_a_real_criterion(self) -> None:
        """`cc:` must be a CRITERION, never free text.

        The CRM lists mail SENT to a person whether they were a direct
        recipient or in copy. Unrecognized, `cc:` fell through to the
        full-text bucket — which matches the address anywhere in the body and
        turns a precise question into a bag of false positives.
        """
        criteria, folder = convert_imap_query("in:sent cc:alice@example.com")
        criteria_str = str(criteria)
        assert "alice@example.com" in criteria_str
        # Proof it is the CC criterion and not the text one.
        assert "text" not in criteria_str.lower()
        assert folder == "sent"

    def test_label_sets_target_folder(self) -> None:
        """label: operator sets the target_folder return value."""
        _, folder = convert_imap_query("label:Important")
        assert folder == "Important"

    @pytest.mark.parametrize(
        ("query", "expected"),
        [("label:DRAFT", "DRAFT"), ("in:trash", "trash"), ("label:Factures", "Factures")],
    )
    def test_the_folder_is_named_as_written_for_the_session_to_resolve(
        self, query: str, expected: str
    ) -> None:
        """A name typed in this converter cannot be the server's: iCloud keeps
        its trash in « Deleted Messages ». The session resolves the value — a
        system location by its role, whatever its case (``label:DRAFT``), a
        folder of the person's own by its name (``test_mail_folders``)."""
        _, folder = convert_imap_query(query)
        assert folder == expected

    def test_the_star_is_the_flag_never_a_folder(self) -> None:
        criteria, folder = convert_imap_query("label:starred")
        assert folder is None
        assert "FLAGGED" in str(criteria)

    def test_date_range(self) -> None:
        """after: and before: parse dates correctly."""
        criteria, _ = convert_imap_query("after:2024/01/01 before:2024-12-31")
        criteria_str = str(criteria)
        assert "2024" in criteria_str

    @pytest.mark.parametrize(
        ("query", "criterion"),
        [
            # 2026-10-20T13:20:00Z and 2026-10-27T13:20:00Z, as Gmail spells instants.
            ("after:1792502400", "SINCE 20-Oct-2026"),
            ("before:1793107200", "BEFORE 28-Oct-2026"),
            # Exactly midnight: the bound already is a day.
            ("before:1793059200", "BEFORE 27-Oct-2026"),
            ("-after:1792502400", "BEFORE 21-Oct-2026"),
            ("-before:1793107200", "SINCE 27-Oct-2026"),
        ],
    )
    def test_an_instant_widens_to_the_whole_day_that_holds_it(
        self, query: str, criterion: str
    ) -> None:
        """IMAP searches by day. The discussion source sends ``after:``/``before:``
        as epoch seconds, which used to read as no date at all: the search became
        ``(ALL)`` and returned another period under the requested window's name."""
        criteria, _ = convert_imap_query(query)
        assert str(criteria) == f"({criterion})"

    def test_bare_text(self) -> None:
        """Bare text (no operator) becomes full-text search."""
        criteria, folder = convert_imap_query("important documents")
        assert folder is None
        assert "important documents" in str(criteria)


@pytest.mark.unit
class TestANegation:
    """A negated operator used to be STRIPPED: « my mails, not the newsletter »
    listed the newsletter too (2026-10-13). IMAP states every negation the
    positive form has: ``NOT`` for people and subjects, the other side of a
    date, the opposite flag."""

    @pytest.mark.parametrize(
        ("query", "criterion"),
        [
            ("-from:bob@example.com", 'NOT (FROM "bob@example.com")'),
            ("-to:bob@example.com", 'NOT (TO "bob@example.com")'),
            ("-cc:alice", 'NOT (CC "alice")'),
            ("-subject:promo", 'NOT (SUBJECT "promo")'),
            ("-after:2026/10/01", "BEFORE 1-Oct-2026"),
            ("-before:2026/10/01", "SINCE 1-Oct-2026"),
            ("-label:starred", "UNFLAGGED"),
            ("-is:starred", "UNFLAGGED"),
        ],
    )
    def test_each_negation_is_a_criterion(self, query: str, criterion: str) -> None:
        criteria, folder = convert_imap_query(query)

        assert criterion in str(criteria)
        assert folder is None

    def test_a_read_state_is_its_opposite(self) -> None:
        unread, _ = convert_imap_query("-is:read")
        read, _ = convert_imap_query("-is:unread")

        assert "UNSEEN" in str(unread)
        assert "SEEN" in str(read) and "UNSEEN" not in str(read)

    def test_a_negation_keeps_the_rest_of_the_query(self) -> None:
        criteria, _ = convert_imap_query("report is:unread -from:shop")

        text = str(criteria)
        assert 'NOT (FROM "shop")' in text
        assert "UNSEEN" in text
        assert '"report"' in text

    def test_another_folder_is_excluded_by_reading_one(self) -> None:
        query = parse_imap_query("in:inbox -in:sent")

        assert query.folder == "inbox"
        assert query.excludes_its_folder is False

    @pytest.mark.parametrize("query", ["-in:inbox", "in:trash -in:Trash", "-label:INBOX"])
    def test_excluding_the_folder_read_is_said(self, query: str) -> None:
        assert parse_imap_query(query).excludes_its_folder is True

    def test_an_excluded_folder_never_reaches_the_text(self) -> None:
        criteria, folder = convert_imap_query("-in:spam report")

        assert folder is None
        assert "spam" not in str(criteria).lower()
