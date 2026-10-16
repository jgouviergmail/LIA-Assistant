"""Who an outgoing e-mail is addressed to, read once for every road (ADR-344).

Python's address parser is strict since 3.13: one stray separator turns a whole
field into ``('', '')`` — ``a@x.com,`` names nobody, ``a@x.com;b@x.com`` too —
and an unreadable address answers the same pair as an empty segment. Gmail's
encoder skipped such pairs (a recipient lost in silence) and Graph's builder
split on every comma (a display name holding one became two broken recipients).
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from time import perf_counter

import pytest

from src.infrastructure.email.recipients import (
    encode_recipients,
    parse_recipients,
    read_recipients,
    recipient_segments,
    same_recipients,
)

pytestmark = pytest.mark.unit


def test_unclosed_address_brackets_do_not_block_later_recipients() -> None:
    """Malformed provider/model input must not occupy the event loop quadratically."""
    field = "<" * 64_000 + ", safe@example.com"
    started = perf_counter()

    segments = recipient_segments(field)

    elapsed = perf_counter() - started
    assert segments == [("<" * 64_000, False), ("safe@example.com", True)]
    # A generous budget for the linear scan and Python's header parser; the
    # former overlapping regex takes seconds retrying an unclosed span.
    assert elapsed < 0.5


class TestParseRecipients:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("a@x.com, b@x.com", [("", "a@x.com"), ("", "b@x.com")]),
            (
                '"Durand, Paul" <paul@example.com>; bob@example.com',
                [("Durand, Paul", "paul@example.com"), ("", "bob@example.com")],
            ),
            ("a@x.com, ;  ,", [("", "a@x.com")]),
            ("Marie <marie@example.com>,", [("Marie", "marie@example.com")]),
            ('"Doe; John" <j@example.com>', [("Doe; John", "j@example.com")]),
            ('"Jo \\"JJ\\" Doe" <j@example.com>', [('Jo "JJ" Doe', "j@example.com")]),
            ("Élodie Exemple <elodie@example.com>", [("Élodie Exemple", "elodie@example.com")]),
            ("", []),
            ("  ", []),
        ],
    )
    def test_every_named_recipient_is_read(
        self, field: str, expected: list[tuple[str, str]]
    ) -> None:
        assert parse_recipients(field) == expected

    @pytest.mark.parametrize(
        "field",
        ["marie@", "Marie", '"Marie" <>', "a@x.com b@x.com", "user@example", "a@x.com, marie@"],
    )
    def test_a_recipient_that_cannot_be_read_is_refused_without_naming_it(self, field: str) -> None:
        with pytest.raises(ValueError) as refused:
            parse_recipients(field)

        assert "marie" not in str(refused.value).lower()


class TestReadRecipients:
    def test_a_received_header_keeps_every_readable_address(self) -> None:
        assert read_recipients("a@x.com, marie@, Paul <paul@example.com>; ") == [
            ("", "a@x.com"),
            ("Paul", "paul@example.com"),
        ]


class TestEncodeRecipients:
    def test_only_a_display_name_outside_ascii_is_encoded(self) -> None:
        assert encode_recipients(
            '"Élodie Exemple" <elodie@example.com>; Bob <bob@example.com>'
        ) == ("=?utf-8?q?=C3=89lodie_Exemple?= <elodie@example.com>, Bob <bob@example.com>")

    def test_the_addresses_stay_readable_once_written_in_a_header(self) -> None:
        message = MIMEMultipart()
        message["To"] = encode_recipients("Élodie Exemple <elodie@example.com>, bob@example.com")

        written = message.as_string()

        assert "<elodie@example.com>, bob@example.com" in written


class TestSameRecipients:
    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("Paul <paul@example.com>", "paul@example.com"),
            ("a@example.com, b@example.com", "B@Example.com; a@example.com"),
            (None, ""),
            ("Paul", "Paul"),
        ],
    )
    def test_the_same_people_are_the_same_recipients(
        self, left: str | None, right: str | None
    ) -> None:
        assert same_recipients(left, right)

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("paul@example.com", "anna@example.com"),
            ("paul@example.com", ""),
            ("Paul", "paul@example.com"),
            ("paul@example.com, Anna", "paul@example.com"),
        ],
    )
    def test_other_people_or_an_unreadable_field_are_a_change(
        self, left: str | None, right: str | None
    ) -> None:
        assert not same_recipients(left, right)
