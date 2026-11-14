"""Content schemas: per-type schema selection is total; models validate (ADR-226)."""

import pytest
from pydantic import ValidationError

from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    COLUMN_KINDS,
    DECK_DELIVERIES,
    FIGURE_KINDS,
    SCHEMA_BY_DOC_TYPE,
    SLIDE_ICONS,
    SLIDE_KINDS,
    ChartSpec,
    DocumentType,
    Illustration,
    KeyFigure,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
    TabularContent,
    WorkbookFigure,
)


@pytest.mark.unit
class TestDocumentSchemas:
    """Schema families and their per-format mapping."""

    def test_schema_map_is_total(self) -> None:
        # Boot-time completeness doctrine (ADR-085): every DocumentType maps.
        assert set(SCHEMA_BY_DOC_TYPE) == set(DocumentType)

    def test_family_assignment(self) -> None:
        assert SCHEMA_BY_DOC_TYPE[DocumentType.CSV] is TabularContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.XLSX] is TabularContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.DOCX] is SectionedContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.PDF] is SectionedContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.MD] is SectionedContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.TXT] is SectionedContent
        assert SCHEMA_BY_DOC_TYPE[DocumentType.PPTX] is SlideContent

    def test_tabular_requires_at_least_one_sheet(self) -> None:
        with pytest.raises(ValidationError):
            TabularContent(filename_stem="x", title="t", sheets=[])

    def test_sectioned_requires_at_least_one_block(self) -> None:
        with pytest.raises(ValidationError):
            SectionedContent(filename_stem="x", title="t", blocks=[])

    def test_slides_require_at_least_one_slide(self) -> None:
        with pytest.raises(ValidationError):
            SlideContent(filename_stem="x", title="t", slides=[])

    def test_section_block_defaults(self) -> None:
        block = SectionBlock(kind="paragraph", text="hello")
        assert block.level == 2
        assert block.items == []
        assert block.table is None

    def test_heading_level_is_not_bounded_by_the_schema(self) -> None:
        """A bound REFUSES the whole document (ADR-269 lesson); levels are clamped."""
        assert SectionBlock(kind="heading", text="t", level=9).level == 9
        assert SectionBlock(kind="heading", text="t", level=0).level == 0

    def test_new_block_kinds_and_fields_default(self) -> None:
        block = SectionBlock(kind="callout", text="watch out")
        assert block.caption == ""
        assert SectionBlock(kind="numbered", items=["a"]).items == ["a"]
        assert SectionBlock(kind="quote", text="q").text == "q"
        assert SectionedContent(filename_stem="x", title="t", blocks=[block]).subtitle == ""

    def test_slide_vocabulary_defaults(self) -> None:
        slide = Slide(title="t")
        assert slide.kind == "content"
        assert slide.subtitle == "" and slide.columns == [] and slide.table is None
        comparison = Slide(
            title="A vs B",
            kind="comparison",
            columns=[SlideColumn(heading="A", bullets=["x"]), SlideColumn(heading="B")],
        )
        assert comparison.columns[1].bullets == []
        assert SlideContent(filename_stem="d", title="D", slides=[slide]).subtitle == ""

    def test_the_schema_the_model_sees_carries_no_bound(self) -> None:
        """Only min_length on the three lists stays: nothing to render otherwise."""
        import json

        for schema in (TabularContent, SectionedContent, SlideContent):
            text = json.dumps(schema.model_json_schema())
            for keyword in ('"maximum"', '"minimum"', '"maxLength"', '"maxItems"', '"pattern"'):
                assert keyword not in text, f"{schema.__name__} publishes {keyword}"

    def test_the_strict_mode_verdict_is_pinned_per_family(self) -> None:
        """Measured 2026-09-08, and frozen so a schema change cannot move it silently.

        OpenAI's strict path allows 5 nesting levels. A table costs TWO
        (``TableSheet`` → ``rows`` → ``list[str]``), so any family carrying one
        inside a repeated block lands at 6:

        - ``SectionedContent`` has been at 6 since ADR-226 — the family was
          never strict, and nobody had measured it; docx/pdf/md/txt have run on
          ``function_calling`` ever since, without incident.
        - ``SlideContent`` joins it at 6 with ADR-274, because a slide may now
          carry data (a table) or two compared sides.
        - ``TabularContent`` stays at 5 — but it is not strict-SHAPED (it
          tolerates extra keys), and the Responses path every current OpenAI
          model takes sends a schema unconverted: measured 2026-09-26, it
          answered 400 on every call while judged strict. It goes by
          ``function_calling`` like the two others, which OpenAI accepts.

        The alternative — hoisting tables to the document root and referencing
        them by index — buys strict mode by handing the model an index it can
        get wrong, which is the trade ADR-184 refuses.

        2026-11-13 (ADR-274 amendment): a table may now say what its columns ARE
        (``columns`` → ``ColumnSpec`` → ``choices``), one level more for every
        family — 6, 7 and 7. None was strict before; the verdicts do not move.
        """
        from src.infrastructure.llm.strict_schema import (
            _analyze_schema_strict_compatibility,
            _get_max_nesting_depth,
        )

        expected = {
            TabularContent: (6, False),
            SectionedContent: (7, False),
            SlideContent: (7, False),
        }
        for schema, (depth, strict) in expected.items():
            assert _get_max_nesting_depth(schema.model_json_schema()) == depth, schema.__name__
            compatible, _reason = _analyze_schema_strict_compatibility(schema)
            assert compatible is strict, schema.__name__

    def test_no_family_approaches_the_property_limit(self) -> None:
        """The other strict-mode wall (100 properties) stays far away."""
        from src.infrastructure.llm.strict_schema import _count_total_properties

        for schema in (TabularContent, SectionedContent, SlideContent):
            assert _count_total_properties(schema.model_json_schema()) < 50, schema.__name__

    def test_a_non_strict_family_still_has_a_native_method(self) -> None:
        """Losing strict mode is not losing structured output: the door picks a method."""
        from src.infrastructure.llm.structured_output import native_structured_method

        assert native_structured_method("openai", use_strict_mode=False) == {
            "method": "function_calling"
        }
        # Ollama's native ``format`` is grammar-constrained whatever the verdict (ADR-267).
        assert native_structured_method("ollama", use_strict_mode=False) == {
            "method": "json_schema"
        }

    def test_descriptions_are_one_line(self) -> None:
        """A class docstring is sent to the model as ``description`` (ADR-269)."""
        for schema in (
            TabularContent,
            SectionedContent,
            SlideContent,
            SectionBlock,
            TableSheet,
            Slide,
            SlideColumn,
            ChartSpec,
            KeyFigure,
            Illustration,
            WorkbookFigure,
        ):
            assert "\n" not in (schema.__doc__ or "").strip(), schema.__name__

    def test_a_workbook_figure_is_offered_the_kinds_it_can_be(self) -> None:
        """A key figure is a number or a date: a text kind is never offered (ADR-184)."""
        published = TabularContent.model_json_schema()["$defs"]["WorkbookFigure"]["properties"]
        assert published["kind"]["enum"] == list(FIGURE_KINDS)
        assert set(COLUMN_KINDS) - set(FIGURE_KINDS) == {"text", "code"}

    def test_an_input_is_offered_the_kinds_a_formula_can_read(self) -> None:
        """An input is read by formulas as a number or a date: what normalization
        keeps is what the writer is offered (ADR-184)."""
        published = TabularContent.model_json_schema()["$defs"]["SheetInput"]["properties"]
        assert published["kind"]["enum"] == list(FIGURE_KINDS)


