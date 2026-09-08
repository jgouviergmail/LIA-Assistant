"""What the renderer enforces, the prompt publishes (ADR-184, ADR-274).

A budget the renderer applies without telling the writer is a trap: the writer
believes it was obeyed, and the split it caused looks like a defect. Every
enforced bound therefore travels as a placeholder read from settings, with the
consequence of each overrun stated in words.
"""

import re
from pathlib import Path
from typing import get_args

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.document_generation.schemas import DocumentType, SectionBlock, Slide
from src.domains.document_generation.service import prompt_values

pytestmark = [pytest.mark.unit]

PROMPT = (
    Path(__file__).parents[5]
    / "src"
    / "domains"
    / "agents"
    / "prompts"
    / "v1"
    / "document_generation_prompt.txt"
)
_PLACEHOLDER = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def _text() -> str:
    return PROMPT.read_text(encoding="utf-8")


class TestThePromptIsRenderable:
    def test_every_placeholder_is_supplied_and_nothing_is_left_open(self) -> None:
        values = prompt_values(
            doc_type=DocumentType.DOCX, language="fr", instructions="x", source_data=""
        )
        assert set(_PLACEHOLDER.findall(_text())) == set(values)
        rendered = _text().format(**values)
        assert not _PLACEHOLDER.search(rendered)

    def test_no_enforced_number_is_hard_coded_in_the_prose(self) -> None:
        """A number written here cannot be reconciled with the one applied."""
        static = _text().split(DYNAMIC_CONTEXT_MARKER)[0]
        for enforced in ("110", "16000", "8800", " 6 bullets"):
            assert enforced not in static, enforced


class TestTheVocabularyIsPublished:
    def test_every_block_kind_is_named(self) -> None:
        text = _text()
        for kind in get_args(SectionBlock.model_fields["kind"].annotation):
            assert f"`{kind}`" in text, kind

    def test_every_slide_kind_is_named(self) -> None:
        text = _text()
        for kind in get_args(Slide.model_fields["kind"].annotation):
            assert f"`{kind}`" in text, kind

    def test_the_fields_a_writer_must_fill_are_named(self) -> None:
        text = _text()
        for field in ("caption", "subtitle", "columns", "notes"):
            assert f"`{field}`" in text, field

    def test_the_writer_is_told_what_the_renderer_does_for_it(self) -> None:
        lowered = _text().lower()
        assert "table of contents" in lowered
        assert "do not number your headings" in lowered
        assert "splits the slide" in lowered


class TestTheCacheableParts:
    def test_the_dynamic_tail_is_marked_and_holds_the_request(self) -> None:
        """The static rules must be cacheable; the request must not be."""
        text = _text()
        assert DYNAMIC_CONTEXT_MARKER in text
        static, dynamic = text.split(DYNAMIC_CONTEXT_MARKER, 1)
        for placeholder in ("{language}", "{instructions}", "{source_data}"):
            assert placeholder in dynamic and placeholder not in static


@pytest.mark.unit
class TestTheLengthBudgetFollowsTheFamily:
    """Measured 2026-09-08 with o200k_base on realistic large documents: prose
    and slides converge to 0.69 words per output token, a workbook to 0.25 —
    the JSON structure of short cells dominates. ONE factor for the three would
    publish a number 2.2x too generous for a spreadsheet, and a model obeying
    it would be cut at the budget it was told to respect (ADR-184, ADR-275)."""

    def test_a_workbook_is_given_a_smaller_budget_than_a_report(self) -> None:
        report = prompt_values(
            doc_type=DocumentType.DOCX, language="fr", instructions="x", source_data=""
        )
        workbook = prompt_values(
            doc_type=DocumentType.XLSX, language="fr", instructions="x", source_data=""
        )
        assert workbook["length_budget_words"] < report["length_budget_words"]

    def test_slides_and_prose_share_the_same_economics(self) -> None:
        deck = prompt_values(
            doc_type=DocumentType.PPTX, language="fr", instructions="x", source_data=""
        )
        report = prompt_values(
            doc_type=DocumentType.DOCX, language="fr", instructions="x", source_data=""
        )
        assert deck["length_budget_words"] == report["length_budget_words"]

    def test_every_content_family_declares_its_factor(self) -> None:
        """ADR-085: a family with no factor would fall back to a guess."""
        from src.core.constants import DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN
        from src.domains.document_generation.schemas import SCHEMA_BY_DOC_TYPE

        assert set(DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN) == {
            model.__name__ for model in SCHEMA_BY_DOC_TYPE.values()
        }

    def test_every_doc_type_gets_a_positive_budget(self) -> None:
        for doc_type in DocumentType:
            values = prompt_values(
                doc_type=doc_type, language="fr", instructions="x", source_data=""
            )
            assert int(values["length_budget_words"]) > 0
