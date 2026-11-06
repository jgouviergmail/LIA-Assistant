"""How a body's links reach the text (ADR-287).

The reader and the model read the same ``[link](url)`` form: a link written
twice is a defect both meet, on every long tracking address of a newsletter.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.clients.normalizers.html_text import html_to_text

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
