"""What the renderer enforces, the prompt publishes (ADR-184, ADR-274).

A budget the renderer applies without telling the writer is a trap: the writer
believes it was obeyed, and the split it caused looks like a defect. Every
enforced bound therefore travels as a placeholder read from settings, with the
consequence of each overrun stated in words.

The writer reads ONE family's rules: the format is known before the call, and a
report writer has no use for the rules of a deck (measured 2026-11-13: the three
families cost 191, 273 and 289 tokens, all sent to every call until then).
"""

import re
from typing import get_args

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.document_generation.formulas import FUNCTIONS
from src.domains.document_generation.prompts import FAMILY_PROMPTS, document_prompt_template
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TabularContent,
)
from src.domains.document_generation.service import prompt_values

pytestmark = [pytest.mark.unit]

_PLACEHOLDER = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")
#: One representative format per family.
_FAMILY_FORMAT = {
    TabularContent: DocumentType.XLSX,
    SectionedContent: DocumentType.DOCX,
    SlideContent: DocumentType.PPTX,
}


def _template(doc_type: DocumentType) -> str:
    return document_prompt_template(doc_type)


def _values(doc_type: DocumentType) -> dict[str, str | int]:
    return prompt_values(doc_type=doc_type, language="fr", instructions="x", source_data="")


class TestThePromptIsRenderable:
    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_every_placeholder_is_supplied_and_nothing_is_left_open(
        self, doc_type: DocumentType
    ) -> None:
        values = _values(doc_type)
        template = _template(doc_type)
        assert set(_PLACEHOLDER.findall(template)) == set(values)
        # The formula grammar's examples are written doubled (« {{Revenue}} ») and
        # reach the writer single; nothing else may survive the formatting.
        assert template.format(**values).count("{") == template.count("{{")

    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_no_enforced_number_is_hard_coded_in_the_prose(self, doc_type: DocumentType) -> None:
        """A number written here cannot be reconciled with the one applied."""
        static = _template(doc_type).split(DYNAMIC_CONTEXT_MARKER)[0]
        for enforced in ("110", "16000", "8800", " 6 bullets", "240"):
            assert enforced not in static, enforced

    def test_every_family_has_its_rules(self) -> None:
        """ADR-085: a family without rules would reach the writer with none."""
        assert set(FAMILY_PROMPTS) == set(SCHEMA_BY_DOC_TYPE.values())


class TestEachFamilyReadsItsOwnRules:
    def test_a_report_writer_never_reads_the_rules_of_a_deck_or_a_sheet(self) -> None:
        report = _template(DocumentType.DOCX)
        assert "speaker notes" not in report.lower()
        assert "column design" not in report.lower()

    def test_a_deck_writer_never_reads_the_rules_of_a_report_or_a_sheet(self) -> None:
        deck = _template(DocumentType.PPTX)
        assert "table of contents" not in deck.lower()
        assert "column design" not in deck.lower()

    def test_a_sheet_writer_never_reads_the_rules_of_a_report_or_a_deck(self) -> None:
        sheet = _template(DocumentType.XLSX)
        assert "speaker notes" not in sheet.lower()
        assert "table of contents" not in sheet.lower()

    def test_formats_of_one_family_share_their_static_rules(self) -> None:
        """docx, pdf, md and txt read the same cacheable prefix."""
        statics = {
            _template(doc_type).split(DYNAMIC_CONTEXT_MARKER)[0]
            for doc_type, family in SCHEMA_BY_DOC_TYPE.items()
            if family is SectionedContent
        }
        assert len(statics) == 1


