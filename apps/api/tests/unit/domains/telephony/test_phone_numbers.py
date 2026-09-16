"""Unit tests for the ONE implementation of « what is a phone number » (lot 1).

The helpers used to be private to the third-party call tool; the identity
service (the person's own verified number) needs the same rules, so they moved
to ``telephony/phone_numbers.py``. Two readers of one rule is how a national
number gets dialled by one and refused by the other.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.telephony.phone_numbers import (
    looks_like_phone,
    normalize_phone,
    number_search_variants,
    same_line,
    to_e164,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+33612345678", True),
        ("06 12 34 56 78", True),
        ("Marie Dupont", False),
        ("+33", False),
    ],
)
def test_looks_like_phone(value: str, expected: bool) -> None:
    assert looks_like_phone(value) is expected


@pytest.mark.unit
def test_normalize_phone_applies_default_country_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)
    assert normalize_phone("06.82.51.16.39") == "+33682511639"
    assert normalize_phone("+33 6 82 51 16 39") == "+33682511639"
    assert normalize_phone("0033682511639") == "0033682511639"


@pytest.mark.unit
def test_same_line_matches_national_and_international_without_country_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
    assert same_line("0612345678", "+33612345678") is True
    assert same_line("0612345678", "+44612345678") is True  # prefix unknown: suffix rule
    assert same_line("0612345678", "0612345679") is False


@pytest.mark.unit
def test_number_search_variants_lists_national_form_first_after_e164(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)
    assert number_search_variants("+33612345678") == ["+33612345678", "0612345678"]


@pytest.mark.unit
class TestToE164:
    """The identity service stores E.164 or nothing."""

    def test_national_number_is_promoted_under_a_country_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)
        assert to_e164("06 12 34 56 78") == "+33612345678"

    def test_international_number_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
        assert to_e164("+1 (415) 555-0100") == "+14155550100"

    @pytest.mark.parametrize(
        "raw",
        ["0612345678", "+33", "Marie", "", "+3361234567890123", "+0612345678"],
    )
    def test_anything_else_is_refused(self, raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # No country code: a national number cannot be promoted, so it is not E.164.
        monkeypatch.setattr(settings, "telephony_default_country_code", "", raising=False)
        assert to_e164(raw) is None
