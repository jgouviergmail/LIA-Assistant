"""A long AI synthesis is folded behind « see more », never drawn whole.

The web-search card and the Perplexity answer card each rendered the whole
synthesis — up to the search model's output budget, several thousand
characters — inside one card. The fold is deterministic (no model call): a
lead of whole paragraphs under a published budget, the rest inside the
native collapsible every other card already uses.
"""

from __future__ import annotations

import pytest

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.folded_synthesis import (
    format_synthesis_html,
    render_folded_synthesis,
    split_lead,
)
from src.domains.agents.display.components.search_result_card import SearchResultCard
from src.domains.agents.display.components.web_search_card import WebSearchCard

pytestmark = pytest.mark.unit

PARAGRAPH = "Sentence one of the paragraph. Sentence two of the paragraph."


def _paragraphs(count: int) -> str:
    return "\n\n".join(f"P{i}. {PARAGRAPH}" for i in range(count))


# ============================================================================
# split_lead — the pure decision
# ============================================================================


def test_short_text_is_all_lead() -> None:
    lead, rest = split_lead(_paragraphs(2), preview_chars=1000)
    assert lead == _paragraphs(2)
    assert rest == ""


def test_lead_takes_whole_paragraphs_under_the_budget() -> None:
    text = _paragraphs(6)
    one = len(f"P0. {PARAGRAPH}")
    lead, rest = split_lead(text, preview_chars=one * 3 + 4)
    assert lead == "\n\n".join(text.split("\n\n")[:3])
    assert rest == "\n\n".join(text.split("\n\n")[3:])


def test_first_paragraph_always_leads_even_over_budget_when_no_sentence_fits() -> None:
    text = "A" * 500 + "\n\n" + "B" * 20
    lead, rest = split_lead(text, preview_chars=100)
    assert lead == "A" * 500
    assert rest == "B" * 20


def test_single_long_paragraph_is_cut_at_a_sentence_boundary() -> None:
    sentences = [f"Sentence number {i} says something useful." for i in range(20)]
    text = " ".join(sentences)
    lead, rest = split_lead(text, preview_chars=120)
    assert lead.endswith(".")
    assert len(lead) <= 120
    assert rest == text[len(lead) :].lstrip()
    assert lead + " " + rest == text


def test_split_is_lossless() -> None:
    text = _paragraphs(9)
    lead, rest = split_lead(text, preview_chars=200)
    assert (lead + "\n\n" + rest) == text


# ============================================================================
# format_synthesis_html — one formatter for both cards
# ============================================================================


def test_format_strips_reference_markers_and_escapes() -> None:
    html = format_synthesis_html("Bold **fact** [1] and <b>raw</b>")
    assert "[1]" not in html
    assert "<strong>fact</strong>" in html
    assert "&lt;b&gt;raw&lt;/b&gt;" in html


def test_format_paragraphs_and_line_breaks() -> None:
    assert format_synthesis_html("a\n\nb") == "<p>a</p><p>b</p>"
    assert format_synthesis_html("a\nb") == "a<br>b"


# ============================================================================
# render_folded_synthesis — the HTML shape
# ============================================================================


def test_short_synthesis_has_no_collapsible() -> None:
    html = render_folded_synthesis(_paragraphs(2), RenderContext(language="en"), preview_chars=1000)
    assert "lia-collapsible" not in html
    assert "<p>P0." in html


def test_long_synthesis_is_folded_behind_see_more_in_the_reader_language() -> None:
    ctx = RenderContext(language="de")
    html = render_folded_synthesis(_paragraphs(8), ctx, preview_chars=200)
    assert '<details class="lia-collapsible"' in html
    assert V3Messages.get_see_more("de") in html
    # The lead is drawn before the fold, the tail inside it.
    assert html.index("<p>P0.") < html.index("<details")
    assert html.index("<details") < html.index("P7.")
    # Nothing is drawn twice.
    assert html.count("P0.") == 1 and html.count("P7.") == 1


# ============================================================================
# The two cards read the setting and share the fold
# ============================================================================


@pytest.mark.parametrize(
    ("card", "payload"),
    [
        (WebSearchCard(), {"query": "q", "synthesis": _paragraphs(12), "sources_used": []}),
        (SearchResultCard(), {"query": "q", "answer": _paragraphs(12)}),
    ],
)
def test_cards_fold_a_long_synthesis(card: object, payload: dict[str, object]) -> None:
    html = card.render(payload, RenderContext(language="fr"))  # type: ignore[attr-defined]
    assert "lia-collapsible" in html
    assert V3Messages.get_see_more("fr") in html


@pytest.mark.parametrize(
    ("card", "payload"),
    [
        (WebSearchCard(), {"query": "q", "synthesis": _paragraphs(2), "sources_used": []}),
        (SearchResultCard(), {"query": "q", "answer": _paragraphs(2)}),
    ],
)
def test_cards_draw_a_short_synthesis_whole(card: object, payload: dict[str, object]) -> None:
    html = card.render(payload, RenderContext(language="fr"))  # type: ignore[attr-defined]
    assert "lia-collapsible" not in html
    assert "P1." in html