class TestTheVocabularyIsPublished:
    def test_every_block_kind_is_named(self) -> None:
        text = _template(DocumentType.DOCX)
        for kind in get_args(SectionBlock.model_fields["kind"].annotation):
            assert f"`{kind}`" in text, kind

    def test_every_slide_kind_is_named(self) -> None:
        text = _template(DocumentType.PPTX)
        for kind in get_args(Slide.model_fields["kind"].annotation):
            assert f"`{kind}`" in text, kind

    def test_the_fields_a_writer_must_fill_are_named(self) -> None:
        assert "`caption`" in _template(DocumentType.DOCX)
        for field in ("subtitle", "columns", "notes"):
            assert f"`{field}`" in _template(DocumentType.PPTX), field

    def test_the_writer_is_told_what_the_renderer_does_for_it(self) -> None:
        assert "table of contents" in _template(DocumentType.PDF).lower()
        assert "do not number your headings" in _template(DocumentType.MD).lower()
        assert "splits the slide" in _template(DocumentType.PPTX).lower()

    def test_a_deck_writer_learns_figures_quotes_pictograms_and_delivery(self) -> None:
        from src.domains.document_generation.schemas import DECK_DELIVERIES

        deck = _template(DocumentType.PPTX)
        for word in ("`figures`", "`value`", "`label`", "`quote`", "`icon`", "`delivery`"):
            assert word in deck, word
        for delivery in DECK_DELIVERIES:
            assert f"`{delivery}`" in deck, delivery

    def test_a_report_writer_learns_figures_pictures_and_sources(self) -> None:
        report = _template(DocumentType.DOCX)
        for word in ("`figures`", "`value`", "`label`", "`illustration`", "`sources`", "`url`"):
            assert word in report, word
        assert "[1], [2]" in report
        assert "never an invented or completed address" in report

    def test_a_deck_writer_writes_no_agenda_and_invents_no_quote(self) -> None:
        deck = _template(DocumentType.PPTX).lower()
        assert "never write an agenda slide" in deck
        assert "never invent" in deck

    def test_the_deck_bounds_are_the_renderer_s(self) -> None:
        from src.domains.document_generation import typography

        values = _values(DocumentType.PPTX)
        assert values["figures_per_slide"] == typography.PPTX_FIGURES_PER_SLIDE
        assert values["agenda_min_parts"] == typography.PPTX_AGENDA_MIN_PARTS


class TestTheTableVocabularyIsPublished:
    """What the renderer computes, the writer must know it may declare (ADR-184)."""

    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_every_family_publishes_the_column_semantics(self, doc_type: DocumentType) -> None:
        text = _template(doc_type)
        for word in ("`columns`", "`kind`", "`unit`", "`formula`", "`amount`", "`percent`"):
            assert word in text, (doc_type.value, word)

    def test_a_sheet_writer_learns_inputs_totals_summaries_choices_and_emphasis(self) -> None:
        text = _template(DocumentType.XLSX)
        for word in ("`inputs`", "`total`", "`summary`", "`choices`", "`better`", "`figures`"):
            assert word in text, word

    def test_a_sheet_writer_learns_the_key_figures_and_their_bound(self) -> None:
        """A figure reads a sheet's whole column by a qualified name, under the bound
        normalization holds (ADR-388)."""
        from src.core.constants import DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX

        text = _template(DocumentType.XLSX)
        assert "SUM({{Sheet/Column}})" in text and "AVERAGE({{Sheet/Column}})" in text
        assert "{workbook_figures_max}" in text
        assert _values(DocumentType.XLSX)["workbook_figures_max"] == (
            DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX
        )

    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_the_comparison_rule_normalization_enforces_is_published(
        self, doc_type: DocumentType
    ) -> None:
        """ADR-184: a condition reading bare a value that may be missing is dropped
        (``columns._invalid_formulas``, ``workbook_figures._invalid``): its writer is told."""
        assert "divides, averages or reads the row above" in _template(doc_type)

    def test_every_grammar_function_the_parser_accepts_is_named(self) -> None:
        """Read from the parser's own registry: a function added there is published."""
        sheet = _template(DocumentType.XLSX)
        for function in sorted(FUNCTIONS):
            assert f"{function}(" in sheet, function


class TestTheCacheableParts:
    @pytest.mark.parametrize("family", list(_FAMILY_FORMAT), ids=lambda f: f.__name__)
    def test_the_dynamic_tail_is_marked_and_holds_the_request(self, family: type) -> None:
        """The static rules must be cacheable; the request must not be."""
        text = _template(_FAMILY_FORMAT[family])
        assert text.count(DYNAMIC_CONTEXT_MARKER) == 1
        static, dynamic = text.split(DYNAMIC_CONTEXT_MARKER, 1)
        for placeholder in ("{language}", "{instructions}", "{source_data}", "{doc_format}"):
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


class TestTheChartVocabularyIsPublished:
    """A chart the renderer can draw, the writer must know it may declare (ADR-184)."""

    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_every_family_learns_the_intents_and_the_one_axis_rule(
        self, doc_type: DocumentType
    ) -> None:
        from src.domains.document_generation.schemas import CHART_INTENTS

        text = _template(doc_type)
        for word in ("`chart`", "`intent`", "`category`", "`values`", "`form`"):
            assert word in text, (doc_type.value, word)
        for intent in CHART_INTENTS:
            assert f"`{intent}`" in text, (doc_type.value, intent)
        assert "ONE unit" in text

    def test_the_series_bound_is_the_palette_s(self) -> None:
        from src.domains.document_generation.typography import CHART_MAX_SERIES

        assert _values(DocumentType.DOCX)["chart_max_series"] == CHART_MAX_SERIES

    def test_a_csv_writer_is_told_its_chart_is_not_written(self) -> None:
        assert "summaries, key figures and charts are not written" in _template(DocumentType.CSV)


