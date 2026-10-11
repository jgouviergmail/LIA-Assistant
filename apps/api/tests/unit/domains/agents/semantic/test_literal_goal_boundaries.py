"""Literal goal tokens cannot borrow a decimal, compound name or URI prefix."""

from datetime import date

import pytest

from src.domains.agents.analysis.requested_outcomes import (
    GoalFieldExpectation,
    GoalRequirement,
    anchored_requirements,
)


def _accepted(value: str, quote: str) -> bool:
    goal = GoalRequirement(
        domain="contact",
        label="Literal goal",
        source_quote=quote,
        expected_fields=(
            GoalFieldExpectation(field="name", expected_value=value, source_quote=quote),
        ),
    )
    return bool(anchored_requirements([goal], quote, ["contact"]))


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("12", "12.34"),
        ("12", "12,34"),
        ("34", "12.34"),
        ("12", "-12"),
        ("2026", "2026-10-06"),
        ("10", "2026-10-06"),
        ("12", "12/34"),
        ("Anne", "Anne-Marie"),
        ("Marie", "Anne-Marie"),
        ("Anne", "Anne‑Marie"),
        ("O", "O'Connor"),
        ("Connor", "O'Connor"),
        ("Anne", "Anne’s"),
        ("Anne", "Anne.Marie"),
        ("Ada", "ada"),
        ("https://example.com/report", "https://example.com/report?account=other"),
        ("https://example.com/report", "https://example.com/report#private"),
        ("https://example.com/report", "https://example.com/report/other"),
        ("https://example.com/report", "https://example.com/report%2Fother"),
        ("anne@example.com", "o'anne@example.com"),
        ("anne@example.com", "anne@example.com.fr"),
        ("anne@example.com", "anne@example.com?account=other"),
    ],
)
def test_a_longer_token_cannot_anchor_another_value(value: str, quote: str) -> None:
    assert not _accepted(value, quote)


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("12", "12 contacts"),
        ("12", "Il y en a 12."),
        ("12", "12, puis 3."),
        ("12.34", "12.34"),
        ("-12", "La valeur est -12."),
        ("Anne", "Anne."),
        ("Anne", "« Anne », puis Ada."),
        ("Anne", "'Anne'"),
        ("Anne-Marie", "Anne-Marie."),
        ("O'Connor", "O'Connor."),
        ("Anne’s", "Anne’s"),
        ("https://example.com/report", "https://example.com/report"),
        ("https://example.com/report", "<https://example.com/report>"),
        ("https://example.com/report", "« https://example.com/report »"),
        ("https://example.com/report?account=other", "https://example.com/report?account=other"),
        ("anne@example.com", "anne@example.com."),
        ("anne@example.com", "« anne@example.com »"),
        ("o'anne@example.com", "o'anne@example.com"),
    ],
)
def test_exact_values_keep_unambiguous_sentence_and_quote_boundaries(
    value: str, quote: str
) -> None:
    assert _accepted(value, quote)


@pytest.mark.parametrize(
    ("count", "quote", "valid"),
    [
        (12, "12.34 contacts", False),
        (12, "12,34 contacts", False),
        (2026, "Contacts le 2026-10-06", False),
        (10, "Contacts le 2026-10-06", False),
        (12, "Liste 12 contacts", True),
        (12, "Liste mes contacts, 12.", True),
        (0, "Liste 3 contacts", False),
        (0, "Liste 0 contacts", True),
    ],
)
def test_count_uses_a_complete_number_instead_of_digits_from_a_date_or_decimal(
    count: int,
    quote: str,
    valid: bool,
) -> None:
    goal = GoalRequirement(domain="contact", label="Contacts", source_quote=quote, min_count=count)
    assert bool(anchored_requirements([goal], quote, ["contact"])) is valid


@pytest.mark.parametrize(
    ("count", "query"),
    [
        (12, "12.34 contacts"),
        (2026, "Contacts le 2026-10-06"),
    ],
)
def test_short_count_quote_cannot_bypass_the_actual_query_boundary(count: int, query: str) -> None:
    goal = GoalRequirement(
        domain="contact", label="Contacts", source_quote=str(count), min_count=count
    )
    assert not anchored_requirements([goal], query, ["contact"])


@pytest.mark.parametrize(
    ("quote", "query", "expected"),
    [
        ("2026-10-08", "Météo le 2026-10-08T00:30:00Z", "2026-10-08"),
        ("2026-10-08", "Météo le 2026-10-08 01:00:00Z", "2026-10-08"),
        ("demain", "Météo après-demain", "2026-10-08"),
    ],
)
def test_short_date_quote_cannot_bypass_a_timestamp_or_relative_date(
    quote: str,
    query: str,
    expected: str,
) -> None:
    goal = GoalRequirement(
        domain="weather",
        label="Forecast",
        source_quote=query,
        expected_fields=(
            GoalFieldExpectation(
                field="date",
                expected_value=expected,
                operator="on_date",
                source_quote=quote,
            ),
        ),
    )
    assert not anchored_requirements(
        [goal],
        query,
        ["weather"],
        reference_date=date(2026, 10, 7),
        reference_timezone="America/New_York",
    )
