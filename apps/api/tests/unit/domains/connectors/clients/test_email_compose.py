"""What a reply or a forward says, whatever the mailbox (ADR-344).

Gmail and IMAP compose their replies by hand, and a reply saved as a mailbox
draft must be the message sending it would have sent. Before this module,
Gmail's « reply all » dropped every other recipient of the original, and
Apple's compared raw header text, so the person was copied on their own reply
whenever the original named them with a display name.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.clients.email_compose import (
    forward_subject,
    forwarded_body,
    quoted_reply,
    reply_recipients,
    reply_subject,
)

pytestmark = pytest.mark.unit

PAUL = "Paul Durand <paul@example.com>"
ME = "me@example.com"


class TestReplyRecipients:
    @pytest.mark.parametrize("reply_all", [False, True])
    def test_the_reply_address_replaces_the_sender_and_is_deduplicated(
        self, reply_all: bool
    ) -> None:
        to, cc = reply_recipients(
            PAUL,
            f"{ME}, help@example.com, marie@example.com",
            "HELP@example.com, anne@example.com",
            own_address=ME,
            reply_all=reply_all,
            reply_to="Help <help@example.com>",
        )

        assert to == (
            "Help <help@example.com>, marie@example.com" if reply_all else "Help <help@example.com>"
        )
        assert cc == ("anne@example.com" if reply_all else "")

    def test_a_reply_to_ones_own_message_still_answers_its_recipients(self) -> None:
        assert reply_recipients(
            ME,
            "marie@example.com",
            "",
            own_address=ME,
            reply_all=False,
            reply_to="help@example.com",
        ) == ("marie@example.com", "")

    def test_a_persons_override_has_priority_over_reply_to(self) -> None:
        assert reply_recipients(
            PAUL,
            ME,
            "",
            own_address=ME,
            reply_all=False,
            override_to="chosen@example.com",
            reply_to="help@example.com",
        ) == ("chosen@example.com", "")

    def test_a_reply_goes_to_the_sender_alone(self) -> None:
        assert reply_recipients(
            PAUL, f"{ME}, marie@example.com", "anne@example.com", own_address=ME, reply_all=False
        ) == (PAUL, "")

    def test_a_reply_to_all_answers_every_other_recipient_where_they_were(self) -> None:
        assert reply_recipients(
            PAUL,
            f"Moi <{ME}>, Marie Exemple <marie@example.com>",
            "anne@example.com",
            own_address=ME,
            reply_all=True,
        ) == (f"{PAUL}, Marie Exemple <marie@example.com>", "anne@example.com")

    def test_the_person_is_never_a_recipient_whatever_the_case_or_name(self) -> None:
        assert reply_recipients(
            PAUL,
            "Moi Exemple <Me@Example.COM>",
            f"Moi <{ME}>, anne@example.com",
            own_address=ME,
            reply_all=True,
        ) == (PAUL, "anne@example.com")

    def test_a_display_name_holding_a_comma_stays_one_recipient(self) -> None:
        _to, cc = reply_recipients(
            PAUL, ME, '"Exemple, Anne" <anne@example.com>', own_address=ME, reply_all=True
        )

        assert cc == '"Exemple, Anne" <anne@example.com>'

    def test_a_recipient_named_twice_is_answered_once(self) -> None:
        assert reply_recipients(
            PAUL,
            f"{ME}, marie@example.com",
            "Marie <MARIE@example.com>, paul@example.com",
            own_address=ME,
            reply_all=True,
        ) == (f"{PAUL}, marie@example.com", "")

    def test_a_reply_to_ones_own_message_answers_its_recipients(self) -> None:
        sender = f"Moi <{ME}>"

        assert reply_recipients(
            sender, "marie@example.com", "anne@example.com", own_address=ME, reply_all=False
        ) == ("marie@example.com", "")
        assert reply_recipients(
            sender, "marie@example.com", "anne@example.com", own_address=ME, reply_all=True
        ) == ("marie@example.com", "anne@example.com")

    def test_a_note_to_oneself_is_answered_to_oneself(self) -> None:
        assert reply_recipients(ME, ME, "", own_address=ME, reply_all=True) == (ME, "")

    def test_an_unknown_own_address_excludes_nobody_but_the_sender(self) -> None:
        assert reply_recipients(PAUL, ME, "paul@example.com", own_address=None, reply_all=True) == (
            f"{PAUL}, {ME}",
            "",
        )

    def test_a_chosen_recipient_replaces_the_answered_ones_and_keeps_the_copies(self) -> None:
        assert reply_recipients(
            PAUL,
            f"{ME}, marie@example.com",
            f"{ME}, anne@example.com",
            own_address=ME,
            reply_all=True,
            override_to="marie@example.com",
        ) == ("marie@example.com", "anne@example.com")


class TestSubjectsAndBodies:
    @pytest.mark.parametrize(
        ("subject", "expected"),
        [("Budget", "Re: Budget"), ("RE: Budget", "RE: Budget"), ("", "Re: ")],
    )
    def test_a_reply_subject_is_prefixed_once(self, subject: str, expected: str) -> None:
        assert reply_subject(subject) == expected

    @pytest.mark.parametrize(
        ("subject", "expected"), [("Budget", "Fwd: Budget"), ("FWD: Budget", "FWD: Budget")]
    )
    def test_a_forward_subject_is_prefixed_once(self, subject: str, expected: str) -> None:
        assert forward_subject(subject) == expected

    def test_a_plain_reply_quotes_the_original_below_its_words(self) -> None:
        assert quoted_reply(
            "Ok.", "Line 1\nLine 2\n", date="Mon, 12 Oct 2026", sender=PAUL, is_html=False
        ) == (f"Ok.\n\nOn Mon, 12 Oct 2026, {PAUL} wrote:\n> Line 1\n> Line 2")

    @pytest.mark.parametrize(("original", "is_html"), [("", False), ("Line", True)])
    def test_nothing_is_quoted_without_a_plain_original(self, original: str, is_html: bool) -> None:
        assert quoted_reply("Ok.", original, date="d", sender=PAUL, is_html=is_html) == "Ok."

    def test_a_forward_carries_the_original_headers_and_body(self) -> None:
        assert forwarded_body(None, "Body", sender=PAUL, date="d", subject="Budget", to=ME) == (
            "\n\n---------- Forwarded message ---------\n"
            f"From: {PAUL}\nDate: d\nSubject: Budget\nTo: {ME}\n\nBody"
        )
