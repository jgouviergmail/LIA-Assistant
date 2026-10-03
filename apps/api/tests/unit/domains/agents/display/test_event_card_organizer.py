"""The organizer line and the description of an event card, as the card draws them."""

from __future__ import annotations

import time

import pytest

from src.core.i18n_drafts import label_separator
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext, compact_html
from src.domains.agents.display.components.event_card import EventCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("fr", "Organisé par Alice"),
        ("en", "Organized by Alice"),
        ("es", "Organizado por Alice"),
        ("de", "Organisiert von Alice"),
        ("it", "Organizzato da Alice"),
        ("zh-CN", "组织者：Alice"),
    ],
)
def test_the_name_sits_where_its_language_puts_it(language: str, expected: str) -> None:
    """« 由……组织 » read before the name said « organised by …… Alice », and
    « 组织者 » joined by a space was a label without its colon."""
    template = V3Messages.get_organized_by(language)

    assert template.format(name="Alice", separator=label_separator(language)) == expected


def test_a_label_joins_its_name_through_the_separator() -> None:
    """« 组织者：{name} » written as a literal drew the same card and escaped
    the one door the label punctuation goes through (``label_separator``)."""
    template = V3Messages.get_organized_by("zh-CN")

    assert template.format(name="Alice", separator="|") == "组织者|Alice"


def _event(**over: object) -> dict[str, object]:
    return {
        "summary": "Point",
        "start": {"dateTime": "2026-09-28T10:00:00Z"},
        "end": {"dateTime": "2026-09-28T11:00:00Z"},
        **over,
    }


@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("fr", 'Organisé par <a href="mailto:o{0}@example.com">Team {x} {0}</a>'),
        ("zh-CN", '组织者：<a href="mailto:o{0}@example.com">Team {x} {0}</a>'),
    ],
)
def test_the_card_draws_the_organizer_line_braces_and_all(language: str, line: str) -> None:
    """The template is formatted, never the name: braces in a name or an
    address are drawn as typed — and the address keeps the space before it
    through the card's compaction, which removes whitespace between two tags."""
    organizer = {"displayName": "Team {x} {0}", "email": "o{0}@example.com"}

    html = compact_html(
        EventCard().render(_event(organizer=organizer), RenderContext(language=language))
    )

    assert line in html
    assert "> o{0}@example.com</span>" in html


def test_the_complete_description_loses_its_tags_before_display() -> None:
    """The details retain the tail, without exposing any provider HTML tag."""
    description = "mot " * 74 + '<a href="https://example.com/a/long/path">lien</a> et la suite'

    html = EventCard().render(_event(description=description), RenderContext(language="fr"))

    assert "&lt;a" not in html
    assert "mot mot" in html
    assert "lien et la suite" in html


def _description(description: str) -> str:
    return EventCard().render(_event(description=description), RenderContext(language="fr"))


def test_a_long_description_is_complete_and_layout_runs_are_folded() -> None:
    html = _description("abcd\n" * 59 + "longword")

    assert "abcd " * 59 + "longword" in html


def test_a_description_reads_its_entities_and_drops_its_style() -> None:
    """It showed « P {margin-top:0;} » and « &amp;nbsp; » on the card."""
    html = _description(
        "<style>p {margin-top:0}</style><p>Réunion&nbsp;d&#x27;équipe &amp; budget</p>"
    )

    assert "Réunion\xa0d&#x27;équipe &amp; budget" in html
    assert "margin" not in html


def test_a_layout_run_of_spaces_folds_and_typography_stays() -> None:
    """A dozen no-break spaces are layout, folded to one; one before a colon
    is French, and stays even when a removed tag leaves a space beside it."""
    html = _description("Point" + "\xa0" * 12 + "important\xa0: budget")
    beside_a_tag = _description("<b>Ordre du jour</b>&nbsp;: budget")

    assert "Point\xa0important\xa0: budget" in html
    assert "Ordre du jour\xa0: budget" in beside_a_tag


