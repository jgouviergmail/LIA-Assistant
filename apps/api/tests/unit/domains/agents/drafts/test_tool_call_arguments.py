"""A tool call's arguments are shown AS THEMSELVES to the person asked to allow it.

The card is what a person reads before a third-party tool runs (ADR-263), and
the arguments approved are replayed whole, so the card states every cut it
makes: what nobody sees is spelled out rather than padding a value out of
sight, markup a value carries is drawn as characters on every plain surface,
and the arguments left out are counted. Measured: seventy ideographic spaces
before an address left the card showing « to: … » (review 11); seventy
zero-width spaces did the same once the spaces were folded, and a value
spelled as a Markdown link read as a link to another host (review 12); a cut
on a word dropped a URL's host after « GET », and emphasis drew italics across
two argument names on Telegram (review 13).
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.plain_text import markdown_to_plain_text
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_confirmation_card
from src.domains.shared.markdown_literal import read_as_markdown
from src.infrastructure.channels.telegram.formatter import markdown_to_telegram_html

pytestmark = pytest.mark.unit

#: An argument dressed as a link to one address that goes to another.
_DISGUISED_LINK = "[https://paypal.com](https://evil.example/login)"

#: The same argument on a Markdown surface: characters, no link.
_DRAWN_AS_ITSELF = "&#91;https&#58;//paypal.com&#93;(https&#58;//evil.example/login)"


def _card_of(arguments: dict[str, object]) -> str:
    draft = Draft(
        type=DraftType.TOOL_CALL,
        content={"tool_name": "send_tool", "tool_label": "Send", "tool_args": arguments},
    )
    return render_confirmation_card(draft, "en")


def _card(value: object) -> str:
    return _card_of({"to": value})


def _shown(card: str) -> str:
    """What the chat shows: the card's references read as the chat reads them."""
    return read_as_markdown(card)


@pytest.mark.parametrize(
    "pad", [chr(0x3000), chr(0x2003), chr(0xA0)], ids=["ideographic", "em", "nbsp"]
)
def test_blank_padding_never_hides_an_argument(pad: str) -> None:
    assert "to: attacker@evil.example" in _shown(_card(pad * 70 + "attacker@evil.example"))


def test_invisible_padding_never_hides_an_argument() -> None:
    card = _card(chr(0x200B) * 70 + "attacker@evil.example")

    assert "to: ⟨U+200B×70⟩attacker@evil.example" in _shown(card)


def test_an_invisible_character_is_shown() -> None:
    assert "pay⟨U+200B⟩pal.example" in _card("pay" + chr(0x200B) + "pal.example")


def test_a_long_argument_is_cut_at_its_bound() -> None:
    """HEAD cut at 80 characters, then an ellipsis: 81. The ellipsis now counts
    in the bound, and the cut falls inside a token — data has no words to keep."""
    value = (
        "Envoyer le compte rendu détaillé de la réunion trimestrielle à toute "
        "l'équipe commerciale"
    )

    assert f"to: {value[:79]}…," in _card_of({"to": value, "cc": "x"})


def test_a_url_keeps_its_host_after_a_word() -> None:
    """Cut on a word, « GET https://evil.example/… » showed « GET… »."""
    card = _card("GET https://evil.example/" + "a" * 100)

    assert f"to: GET https://evil.example/{'a' * 54}…" in _shown(card)


def test_a_url_keeps_its_host_after_a_marker() -> None:
    """Cut on a word, two zero-width spaces showed their marker and nothing else."""
    card = _card(chr(0x200B) * 2 + "https://evil.example/" + "a" * 100)

    assert "to: ⟨U+200B×2⟩https://evil.example/aaa" in _shown(card)


def test_the_tool_s_label_and_an_argument_s_name_are_drawn_as_data() -> None:
    """The label is a third party's, and so is a name: spelled, like a value."""
    draft = Draft(
        type=DraftType.TOOL_CALL,
        content={
            "tool_name": "send_tool",
            "tool_label": "Se" + chr(0x200B) + "nd",
            "tool_args": {"t" + chr(0x200B) + "o": "x", "k" * 100: 1},
        },
    )

    card = render_confirmation_card(draft, "en")

    assert "Se⟨U+200B⟩nd" in card
    assert "t⟨U+200B⟩o: x" in card
    assert "k" * 79 + "…: 1" in card


def test_markup_in_a_value_is_drawn_as_itself() -> None:
    """Rendered, the value was a link reading « paypal.com » to another host."""
    assert _DRAWN_AS_ITSELF in _card(_DISGUISED_LINK)


def test_emphasis_in_a_value_is_drawn_as_itself() -> None:
    """« 2*3*4 » drew its 3 in italics."""
    card = _card("2*3*4 ~~x~~ __y__")

    assert "2&#42;3&#42;4 &#126;&#126;x&#126;&#126; &#95;&#95;y&#95;&#95;" in card


def test_the_ticket_reads_every_value_as_typed() -> None:
    """The ticket's flattener erased the marker, a value's tags and its
    emphasis, and turned a link into « label (url) »: every character now
    comes back as typed."""
    card = _card_of(
        {
            "to": "pay" + chr(0x200B) + "pal.example",
            "note": "<b>ok</b>",
            "link": _DISGUISED_LINK,
            "expr": "2*3*4 and __y__",
        }
    )

    ticket = markdown_to_plain_text(card)

    assert "to: pay⟨U+200B⟩pal.example" in ticket
    assert "note: <b>ok</b>" in ticket
    assert f"link: {_DISGUISED_LINK}" in ticket
    assert "expr: 2*3*4 and __y__" in ticket


def test_telegram_draws_no_link_from_a_value() -> None:
    """Telegram's HTML links through ``<a>`` alone: the brackets are characters."""
    telegram = markdown_to_telegram_html(_card(_DISGUISED_LINK))

    assert "<a href" not in telegram
    assert f"to: {_DISGUISED_LINK}" in telegram


def test_telegram_draws_no_italics_across_two_names() -> None:
    """``max_results: 10, page_token`` drew italics from one name to the next."""
    telegram = markdown_to_telegram_html(_card_of({"max_results": 10, "page_token": "abc"}))

    assert "<i>" not in telegram
    assert "max_results: 10, page_token: abc" in telegram


def test_an_argument_s_name_stays_on_its_row() -> None:
    """A name carrying a line break drew a row of its own, like the card's."""
    card = _card_of({"to" + chr(10) + "- **Amount**: 1 EUR": "x"})

    rows = [line for line in card.splitlines() if line.startswith("- ")]
    assert len(rows) == 2  # the tool, then the details


def test_the_arguments_left_out_are_counted() -> None:
    """The approval replays every argument: the card says how many it left out."""
    card = _card_of({f"arg{index}": index for index in range(8)})

    assert "arg5: 5, … (+2)" in card
    assert "arg6" not in card