def _illustrated_values(doc_type: DocumentType, preferences: object) -> dict[str, str | int]:
    from src.core.document_preferences import DocumentPreferences

    assert isinstance(preferences, DocumentPreferences)
    return prompt_values(
        doc_type=doc_type,
        language="fr",
        instructions="x",
        source_data="",
        preferences=preferences,
    )


def _deck_values(preferences: object) -> dict[str, str | int]:
    from src.core.document_preferences import DocumentPreferences

    assert isinstance(preferences, DocumentPreferences)
    return prompt_values(
        doc_type=DocumentType.PPTX,
        language="fr",
        instructions="x",
        source_data="",
        preferences=preferences,
    )


class TestTheIllustrationRulesArePublished:
    """What the normalization enforces, the writer reads — and only in the request's tail."""

    def test_a_deck_the_person_illustrates_reads_the_enforced_budget(self) -> None:
        from src.core.document_preferences import DocumentPreferences
        from src.domains.document_generation.pictures import illustration_budget

        preferences = DocumentPreferences(images_allowed=True)
        text = str(_deck_values(preferences)["illustrations"])

        assert f"at most {illustration_budget(preferences)} pictures" in text
        for word in ("`illustration.subject`", "`illustration.alt`", "`image_style`"):
            assert word in text, word
        assert "cover first" in text

    def test_on_request_waits_for_the_request_to_ask(self) -> None:
        from src.core.document_preferences import DocumentIllustrations, DocumentPreferences

        text = str(
            _deck_values(
                DocumentPreferences(
                    images_allowed=True, illustrations=DocumentIllustrations.ON_REQUEST
                )
            )["illustrations"]
        )
        assert text.startswith("ILLUSTRATIONS: only if the request asks")

    @pytest.mark.parametrize("case", ["images_off", "never", "instance_off"])
    def test_no_budget_tells_the_writer_to_leave_them_empty(
        self, case: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.core.document_preferences import DocumentIllustrations, DocumentPreferences

        preferences = DocumentPreferences(images_allowed=case != "images_off")
        if case == "never":
            preferences = DocumentPreferences(
                images_allowed=True, illustrations=DocumentIllustrations.NEVER
            )
        if case == "instance_off":
            monkeypatch.setattr(settings, "document_illustrations_max", 0)

        text = str(_deck_values(preferences)["illustrations"])

        assert "Leave every `illustration` empty" in text

    @pytest.mark.parametrize("doc_type", [DocumentType.CSV, DocumentType.XLSX])
    def test_a_family_that_places_no_picture_is_told_nothing_of_them(
        self, doc_type: DocumentType
    ) -> None:
        assert _values(doc_type)["illustrations"] == ""

    @pytest.mark.parametrize("doc_type", [DocumentType.DOCX, DocumentType.PDF])
    def test_a_report_the_person_illustrates_reads_its_own_rules(
        self, doc_type: DocumentType
    ) -> None:
        from src.core.document_preferences import DocumentPreferences
        from src.domains.document_generation.pictures import illustration_budget

        preferences = DocumentPreferences(images_allowed=True)
        text = str(_illustrated_values(doc_type, preferences)["illustrations"])

        assert f"at most {illustration_budget(preferences)} pictures" in text
        for word in ("`illustration` block", "`caption`", "`image_style`", "cover"):
            assert word in text, word
        assert "slide" not in text and "deck" not in text

    @pytest.mark.parametrize("doc_type", [DocumentType.MD, DocumentType.TXT])
    def test_a_text_file_is_asked_for_no_picture_it_cannot_hold(
        self, doc_type: DocumentType
    ) -> None:
        from src.core.document_preferences import DocumentPreferences

        text = str(
            _illustrated_values(doc_type, DocumentPreferences(images_allowed=True))["illustrations"]
        )
        assert "Leave every `illustration` empty" in text

    def test_the_rules_stand_in_the_request_s_tail(self) -> None:
        """They depend on the person: in the cached head they would split the cache."""
        head, _marker, tail = _template(DocumentType.PPTX).partition(DYNAMIC_CONTEXT_MARKER)
        assert "{illustrations}" not in head
        assert "{illustrations}" in tail


class TestTheToneIsPublished:
    @pytest.mark.parametrize("doc_type", list(DocumentType), ids=lambda t: t.value)
    def test_every_family_learns_every_tone(self, doc_type: DocumentType) -> None:
        from src.domains.document_generation.schemas import DOCUMENT_TONES

        text = _template(doc_type)
        assert "`tone`" in text
        for tone in DOCUMENT_TONES:
            assert f"`{tone}`" in text, (doc_type.value, tone)
