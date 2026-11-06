"""Editing a mailbox draft changes what was asked, and nothing else (ADR-344).

Gmail replaces a draft's whole message and IMAP stores a new one: an edit built
from the fields alone would drop the files a forward carries and the headers
that keep a reply in its thread. The editor rewrites the RAW message instead.
"""

from __future__ import annotations

import email
from collections.abc import Awaitable, Callable
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from src.core.exceptions import AuthenticationError, ConnectorAPIError, ExternalServiceError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    TRASH_REFUSED,
    TRASH_UNAVAILABLE,
    MailboxDraftNotFoundError,
    edit_draft_message,
    parse_message,
    prepare_for_smtp,
    trash_each,
)
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = pytest.mark.unit

FILE = OutgoingAttachment("note.txt", "text/plain", b"hello")

PDF = b"%PDF-1.4 minimal"


def _draft(*, html: bool = False, with_file: bool = False) -> bytes:
    message = EmailMessage()
    message["From"] = "me@example.com"
    message["To"] = "Paul <paul@example.com>"
    message["Cc"] = "anne@example.com"
    message["Subject"] = "Re: Budget"
    message["In-Reply-To"] = "<orig-1@example.com>"
    message["References"] = "<orig-1@example.com>"
    message.set_content("Old words.\n\nOn Mon, Paul wrote:\n> Budget?")
    if html:
        message.add_alternative("<p>Old words.</p>", subtype="html")
    if with_file:
        message.add_attachment(PDF, maintype="application", subtype="pdf", filename="budget.pdf")
    return message.as_bytes()


def _parse(raw: bytes) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(parsed, EmailMessage)
    return parsed


def _text(message: EmailMessage) -> str:
    body = message.get_body(preferencelist=("plain",))
    assert body is not None
    return str(body.get_content())


class TestAFormattedBody:
    def test_it_replaces_the_words_as_html_keeping_the_files(self) -> None:
        edited = edit_draft_message(_draft(with_file=True), body="<b>New</b>", is_html=True)

        body = edited.get_body(preferencelist=("html",))
        assert body is not None and body.get_content().strip() == "<b>New</b>"
        assert edited.get_body(preferencelist=("plain",)) is None
        assert [part.get_filename() for part in edited.iter_attachments()]

    def test_text_stays_text(self) -> None:
        edited = edit_draft_message(_draft(), body="New")

        assert edited.get_body(preferencelist=("plain",)) is not None


class TestAFile:
    """Files go by name: the one handle every provider keeps from one read to the next."""

    def _message(self, *names: str) -> bytes:
        message = EmailMessage()
        message["To"] = "paul@example.com"
        message["In-Reply-To"] = "<orig@example.com>"
        message.set_content("Words.")
        for name in names:
            message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename=name)
        return message.as_bytes()

    def _files(self, message: EmailMessage) -> list[str | None]:
        return [part.get_filename() for part in message.iter_attachments()]

    def test_one_joins_a_message_that_had_none(self) -> None:
        edited = edit_draft_message(self._message(), add_files=[FILE])

        assert self._files(edited) == ["note.txt"]
        assert edited["In-Reply-To"] == "<orig@example.com>"
        body = edited.get_body(preferencelist=("plain",))
        assert body is not None and body.get_content().strip() == "Words."

    def test_its_bytes_and_type_are_kept(self) -> None:
        edited = edit_draft_message(self._message(), add_files=[FILE])

        (part,) = edited.iter_attachments()
        assert part.get_content_type() == "text/plain"
        assert part.get_payload(decode=True) == b"hello"

    def test_a_name_with_accents_survives(self) -> None:
        accented = OutgoingAttachment("résumé.pdf", "application/pdf", b"%PDF")

        edited = edit_draft_message(self._message(), add_files=[accented])

        assert self._files(parse_message(edited.as_bytes())) == ["résumé.pdf"]

    def test_one_joins_those_already_there(self) -> None:
        edited = edit_draft_message(self._message("a.pdf"), add_files=[FILE])

        assert self._files(edited) == ["a.pdf", "note.txt"]

    def test_one_leaves_by_its_name_the_others_stay(self) -> None:
        edited = edit_draft_message(self._message("a.pdf", "b.pdf"), remove_files=["a.pdf"])

        assert self._files(edited) == ["b.pdf"]

    def test_a_name_takes_one_file_when_two_share_it(self) -> None:
        edited = edit_draft_message(self._message("a.pdf", "a.pdf"), remove_files=["a.pdf"])

        assert self._files(edited) == ["a.pdf"]

    def test_a_name_the_message_does_not_hold_changes_nothing(self) -> None:
        edited = edit_draft_message(self._message("a.pdf"), remove_files=["gone.pdf"])

        assert self._files(edited) == ["a.pdf"]

    def test_the_last_one_gone_leaves_the_words(self) -> None:
        edited = edit_draft_message(self._message("a.pdf"), remove_files=["a.pdf"])

        reread = parse_message(edited.as_bytes())
        assert self._files(reread) == []
        body = reread.get_body(preferencelist=("plain",))
        assert body is not None and body.get_content().strip() == "Words."

    def test_new_words_and_files_go_together(self) -> None:
        edited = edit_draft_message(
            self._message("a.pdf"), body="New.", add_files=[FILE], remove_files=["a.pdf"]
        )

        assert self._files(edited) == ["note.txt"]
        body = edited.get_body(preferencelist=("plain",))
        assert body is not None and body.get_content().strip() == "New."


