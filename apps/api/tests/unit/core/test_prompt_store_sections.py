"""One parser for every ``key|Header|template`` prompt file (prompt audit 2026-09-12, lot D).

Three copies of the same loop lived in ``memory_injection``, ``peer_context_injection``
and ``relations/debrief/injection`` — two- and three-column variants that could drift
apart. ``parse_prompt_sections`` is the single implementation; it lives in
``core.prompt_store`` because ``relations`` must not import ``agents``.
"""

from __future__ import annotations

import pytest

from src.core.prompt_store import parse_prompt_sections

LF = chr(10)


def _text(*lines: str) -> str:
    return LF.join(lines) + LF


def test_two_columns() -> None:
    text = _text("# comment", "", "sensitivities|Sensitivities and painful topics", "goals|Goals")
    assert parse_prompt_sections(text, 2) == [
        ("sensitivities", "Sensitivities and painful topics"),
        ("goals", "Goals"),
    ]


def test_three_columns_keep_the_template_intact_including_later_pipes() -> None:
    text = _text("emails|Emails|- {value} | sent")
    assert parse_prompt_sections(text, 3) == [("emails", "Emails", "- {value} | sent")]


def test_cells_are_stripped() -> None:
    assert parse_prompt_sections(_text("  key |  Header  |  tpl "), 3) == [("key", "Header", "tpl")]


def test_a_line_short_of_a_column_is_skipped_not_guessed() -> None:
    """A two-cell line in a three-column file has no template: it is not a section."""
    assert parse_prompt_sections(_text("a|b", "c|d|e"), 3) == [("c", "d", "e")]


def test_comments_and_blank_lines_are_ignored() -> None:
    assert parse_prompt_sections(_text("", "   ", "# a|b", "a|b"), 2) == [("a", "b")]


def test_order_is_the_file_order() -> None:
    text = _text("z|Z", "a|A", "m|M")
    assert [k for k, _ in parse_prompt_sections(text, 2)] == ["z", "a", "m"]


@pytest.mark.parametrize("columns", [0, 1])
def test_fewer_than_two_columns_is_a_programming_error(columns: int) -> None:
    with pytest.raises(ValueError):
        parse_prompt_sections(_text("a|b"), columns)


def test_crlf_files_parse_like_lf_files() -> None:
    """A Windows checkout carries CRLF; the last cell must not keep the CR."""
    text = "a|b|c\r\nd|e|f\r\n"
    assert parse_prompt_sections(text, 3) == [("a", "b", "c"), ("d", "e", "f")]
