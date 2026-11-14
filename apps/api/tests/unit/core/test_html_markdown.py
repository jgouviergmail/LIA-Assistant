"""« How an answer becomes Markdown » has one door, in the core (ADR-291).

``html_to_markdown`` moved here from ``rag_spaces/processing`` so a reader that
only wants the conversion — the export of one discussion — does not have to
import a document-processing domain for it. The knowledge spaces and the kept
answers still reach the SAME function through their historical import.
"""

from __future__ import annotations

import pytest

from src.core.html_markdown import as_markdown, html_to_markdown

pytestmark = pytest.mark.unit


def test_markdown_is_kept_as_written() -> None:
    answer = "**Two** steps:\n\n1. `x < y`\n2. done"

    assert as_markdown(answer) == answer


def test_a_comparison_in_prose_is_not_taken_for_markup() -> None:
    answer = "if x<a and b>c then stop"

    assert as_markdown(answer) == answer


def test_an_html_answer_becomes_markdown() -> None:
    answer = '<div class="lia-response"><h2>Plan</h2><p>Two <strong>steps</strong>.</p></div>'

    markdown = as_markdown(answer)

    assert "## Plan" in markdown
    assert "**steps**" in markdown
    assert "<" not in markdown


def test_scripts_and_styles_never_reach_the_text() -> None:
    answer = "<div><style>.x{color:red}</style><script>alert(1)</script><p>Hello</p></div>"

    markdown = as_markdown(answer)

    assert "Hello" in markdown
    assert "alert" not in markdown and "color" not in markdown


def test_the_knowledge_spaces_reach_the_same_door() -> None:
    from src.domains.rag_spaces import processing

    assert processing.html_to_markdown is html_to_markdown
