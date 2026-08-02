"""The ``$steps`` reference syntax, and its documented divergence.

Inherited from ``test_reference_validator_schema`` when ``ReferenceValidator``
was removed (ADR-194): the validator around this regex never rejected anything,
but the regex itself is load-bearing — ``capability_directives`` uses it to know
which steps a surviving step still depends on, and dropping a depended-upon step
would break the plan.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.semantic_validator import _STEPS_REFERENCE_PATTERN
from src.domains.agents.orchestration.step_references import STEPS_REFERENCE_PATTERN

pytestmark = pytest.mark.unit


class TestStepsReferencePattern:
    def test_extracts_step_id_and_field_path(self) -> None:
        matches = STEPS_REFERENCE_PATTERN.findall(
            "$steps.search.contacts[0].emailAddresses[0].value"
        )
        assert matches == [("search", "contacts[0].emailAddresses[0].value")]

    def test_extracts_multiple_references_in_one_string(self) -> None:
        matches = STEPS_REFERENCE_PATTERN.findall(
            "from:$steps.a.contacts[0].value OR to:$steps.b.contacts[1].value"
        )
        assert matches == [("a", "contacts[0].value"), ("b", "contacts[1].value")]

    def test_wildcard_index_is_captured(self) -> None:
        matches = STEPS_REFERENCE_PATTERN.findall(
            "$steps.search.contacts[*].emailAddresses[*].value"
        )
        assert matches == [("search", "contacts[*].emailAddresses[*].value")]

    def test_non_reference_string_yields_no_match(self) -> None:
        assert STEPS_REFERENCE_PATTERN.findall("just a plain subject line") == []

    def test_single_char_terminal_field_is_not_matched(self) -> None:
        """Documented gap: the field-path group needs >=2 chars, so a 1-char
        terminal field name (``$steps.s.x``) is NOT extracted. Pinned so a future
        regex change is a conscious decision, not an accident. Real tool fields
        are multi-character (``value``, ``resource_name``), so this never bites."""
        assert STEPS_REFERENCE_PATTERN.findall("$steps.s.x") == []
        # Two chars already match:
        assert STEPS_REFERENCE_PATTERN.findall("$steps.s.id") == [("s", "id")]


class TestTheTwoPatternsAreDeliberatelyDifferent:
    """Pin the divergence so nobody 'deduplicates' them into a single regex.

    ``semantic_validator`` needs the DOMAIN key alone to compare it against the
    producing step's ``result_key``; this module needs the full path. One regex
    cannot serve both, and a merge would silently break ghost-dependency
    detection or dependency extraction.
    """

    @pytest.mark.parametrize(
        ("reference", "full_path", "domain_key"),
        [
            ("$steps.s1.contacts[0].name", "contacts[0].name", "contacts"),
            ("$steps.s1.events[*].start.dateTime", "events[*].start.dateTime", "events"),
        ],
    )
    def test_full_path_versus_domain_key(
        self, reference: str, full_path: str, domain_key: str
    ) -> None:
        assert STEPS_REFERENCE_PATTERN.findall(reference) == [("s1", full_path)]
        assert _STEPS_REFERENCE_PATTERN.findall(reference) == [("s1", domain_key)]

    def test_single_char_field_matches_only_the_narrow_pattern(self) -> None:
        """The narrow pattern has no >=2 char floor — another reason to keep both."""
        assert STEPS_REFERENCE_PATTERN.findall("$steps.s1.x") == []
        assert _STEPS_REFERENCE_PATTERN.findall("$steps.s1.x") == [("s1", "x")]
