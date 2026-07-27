"""Unit tests for the pure core of scripts/measure_journal_themes.py.

The script is the theme-reachability measurement instrument. Its I/O shell (LLM
calls, CLI) is thin; the battery definition and the aggregation are pure and are
tested here without an LLM. Loaded via importlib because ``scripts/`` is not a
package (same technique as test_measure_psyche.py).

The battery itself is under test too: a scenario battery that silently loses its
negative cases would report a noise rate of 0.0 for a prompt that writes on
every turn.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from src.domains.journals.models import JournalTheme

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parents[4] / "scripts" / "measure_journal_themes.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_journal_themes", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: dataclasses resolves cls.__module__ via sys.modules.
    sys.modules["measure_journal_themes"] = module
    spec.loader.exec_module(module)
    return module


mjt = _load_script()


class TestBatteryShape:
    """The battery must keep both arms; a one-armed battery cannot arbitrate."""

    def test_every_theme_has_at_least_two_positive_scenarios(self) -> None:
        """Each theme is probed by an explicit AND an implicit case.

        A theme probed only by its explicit case reports full recall while the
        realistic path (a signal shown, never stated) is still dead — which is
        precisely how the regression stayed invisible.
        """
        counts: dict[str, int] = {}
        for scenario in mjt.SCENARIOS:
            if scenario.expected is not None:
                counts[scenario.expected.value] = counts.get(scenario.expected.value, 0) + 1
        for theme in JournalTheme:
            assert counts.get(theme.value, 0) >= 2, (
                f"Theme {theme.value!r} has {counts.get(theme.value, 0)} positive scenario(s); "
                "at least two are required (one explicit, one implicit)."
            )

    def test_negative_scenarios_are_present(self) -> None:
        """Negatives are the guard rail against buying recall with noise."""
        negatives = [s for s in mjt.SCENARIOS if s.expected is None]
        assert len(negatives) >= 5, (
            f"Only {len(negatives)} negative scenarios. Without them the harness "
            "cannot tell a better prompt from a chattier one."
        )

    def test_scenario_ids_are_unique(self) -> None:
        """Ids address scenarios on the CLI and key the report."""
        ids = [s.id for s in mjt.SCENARIOS]
        assert len(ids) == len(set(ids)), f"duplicate scenario ids: {ids}"


class TestScenarioResult:
    """Per-scenario rates."""

    def test_recall_counts_runs_not_entries(self) -> None:
        """Recall is the share of RUNS that produced the theme.

        Counting entries would let a single run writing three entries report a
        recall above 1.0.
        """
        result = mjt.ScenarioResult(scenario_id="s", expected="learnings", reps=4)
        result.created_themes["learnings"] = 3
        result.total_created = 7
        assert result.recall == pytest.approx(0.75)

    def test_recall_is_none_for_negative_scenarios(self) -> None:
        """A negative scenario has no expected theme, hence no recall."""
        result = mjt.ScenarioResult(scenario_id="s", expected=None, reps=4)
        assert result.recall is None

    def test_silence_and_volume(self) -> None:
        """Silence and volume are computed over the run count."""
        result = mjt.ScenarioResult(scenario_id="s", expected=None, reps=4)
        result.silent_runs = 3
        result.total_created = 2
        assert result.silence_rate == pytest.approx(0.75)
        assert result.volume == pytest.approx(0.5)

    def test_zero_reps_does_not_divide_by_zero(self) -> None:
        """A filtered-out scenario must not crash the report."""
        result = mjt.ScenarioResult(scenario_id="s", expected="learnings", reps=0)
        assert result.recall is None
        assert result.silence_rate == 0.0
        assert result.volume == 0.0


class TestSummarize:
    """The headline figures the calibration decision is made on."""

    def _result(self, sid: str, expected: str | None, reps: int, **kwargs: object) -> object:
        result = mjt.ScenarioResult(scenario_id=sid, expected=expected, reps=reps)
        for key, value in kwargs.items():
            setattr(result, key, value)
        return result

    def test_unreachable_theme_is_reported(self) -> None:
        """A theme at 0.0 across ALL its scenarios is flagged unreachable.

        This is the single figure that would have caught the 2026-06-02
        regression on the day it shipped.
        """
        results = [
            self._result("a", "learnings", 4),
            self._result("b", "ideas_analyses", 4),
        ]
        results[0].created_themes["learnings"] = 4  # type: ignore[attr-defined]
        summary = mjt.summarize(results)
        assert summary["themes_unreachable"] == ["ideas_analyses"]
        assert summary["recall_by_theme"]["learnings"] == 1.0
        assert summary["recall_by_theme"]["ideas_analyses"] == 0.0

    def test_partially_reachable_theme_is_not_flagged(self) -> None:
        """A theme reached by one of its two scenarios is degraded, not dead."""
        results = [
            self._result("a", "ideas_analyses", 4),
            self._result("b", "ideas_analyses", 4),
        ]
        results[0].created_themes["ideas_analyses"] = 4  # type: ignore[attr-defined]
        summary = mjt.summarize(results)
        assert summary["themes_unreachable"] == []
        assert summary["recall_by_theme"]["ideas_analyses"] == pytest.approx(0.5)

    def test_noise_rate_counts_negative_runs_that_wrote(self) -> None:
        """Noise is the share of negative runs that were not silent.

        Values are picked to avoid a rounding tie: the report rounds rates to
        three decimals and volumes to two, for readability.
        """
        results = [
            self._result("neg1", None, 4, silent_runs=4),
            self._result("neg2", None, 4, silent_runs=1, total_created=4),
        ]
        summary = mjt.summarize(results)
        assert summary["negative_noise_rate"] == pytest.approx(3 / 8)
        assert summary["negative_volume"] == pytest.approx(0.5)

    def test_summary_without_negatives_does_not_divide_by_zero(self) -> None:
        """Restricting the run to positives must not crash the summary."""
        results = [self._result("a", "learnings", 2)]
        summary = mjt.summarize(results)
        assert summary["negative_noise_rate"] == 0.0
        assert summary["negative_volume"] == 0.0
