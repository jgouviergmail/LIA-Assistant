"""How a body's links reach the text (ADR-287).

The reader and the model read the same ``[link](url)`` form: a link written
twice is a defect both meet, on every long tracking address of a newsletter.
"""

from __future__ import annotations

import pytest

from src.core.constants import EMAIL_HTML_TEXT_MAX_CHARS
from src.domains.connectors.clients.normalizers.html_text import html_to_text, shown_words

pytestmark = pytest.mark.unit

LONG = "https://example.org/" + "a" * 120


def test_a_long_link_behind_words_is_written_once() -> None:
    text = html_to_text(f'<p>Read <a href="{LONG}">this</a></p>', url_shorten_threshold=60)

    assert text == f"Read this [link]({LONG})"


def test_a_long_bare_address_is_shortened_once() -> None:
    text = html_to_text(f"<p>See {LONG} now</p>", url_shorten_threshold=60)

    assert text == f"See [link]({LONG}) now"


def test_a_short_bare_address_stays_as_written() -> None:
    text = html_to_text("<p>See https://example.org/a now</p>", url_shorten_threshold=60)

    assert text == "See https://example.org/a now"


def test_a_link_holding_brackets_is_written_once() -> None:
    tracked = f"{LONG}?filter[year]=2026"

    text = html_to_text(f'<p><a href="{tracked}">Read</a></p>', url_shorten_threshold=60)

    assert text == f"Read [link]({tracked})"


def test_an_address_inside_a_link_stays_inside_it() -> None:
    tracked = f"https://click.example.org/?to={LONG}"

    text = html_to_text(f'<p><a href="{tracked}">Read</a></p>', url_shorten_threshold=60)

    assert text == f"Read [link]({tracked})"


# What a reader of a message reads (ADR-287 amendment 2026-11-15): the words its layout shows.

INVITATION = "<table><tr><td><h1>Board meeting</h1><p>Thursday 20 November, 14:00</p></td></tr>"
#: What a mailer writes as the text part beside such a layout: nothing of the event.
TEXT_PART = "To view this email, open it in a client that shows HTML."


def test_the_layout_holding_words_is_read_over_the_text_part() -> None:
    assert shown_words(TEXT_PART, INVITATION) == "Board meeting\n\nThursday 20 November, 14:00"


def test_a_layout_holding_no_words_leaves_the_text_part() -> None:
    assert shown_words(TEXT_PART, '<img src="https://example.org/banner.png">') == TEXT_PART


def test_a_text_part_that_is_markup_is_read_as_text() -> None:
    assert shown_words("<p>Hello <b>you</b></p>", None) == "Hello you"


def test_a_text_part_alone_is_read_as_written() -> None:
    assert shown_words("Hello <you>, 3 < 4", None) == "Hello <you>, 3 < 4"


def test_the_layout_is_cut_before_it_is_parsed() -> None:
    filler = "<p>" + "word " * (EMAIL_HTML_TEXT_MAX_CHARS // 5) + "</p>"

    words = shown_words(TEXT_PART, filler + "<p>PAST THE CEILING</p>")

    assert words.startswith("word word")
    assert "PAST THE CEILING" not in words
