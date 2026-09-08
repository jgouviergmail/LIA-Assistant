"""Content schemas: per-type schema selection is total; models validate (ADR-226)."""

import pytest
from pydantic import ValidationError

from src.domains.document_generation.schemas import (
    BLOCK_KINDS,
    SCHEMA_BY_DOC_TYPE,
    SLIDE_KINDS,
    DocumentType,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideColumn,
    SlideContent,
    TableSheet,
    TabularContent,
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
        - ``TabularContent`` stays at 5 and stays strict.

        The alternative — hoisting tables to the document root and referencing
        them by index — buys strict mode by handing the model an index it can
        get wrong, which is the trade ADR-184 refuses.
        """
        from src.infrastructure.llm.strict_schema import (
            _analyze_schema_strict_compatibility,
            _get_max_nesting_depth,
        )

        expected = {
            TabularContent: (5, True),
            SectionedContent: (6, False),
            SlideContent: (6, False),
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
        ):
            assert "\n" not in (schema.__doc__ or "").strip(), schema.__name__


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
        }
        assert SLIDE_KINDS == {"content", "section", "comparison", "table"}

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