@pytest.mark.parametrize(
    ("description", "shown"),
    [
        ("<b>Attention</b>\u202f! budget", "Attention\u202f! budget"),
        ("<b>1</b>\u2007000 euros", "1\u2007000 euros"),
        ("<b>会议</b>\u3000议程", "会议\u3000议程"),
        ("<p>Intro</p><p>&nbsp;</p><p>Suite</p>", "Intro Suite"),
    ],
    ids=["narrow_no_break", "figure", "ideographic", "empty_paragraph"],
)
def test_a_typographic_space_touching_the_text_stays_and_layout_folds(
    description: str, shown: str
) -> None:
    """The narrow no-break space of « ! », the figure space of « 1 000 » and an
    ideographic space stay beside a removed tag; an empty paragraph is layout
    (review 14: it drew « Intro\\xa0Suite »)."""
    assert shown in _description(description)


@pytest.mark.parametrize(
    ("description", "shown", "hidden"),
    [
        ("<style><!-- div > p {margin:0} --></style>Réunion", "Réunion", "margin"),
        ("<script>if (a<b) {x()}</script>Réunion", "Réunion", "x()"),
        ("<STYLE>p {margin:0}</STYLE>Réunion", "Réunion", "margin"),
        ("Réunion<style>p {margin:0}", "Réunion", "margin"),
        ("Réunion<br>Ordre", "Réunion Ordre", "RéunionOrdre"),
        ("Code &lt;b&gt;x&lt;/b&gt;", "Code &lt;b&gt;x&lt;/b&gt;", "Code x"),
        ("Réunion<style>p {margin:0}</style>Ordre", "Réunion Ordre", "RéunionOrdre"),
        (
            "Voir</script> ci-dessous<script>x()</script> la suite",
            "Voir ci-dessous la suite",
            "ci-dessous ci-dessous",
        ),
        ("<style>p {margin:0}</style foo>Réunion", "Réunion", "margin"),
        ("Avant<!-- a > b -->Après", "Avant Après", "b --"),
        # `--!>` ends a comment for the HTML parser too (a recovered parse
        # error): read as still open, it hid « Après » (CodeQL py/bad-tag-filter).
        ("Avant<!-- a --!>Après", "Avant Après", "a --"),
        ("<head><title>Invitation</title></head>Réunion", "Réunion", "Invitation"),
    ],
    ids=[
        "style_holding_a_bracket",
        "script_holding_a_bracket",
        "uppercase_style",
        "unclosed_style",
        "a_tag_between_two_words",
        "entities_after_the_tags",
        "one_space_where_a_block_was",
        "a_closing_before_its_block_closes_nothing",
        "a_closing_tag_with_attributes",
        "a_comment_holding_a_bracket",
        "a_comment_closed_by_the_bang_form",
        "the_head_and_its_title",
    ],
)
def test_what_a_description_hides_stays_hidden(description: str, shown: str, hidden: str) -> None:
    """A block's content is CSS or code: it ends at its closing tag, never at
    the first « < » it holds, and a block left open drops the rest. A tag
    between two words leaves a space, and an entity is decoded after the tags
    are gone, so an escaped tag stays text."""
    html = _description(description)

    assert shown in html
    assert hidden not in html


def test_a_run_of_unclosed_brackets_is_read_in_linear_time() -> None:
    """The tag pattern restarted its scan at every « < »: 3.6 s for 100 000 of
    them, on the event loop. Linear, they take a few milliseconds."""
    started = time.perf_counter()
    _description("<" * 100_000)

    assert time.perf_counter() - started < 1.0


def test_an_unclosed_style_is_read_in_linear_time() -> None:
    """Each block's closing tag is searched once, from where the block opened."""
    started = time.perf_counter()
    _description("<style>" * 50_000)

    assert time.perf_counter() - started < 1.0


def test_an_unclosed_comment_is_read_in_linear_time() -> None:
    """A comment is a block too: its end is searched once, from where it opened."""
    started = time.perf_counter()
    _description("Avant" + "<!--" * 50_000)

    assert time.perf_counter() - started < 1.0
