"""The two parameters the lookups share (ADR-318): a ceiling repaired, a period refused."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.lookup_parameters import bounded_count, read_period
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class TestTheCeiling:
    @pytest.mark.parametrize(
        ("requested", "expected"), [(None, 10), (3, 3), (10, 10), (500, 10), (0, 1), (-4, 1)]
    )
    def test_is_repaired_never_refused(self, requested: int | None, expected: int) -> None:
        assert bounded_count(requested, 10) == expected


class TestThePeriod:
    def test_a_readable_period(self) -> None:
        assert read_period("2026-09-21", "2026-09-21", PARIS, now=NOW, default_days=7) == (
            datetime(2026, 9, 21, tzinfo=PARIS),
            datetime(2026, 9, 22, tzinfo=PARIS),
        )

    def test_the_default_window(self) -> None:
        assert read_period(None, None, PARIS, now=NOW, default_days=3) == (
            NOW - timedelta(days=3),
            NOW,
        )

    def test_an_unreadable_value_is_the_adr_310_refusal(self) -> None:
        refusal = read_period("yesterday", None, PARIS, now=NOW, default_days=None)

        assert isinstance(refusal, UnifiedToolOutput)
        assert refusal.error_code == ToolErrorCode.INVALID_INPUT.value
        assert "'yesterday'" in refusal.message and "YYYY-MM-DD" in refusal.message

    def test_an_inverted_period_is_its_own_refusal(self) -> None:
        refusal = read_period("2026-09-22", "2026-09-20", PARIS, now=NOW, default_days=None)

        assert isinstance(refusal, UnifiedToolOutput)
        assert refusal.error_code == ToolErrorCode.INVALID_PARAM_VALUE.value


@pytest.mark.parametrize(
    ("wording", "bound"),
    [
        (
            "src.domains.agents.calculation.catalogue_manifests:CALCULATE_EXPRESSION_DESCRIPTION",
            "calculator_expression_max_chars",
        ),
        (
            "src.domains.agents.journal.catalogue_manifests:JOURNAL_MAX_RESULTS_DESCRIPTION",
            "journal_search_max_results",
        ),
        (
            "src.domains.agents.activity.catalogue_manifests:ACTIVITY_MAX_RESULTS_DESCRIPTION",
            "effect_activity_max_actions",
        ),
        (
            "src.domains.agents.generated_file.catalogue_manifests:"
            "GENERATED_FILES_MAX_RESULTS_DESCRIPTION",
            "generated_files_search_max_results",
        ),
    ],
)
def test_the_wording_both_readers_bind_states_the_enforced_bound(wording: str, bound: str) -> None:
    """The ReAct loop binds the schema, never the manifest (ADR-310): a bound only
    the manifest's constraint published would be hidden from it (ADR-184)."""
    import importlib

    from src.core.config import settings

    module_name, attribute = wording.split(":")
    text = getattr(importlib.import_module(module_name), attribute)

    assert str(getattr(settings, bound)) in text