def _slide_properties() -> dict[str, dict[str, object]]:
    schema = SlideContent.model_json_schema()
    properties: dict[str, dict[str, object]] = schema["$defs"]["Slide"]["properties"]
    return properties


@pytest.mark.unit
class TestTheDeckVocabulary:
    """Key figures, quotes, icons and delivery: published, never refused (ADR-184, ADR-269)."""

    def test_a_key_figure_needs_only_its_value(self) -> None:
        figure = KeyFigure(value="42 %")
        assert (figure.label, figure.icon) == ("", "")

    def test_the_new_slide_fields_default_to_nothing(self) -> None:
        slide = Slide(title="t")
        assert (slide.figures, slide.quote, slide.icon) == ([], "", "")
        assert SlideContent(filename_stem="d", title="D", slides=[slide]).delivery == ""

    def test_the_icon_names_are_published_on_the_slide(self) -> None:
        assert _slide_properties()["icon"]["enum"] == list(SLIDE_ICONS)

    def test_the_deliveries_are_published_on_the_deck(self) -> None:
        delivery = SlideContent.model_json_schema()["properties"]["delivery"]
        assert delivery["enum"] == list(DECK_DELIVERIES)
        assert set(DECK_DELIVERIES) == {"presented", "read"}

    def test_a_figure_s_icon_points_at_the_one_published_list(self) -> None:
        """The list is published ONCE: a second copy would cost its tokens twice."""
        figure = SlideContent.model_json_schema()["$defs"]["KeyFigure"]["properties"]["icon"]
        assert "enum" not in figure
        assert "`icon`" in str(figure["description"])

    def test_an_unknown_icon_or_delivery_is_accepted_for_repair(self) -> None:
        assert Slide(title="t", icon="unicorn").icon == "unicorn"
        assert KeyFigure(value="1", icon="unicorn").icon == "unicorn"
        deck = SlideContent(
            filename_stem="d", title="D", delivery="keynote", slides=[Slide(title="t")]
        )
        assert deck.delivery == "keynote"

    def test_a_picture_is_asked_for_by_its_subject_and_described_by_its_alt(self) -> None:
        picture = Illustration(subject="a lighthouse at dawn")
        assert picture.alt == ""
        assert Slide(title="t").illustration is None
        deck = SlideContent(filename_stem="d", title="D", slides=[Slide(title="t")])
        assert (deck.illustration, deck.image_style) == (None, "")

    def test_the_cover_and_the_slides_can_ask_for_a_picture_in_one_style(self) -> None:
        schema = SlideContent.model_json_schema()
        assert "illustration" in schema["properties"]
        assert "image_style" in schema["properties"]
        assert "illustration" in _slide_properties()
        illustration = schema["$defs"]["Illustration"]["properties"]
        assert set(illustration) == {"subject", "alt"}

    def test_icon_names_are_lucide_names(self) -> None:
        import re

        assert len(set(SLIDE_ICONS)) == len(SLIDE_ICONS)
        for name in SLIDE_ICONS:
            assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), name


