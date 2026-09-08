"""Formula-injection neutralization and filename sanitization (ADR-226).

The openpyxl probe (2026-08-17) proved a leading '=' string is stored as a
FORMULA (data_type 'f'): neutralization is a correctness requirement, not a
precaution.
"""

import pytest

from src.domains.document_generation.sanitize import (
    neutralize_formula,
    sanitize_filename_stem,
    strip_control_characters,
)


@pytest.mark.unit
class TestNeutralizeFormula:
    """Spreadsheet-active values are quoted; data stays data."""

    @pytest.mark.parametrize("raw", ["=1+2", "+A1", "-2+3", "@cmd", "\tx", "\rx"])
    def test_dangerous_prefixes_neutralized(self, raw: str) -> None:
        assert neutralize_formula(raw) == f"'{raw}"

    @pytest.mark.parametrize("raw", ["hello", "12", "a=b", "", "négatif -5 après texte"])
    def test_safe_values_untouched(self, raw: str) -> None:
        assert neutralize_formula(raw) == raw

    @pytest.mark.parametrize("raw", ["-5", "-5.2", "-0.001", "+3", "+3.14", "-1e6", "-5,2"])
    def test_plain_numbers_are_not_formulas(self, raw: str) -> None:
        # A legitimate signed NUMBER must never be defaced: '-5.2 in a data
        # column is a rendering defect. Only spreadsheet-ACTIVE strings are
        # neutralized.
        assert neutralize_formula(raw) == raw


@pytest.mark.unit
class TestSanitizeFilenameStem:
    """LLM/user-suggested names become safe download stems."""

    def test_strips_separators_and_controls(self) -> None:
        cleaned = sanitize_filename_stem("../..\\évil\x00name")
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert "\x00" not in cleaned
        assert "évil" in cleaned  # accents survive (RFC 5987 proven)

    def test_windows_forbidden_characters_removed(self) -> None:
        cleaned = sanitize_filename_stem('a<b>c:d"e|f?g*h')
        assert not set(cleaned) & set('<>:"|?*')

    def test_empty_falls_back(self) -> None:
        assert sanitize_filename_stem("   ") == "document"
        assert sanitize_filename_stem("...") == "document"

    def test_capped_at_80(self) -> None:
        assert len(sanitize_filename_stem("x" * 300)) <= 80

    def test_no_leading_dot_no_trailing_dot(self) -> None:
        cleaned = sanitize_filename_stem(".hidden.")
        assert not cleaned.startswith(".")
        assert not cleaned.endswith(".")


@pytest.mark.unit
class TestControlCharactersAreRemoved:
    """XML forbids most C0 controls, so python-docx and openpyxl REFUSE them:
    a model that echoed a form feed out of an extracted PDF crashed the render
    after the call had been paid for (measured 2026-09-08)."""

    def test_the_characters_xml_forbids_are_dropped(self) -> None:
        assert strip_control_characters("a\x00b\x07c\x1bd") == "abcd"

    def test_tab_newline_and_carriage_return_survive(self) -> None:
        """They are legal in XML, and the whitespace collapsing owns them."""
        assert strip_control_characters("a\tb\nc\rd") == "a\tb\nc\rd"

    def test_ordinary_text_is_untouched(self) -> None:
        assert strip_control_characters("Émile — 12 \u20ac \u4e00") == "Émile — 12 \u20ac \u4e00"
