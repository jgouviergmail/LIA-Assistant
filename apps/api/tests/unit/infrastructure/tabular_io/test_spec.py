"""Unit tests for the declarative workbook specification.

The spec is the contract every other layer reads: the writer turns it into
sheets, dropdowns and locked cells; the reader resolves columns by key from it;
the domain declares one and gets both halves for free. A malformed spec must
therefore fail at construction — not silently produce a workbook whose columns
cannot be read back.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.infrastructure.tabular_io.spec import (
    ColumnSpec,
    SheetSpec,
    SpecError,
    WorkbookSpec,
)


def _column(key: str, **overrides: object) -> ColumnSpec:
    defaults: dict[str, object] = {"key": key, "label_key": f"label.{key}", "kind": "text"}
    return ColumnSpec(**{**defaults, **overrides})  # type: ignore[arg-type]


def _sheet(*columns: ColumnSpec, name: str = "Sheet", key_column: str = "id") -> SheetSpec:
    return SheetSpec(
        name=name, title_key="title.sheet", columns=tuple(columns), key_column=key_column
    )


@pytest.mark.unit
class TestColumnSpec:
    def test_a_text_column_needs_nothing_more(self) -> None:
        column = _column("name")
        assert column.editable is True and column.referential is None

    def test_an_enum_column_without_a_referential_is_refused(self) -> None:
        with pytest.raises(SpecError, match="referential"):
            _column("provider", kind="enum")

    def test_an_enum_list_column_without_a_referential_is_refused(self) -> None:
        with pytest.raises(SpecError, match="referential"):
            _column("values", kind="enum_list")

    def test_a_referential_on_a_free_text_column_is_refused(self) -> None:
        """A dropdown on a column the reader parses as free text would lie."""
        with pytest.raises(SpecError, match="referential"):
            _column("name", kind="text", referential="PROVIDER")

    def test_a_decimal_column_declares_its_scale(self) -> None:
        column = _column("price", kind="decimal", decimals=6, minimum=Decimal("0"))
        assert column.decimals == 6

    def test_a_decimal_column_without_a_scale_is_refused(self) -> None:
        """Without a declared scale the reader cannot tell 0.1 from 0.1000001."""
        with pytest.raises(SpecError, match="decimals"):
            _column("price", kind="decimal")

    def test_a_scale_on_a_non_decimal_column_is_refused(self) -> None:
        with pytest.raises(SpecError, match="decimals"):
            _column("name", kind="text", decimals=2)

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(SpecError, match="key"):
            _column("")

    def test_a_read_only_column_is_never_required(self) -> None:
        """Requiring a value the admin cannot type is a contradiction."""
        with pytest.raises(SpecError, match="read-only"):
            _column("statut", editable=False, required=True)


@pytest.mark.unit
class TestSheetSpec:
    def test_duplicate_column_keys_are_refused(self) -> None:
        with pytest.raises(SpecError, match="duplicate"):
            _sheet(_column("id"), _column("id"))

    def test_the_key_column_must_exist(self) -> None:
        with pytest.raises(SpecError, match="key_column"):
            _sheet(_column("name"), key_column="id")

    def test_a_sheet_without_columns_is_refused(self) -> None:
        with pytest.raises(SpecError, match="column"):
            _sheet(key_column="id")

    def test_a_sheet_name_excel_rejects_is_refused(self) -> None:
        """openpyxl silently mangles these characters; failing early is honest."""
        with pytest.raises(SpecError, match="name"):
            _sheet(_column("id"), name="Bad/Name")

    def test_a_sheet_name_over_31_characters_is_refused(self) -> None:
        with pytest.raises(SpecError, match="name"):
            _sheet(_column("id"), name="x" * 32)

    def test_column_lookup_by_key(self) -> None:
        sheet = _sheet(_column("id"), _column("name"))
        assert sheet.column("name").label_key == "label.name"

    def test_looking_up_an_unknown_column_raises(self) -> None:
        with pytest.raises(KeyError):
            _sheet(_column("id")).column("nope")

    def test_editable_keys_exclude_read_only_columns(self) -> None:
        sheet = _sheet(_column("id"), _column("statut", editable=False))
        assert sheet.editable_keys == ("id",)


@pytest.mark.unit
class TestWorkbookSpec:
    def test_a_referential_used_by_a_column_must_be_declared(self) -> None:
        sheet = _sheet(_column("id"), _column("provider", kind="enum", referential="PROVIDER"))
        with pytest.raises(SpecError, match="PROVIDER"):
            WorkbookSpec(sheets=(sheet,), referentials={}, schema_version=1)

    def test_a_declared_referential_satisfies_the_column(self) -> None:
        sheet = _sheet(_column("id"), _column("provider", kind="enum", referential="PROVIDER"))
        workbook = WorkbookSpec(
            sheets=(sheet,), referentials={"PROVIDER": ("openai",)}, schema_version=1
        )
        assert workbook.sheet("Sheet").column("provider").referential == "PROVIDER"

    def test_duplicate_sheet_names_are_refused(self) -> None:
        with pytest.raises(SpecError, match="duplicate"):
            WorkbookSpec(
                sheets=(_sheet(_column("id")), _sheet(_column("id"))),
                referentials={},
                schema_version=1,
            )

    def test_an_empty_referential_is_refused(self) -> None:
        """An empty dropdown makes its column impossible to fill."""
        sheet = _sheet(_column("id"), _column("provider", kind="enum", referential="PROVIDER"))
        with pytest.raises(SpecError, match="empty"):
            WorkbookSpec(sheets=(sheet,), referentials={"PROVIDER": ()}, schema_version=1)

    def test_a_workbook_without_sheets_is_refused(self) -> None:
        with pytest.raises(SpecError, match="sheet"):
            WorkbookSpec(sheets=(), referentials={}, schema_version=1)

    def test_looking_up_an_unknown_sheet_raises(self) -> None:
        workbook = WorkbookSpec(sheets=(_sheet(_column("id")),), referentials={}, schema_version=1)
        with pytest.raises(KeyError):
            workbook.sheet("Nope")

    def test_an_unused_referential_is_allowed(self) -> None:
        """Declaring more than needed is harmless; the writer emits what it uses."""
        workbook = WorkbookSpec(
            sheets=(_sheet(_column("id")),),
            referentials={"UNUSED": ("a",)},
            schema_version=1,
        )
        assert "UNUSED" in workbook.referentials


@pytest.mark.unit
class TestKeyUniqueness:
    """A detail sheet groups rows by a parent key; it does not identify them.

    Found by simulating a real export: the time-slot sheet holds one row per
    window, so a model with two windows appears twice — and the reader refused
    the file as if the administrator had duplicated a line.
    """

    def test_a_sheet_key_is_unique_by_default(self) -> None:
        assert _sheet(_column("id")).key_is_unique is True

    def test_a_sheet_can_declare_a_grouping_key(self) -> None:
        sheet = SheetSpec(
            name="Detail",
            title_key="t",
            columns=(_column("id"), _column("value")),
            key_column="id",
            key_is_unique=False,
        )
        assert sheet.key_is_unique is False


@pytest.mark.unit
class TestHiddenColumns:
    """Some columns travel both ways without ever concerning the reader's eye.

    A per-row fingerprint is written by the export and read back by the import
    to detect rows edited underneath the administrator — but showing it would
    only invite someone to "clean it up".
    """

    def test_a_column_is_visible_by_default(self) -> None:
        assert _column("name").hidden is False

    def test_a_column_can_be_declared_hidden(self) -> None:
        assert _column("row_fingerprint", editable=False, hidden=True).hidden is True