class TestEditDraftMessage:
    def test_headers_given_replace_their_value_and_the_others_stay(self) -> None:
        edited = _parse(edit_draft_message(_draft(), to="Marie <marie@example.com>").as_bytes())

        assert edited["To"] == "Marie <marie@example.com>"
        assert edited["Cc"] == "anne@example.com"
        assert edited["Subject"] == "Re: Budget"
        assert edited["In-Reply-To"] == "<orig-1@example.com>"
        assert edited["References"] == "<orig-1@example.com>"

    def test_an_empty_header_value_removes_it(self) -> None:
        edited = _parse(edit_draft_message(_draft(), cc="").as_bytes())

        assert edited["Cc"] is None

    def test_a_new_body_keeps_the_files(self) -> None:
        edited = _parse(edit_draft_message(_draft(with_file=True), body="New words.").as_bytes())

        assert _text(edited).strip() == "New words."
        files = [(part.get_filename(), part.get_content()) for part in edited.iter_attachments()]
        assert files == [("budget.pdf", PDF)]

    def test_a_header_edit_leaves_the_body_untouched(self) -> None:
        edited = _parse(edit_draft_message(_draft(html=True), subject="Budget 2027").as_bytes())

        assert edited.get_body(preferencelist=("html",)) is not None
        assert _text(edited).startswith("Old words.")

    def test_a_new_body_replaces_an_html_alternative_with_plain_text(self) -> None:
        edited = _parse(edit_draft_message(_draft(html=True), body="New words.").as_bytes())

        assert edited.get_body(preferencelist=("html",)) is None
        assert _text(edited).strip() == "New words."

    def test_a_rewritten_body_travels_in_seven_bits(self) -> None:
        """Every road takes it: Gmail's upload, an IMAP APPEND, an SMTP send."""
        edited = edit_draft_message(_draft(), body="Déjà vu — 你好")

        assert edited.as_bytes().isascii()
        assert _text(_parse(edited.as_bytes())).strip() == "Déjà vu — 你好"

    def test_non_ascii_headers_and_body_survive_the_round_trip(self) -> None:
        edited = edit_draft_message(
            _draft(), to="Élodie Exemple <elodie@example.com>", subject="Été", body="Déjà vu"
        )

        reparsed = _parse(edited.as_bytes())
        assert reparsed["To"] == "Élodie Exemple <elodie@example.com>"
        assert reparsed["Subject"] == "Été"
        assert _text(reparsed).strip() == "Déjà vu"


class TestPrepareForSmtp:
    def test_every_recipient_is_returned_once_and_the_bcc_header_is_gone(self) -> None:
        stored = (
            b"To: Paul <paul@example.com>, marie@example.com\r\n"
            b"Cc: anne@example.com; MARIE@example.com\r\n"
            b"Bcc: =?utf-8?q?Le_Ch=C3=A8f?= <boss@example.com>\r\n"
            b"Subject: Hello\r\n\r\nBody\r\n"
        )
        message = email.message_from_bytes(stored)

        recipients = prepare_for_smtp(message)

        assert recipients == [
            "paul@example.com",
            "marie@example.com",
            "anne@example.com",
            "boss@example.com",
        ]
        assert message["Bcc"] is None
        assert b"boss@example.com" not in message.as_bytes()

    def test_a_recipient_that_cannot_be_read_stops_the_send(self) -> None:
        message = email.message_from_bytes(b"To: marie@\r\n\r\nBody\r\n")

        with pytest.raises(ValueError):
            prepare_for_smtp(message)


class TestTrashEach:
    """A batch says what became of EVERY draft, never only that it ended."""

    @staticmethod
    def _trasher(
        outcomes: dict[str, Exception | None],
    ) -> tuple[list[str], Callable[[str], Awaitable[None]]]:
        tried: list[str] = []

        async def trash_one(draft_id: str) -> None:
            tried.append(draft_id)
            outcome = outcomes.get(draft_id)
            if outcome is not None:
                raise outcome

        return tried, trash_one

    async def test_each_draft_is_reported_once_with_its_outcome(self) -> None:
        tried, trash_one = self._trasher(
            {
                "gone": MailboxDraftNotFoundError("gone"),
                "bad": ConnectorAPIError(connector_type="x", status_code=400, detail="no"),
            }
        )

        result = await trash_each(["a", "gone", "a", "bad", "b"], trash_one)

        assert tried == ["a", "gone", "bad", "b"]
        assert result == {
            "trashed": ["a", "b"],
            "failed": [
                {FIELD_MAILBOX_DRAFT_ID: "gone", "status": TRASH_NOT_FOUND},
                {FIELD_MAILBOX_DRAFT_ID: "bad", "status": TRASH_REFUSED},
            ],
        }

    async def test_a_mailbox_that_stops_answering_ends_the_batch_and_says_so(self) -> None:
        tried, trash_one = self._trasher(
            {"b": ExternalServiceError(service_name="x", detail="down")}
        )

        result = await trash_each(["a", "b", "c"], trash_one)

        assert tried == ["a", "b"]
        assert result == {
            "trashed": ["a"],
            "failed": [
                {FIELD_MAILBOX_DRAFT_ID: "b", "status": TRASH_UNAVAILABLE},
                {FIELD_MAILBOX_DRAFT_ID: "c", "status": TRASH_UNAVAILABLE},
            ],
        }

    async def test_a_failure_before_anything_was_trashed_is_raised(self) -> None:
        _tried, trash_one = self._trasher(
            {"a": AuthenticationError(detail="reconnect", connector_type="x")}
        )

        with pytest.raises(AuthenticationError):
            await trash_each(["a", "b"], trash_one)
