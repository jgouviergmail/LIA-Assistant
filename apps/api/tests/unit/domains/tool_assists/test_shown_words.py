"""What LIA reads of a message is what its reader shows (owner, 2026-11-14).

A message the Tools draw in its original layout is asked about as that layout: its HTML turned to
text by the one door every mailbox uses, whole, never the text part a sender wrote beside it. A
message with no HTML keeps the mailbox's text, itself turned to text when it was markup sent as
text. Measured in production on 2026-11-14: « make it an event » on HTML mail read a nearly empty
body (556 tokens in all, the instructions included) and found nothing.
"""

from __future__ import annotations

import threading

import pytest

from src.core.constants import EMAIL_HTML_TEXT_MAX_CHARS
from src.domains.connectors.clients.normalizers import html_text
from src.domains.tool_assists.shown_words import words_as_shown

pytestmark = pytest.mark.unit

INVITATION_HTML = (
    "<html><head><style>.cta{color:#fff}</style></head><body>"
    "<div class='preheader'>Your invitation</div>"
    "<table><tr><td><h1>Board meeting</h1>"
    "<p>Thursday 20 November 2026, 14:00 - 16:00</p>"
    "<p>Room Galilée, 12 rue des Lilas, Lyon</p></td></tr></table></body></html>"
)
#: What a mailer wrote as the text part beside it: nothing of the event.
TEXT_PART = "To view this email, open it in a client that shows HTML."


class _Mailbox:
    """A mailbox that holds a message's HTML, or none."""

    def __init__(self, html: str | None) -> None:
        self.html = html
        self.asked: list[str] = []

    async def get_message_html(self, message_id: str) -> str | None:
        self.asked.append(message_id)
        return self.html


async def test_a_message_with_an_original_layout_is_read_as_that_layout() -> None:
    mailbox = _Mailbox(INVITATION_HTML)

    words = await words_as_shown(mailbox, "m1", TEXT_PART)

    assert mailbox.asked == ["m1"]
    assert "Board meeting" in words
    assert "Thursday 20 November 2026, 14:00 - 16:00" in words
    assert "Room Galilée, 12 rue des Lilas, Lyon" in words
    assert "To view this email" not in words, "the text part a sender wrote beside it is not read"
    assert "color:#fff" not in words and "<" not in words, "never the markup"


async def test_a_message_with_no_layout_keeps_the_mailbox_s_text() -> None:
    words = await words_as_shown(_Mailbox(None), "m1", "Lunch Thursday at noon?")

    assert words == "Lunch Thursday at noon?"


async def test_a_layout_with_no_words_keeps_the_mailbox_s_text() -> None:
    picture_only = (
        "<html><body><img src='cid:poster'><table><tr><td></td></tr></table></body></html>"
    )

    words = await words_as_shown(_Mailbox(picture_only), "m1", "The poster is attached.")

    assert words == "The poster is attached."


async def test_markup_sent_as_text_is_read_as_text() -> None:
    sent_as_text = "<div><p>Dinner <b>Friday</b> at 8 pm</p><br><p>Chez Marcel</p></div>"

    words = await words_as_shown(_Mailbox(None), "m1", sent_as_text)

    assert "Dinner Friday at 8 pm" in words and "Chez Marcel" in words
    assert "<" not in words


@pytest.mark.parametrize(
    "prose",
    ["if x<a and b>c then stop", "count<b et total>i", "Price < 10 € > nothing"],
)
async def test_prose_that_merely_holds_angle_brackets_is_left_as_written(prose: str) -> None:
    assert await words_as_shown(_Mailbox(None), "m1", prose) == prose


async def test_a_layout_is_turned_to_text_up_to_its_ceiling_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turned: list[tuple[int, bool]] = []
    loop_thread = threading.get_ident()

    def spy(html: str) -> str:
        turned.append((len(html), threading.get_ident() != loop_thread))
        return "words"

    monkeypatch.setattr(html_text, "html_to_text", spy)

    words = await words_as_shown(_Mailbox("<p>x</p>" * EMAIL_HTML_TEXT_MAX_CHARS), "m1", TEXT_PART)

    assert words == "words"
    assert turned == [(EMAIL_HTML_TEXT_MAX_CHARS, True)]


async def test_an_empty_text_and_no_layout_stays_empty() -> None:
    assert await words_as_shown(_Mailbox(None), "m1", "") == ""