@pytest.mark.unit
class TestEveryRendererCoversTheVocabulary:
    """ADR-085 over the five registries keyed by the block or slide vocabulary.

    The import-time asserts refuse a partial map; this test says WHICH map is
    partial when one is, and pins the vocabulary to the schema rather than to a
    list somebody typed.
    """

    def test_the_vocabularies_are_read_from_the_schema(self) -> None:
        assert BLOCK_KINDS == {
            "heading",
            "paragraph",
            "bullets",
            "numbered",
            "quote",
            "callout",
            "table",
            "chart",
            "figures",
            "illustration",
        }
        assert SLIDE_KINDS == {
            "content",
            "section",
            "comparison",
            "table",
            "chart",
            "figures",
            "quote",
        }

    def test_the_total_registries_cover_every_block_kind(self) -> None:
        from src.domains.document_generation.renderers.docx import _BLOCKS
        from src.domains.document_generation.renderers.text import _MD_BLOCKS, _TXT_BLOCKS

        for registry in (_BLOCKS, _MD_BLOCKS, _TXT_BLOCKS):
            assert set(registry) == BLOCK_KINDS

    def test_the_pdf_registry_plus_its_structured_kinds_is_total(self) -> None:
        from src.domains.document_generation.renderers.pdf import (
            _SIMPLE_BLOCKS,
            _STRUCTURED_KINDS,
        )

        assert set(_SIMPLE_BLOCKS) | _STRUCTURED_KINDS == BLOCK_KINDS
        assert not set(_SIMPLE_BLOCKS) & _STRUCTURED_KINDS

    def test_the_slide_registry_covers_every_slide_kind(self) -> None:
        from src.domains.document_generation.renderers.pptx import _KINDS

        assert set(_KINDS) == SLIDE_KINDS

    def test_normalization_covers_every_content_family(self) -> None:
        from src.domains.document_generation.normalize import _NORMALIZERS

        assert set(_NORMALIZERS) == set(SCHEMA_BY_DOC_TYPE.values())


@pytest.mark.unit
class TestTheReportVocabulary:
    def test_a_report_can_carry_figures_pictures_and_its_sources(self) -> None:
        schema = SectionedContent.model_json_schema()
        for name in ("illustration", "image_style", "sources"):
            assert name in schema["properties"], name
        assert set(schema["$defs"]["Source"]["properties"]) == {"title", "url"}
        assert {"figures", "illustration"} <= set(schema["$defs"]["SectionBlock"]["properties"])

    def test_a_source_is_named_by_its_title_alone_when_it_has_no_address(self) -> None:
        from src.domains.document_generation.schemas import Source

        assert Source(title="A book").url == ""
