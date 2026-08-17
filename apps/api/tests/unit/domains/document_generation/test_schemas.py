"""Content schemas: per-type schema selection is total; models validate (ADR-226)."""

import pytest
from pydantic import ValidationError

from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentType,
    SectionBlock,
    SectionedContent,
    SlideContent,
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

    def test_heading_level_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SectionBlock(kind="heading", text="t", level=9)
