"""The rhythm calibration harness stays honest and cannot rot (ADR-214).

The original harness was a scratchpad and was lost; this one lives in the
repository, so it must keep proving three things without network or data:

- it is DETERMINISTIC (a seed reproduces the population byte for byte) — a
  calibration nobody can replay is a guess with a decimal point;
- its populations mean what they say: the structureless one must not claim a
  window under the CURRENT thresholds (the false-positive floor the ADR
  publishes), the tight habitual one must;
- its threshold sweep keeps the hysteresis invariant (exit below entry) and
  the split-half bar under the main bar — a sweep that silently kept the old
  strictness would measure nothing.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "habits" / "measure_calibration.py"


def _harness() -> Any:
    spec = importlib.util.spec_from_file_location("measure_calibration", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = _harness()


class TestDeterminism:
    def test_same_seed_same_population(self) -> None:
        a = HARNESS.gen_habitual(random.Random(7), 0.15)
        b = HARNESS.gen_habitual(random.Random(7), 0.15)
        assert a == b


class TestPopulationsMeanWhatTheySay:
    def test_current_thresholds_reproduce_the_published_calibration(self) -> None:
        """The anchor: under the shipped thresholds a structureless user never
        claims, a tight habitual user always does (ADR-214: FP 0-0.3 %,
        detection 98-100 %). A harness that cannot reproduce the published
        numbers cannot be trusted anywhere else on its grid."""
        th = HARNESS._thresholds(0.6, 1.9)
        uniform_claims = sum(
            1 for i in range(20) if HARNESS._claims(HARNESS.gen_uniform(random.Random(i)), th)
        )
        habitual_claims = sum(
            1
            for i in range(20)
            if HARNESS._claims(HARNESS.gen_habitual(random.Random(i), 0.15), th)
        )
        assert uniform_claims == 0
        assert habitual_claims == 20


class TestTheSweepKeepsItsInvariants:
    @pytest.mark.parametrize(("capture", "selectivity"), HARNESS.RHYTHM_GRID)
    def test_exit_stays_below_entry(self, capture: float, selectivity: float) -> None:
        th = HARNESS._thresholds(capture, selectivity)
        assert th.exit_capture < th.capture_min
        assert th.exit_selectivity < th.selectivity_min


class TestNamedSetsKeepTheirInvariants:
    @pytest.mark.parametrize(("name", "spec"), HARNESS.RHYTHM_SETS)
    def test_rhythm_set_is_coherent(self, name: str, spec: dict[str, float]) -> None:
        """Exit under entry, split-half under main, follower bars follow."""
        th = HARNESS._set_thresholds(spec)
        assert th.exit_presence < th.presence_min
        assert th.exit_capture < th.capture_min
        assert th.exit_selectivity < th.selectivity_min
        assert th.half_presence_min < th.presence_min
        assert th.recent_min <= th.presence_min - 0.10
        assert th.sparse_active_days_min <= th.presence_min

    def test_rhythm_sets_start_from_the_shipped_defaults(self) -> None:
        """The first set IS the shipped configuration — a drifted 'current'
        row would compare candidates against a baseline nobody runs. The
        CONSTANTS are the reference: the harness must measure the same
        numbers under ``task`` (root .env injected) and under a bare
        interpreter."""
        from src.core import constants as C

        _name, spec = HARNESS.RHYTHM_SETS[0]
        assert spec["presence"] == C.HABITS_PRESENCE_MIN_DEFAULT
        assert spec["wilson"] == C.HABITS_WILSON_FLOOR_DEFAULT
        assert spec["sparse"] == C.HABITS_SPARSE_ACTIVE_DAYS_MIN_DEFAULT
        assert spec["half"] == C.HABITS_HALF_PRESENCE_MIN_DEFAULT
        assert spec["sel"] == C.HABITS_SELECTIVITY_MIN_DEFAULT

    def test_the_harness_baseline_is_the_shipped_configuration(self) -> None:
        """Every ``*_DEFAULT`` the detectors read is mirrored in the harness
        baseline, field for field — a constant added to the config and not
        here would be measured at whatever ``SimpleNamespace`` lacks (an
        AttributeError at best, a stale number at worst).

        The reference is what the settings classes DECLARE, never what the
        environment holds: ``HabitsSettings()`` reads ``HABITS_*`` from the
        process environment, so the previous form of this test was green on
        the CI runner and red inside any container whose ``.env`` pinned an
        older calibration (measured 2026-09-11: ``selectivity_min 1.9 != 1.6``
        on docker dev) — a verdict that depends on the launcher is not a test
        of the code. ``model_construct`` materialises the declared defaults
        without consulting the environment.
        """
        from src.core.config.habits import HabitsSettings
        from src.domains.habits.rhythm import RhythmThresholds

        rhythm = RhythmThresholds.from_settings(HARNESS.SHIPPED_RHYTHM)
        assert rhythm == RhythmThresholds.from_settings(HabitsSettings.model_construct())

    def test_the_baseline_check_ignores_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pinned ``HABITS_SELECTIVITY_MIN`` in the environment must not
        change the verdict: the harness measures the shipped code."""
        from src.core.config.habits import HabitsSettings
        from src.domains.habits.rhythm import RhythmThresholds

        monkeypatch.setenv("HABITS_SELECTIVITY_MIN", "4.9")
        assert HabitsSettings().habits_selectivity_min == 4.9  # the env IS read by a live instance
        assert RhythmThresholds.from_settings(
            HARNESS.SHIPPED_RHYTHM
        ) == RhythmThresholds.from_settings(HabitsSettings.model_construct())


class TestStructurelessPopulationsNeverClaimUnderAnySet:
    """The sweep's reason to exist: relaxation candidates are only
    candidates while every no-structure population stays at zero. 20 seeded
    trials per population — the 300-trial run is the measurement; this is
    the guard that keeps the harness honest in CI."""

    @pytest.mark.parametrize(
        ("set_name", "spec"),
        [(n, s) for n, s in HARNESS.RHYTHM_SETS if n in HARNESS.RHYTHM_SETS_FP_CLEAN],
    )
    def test_fp_clean_rhythm_sets_never_claim_a_structureless_population(
        self, set_name: str, spec: dict[str, float]
    ) -> None:
        """Only the sets DECLARED clean are pinned: relaxed_b/relaxed_c are
        kept in the sweep as measured counter-examples (they claim windows on
        the scattered control), and pinning them to zero would either red the
        build or push the harness to hide the cost it exists to show."""
        th = HARNESS._set_thresholds(spec)
        for pop_name, gen in HARNESS.RHYTHM_TRAJECTORY_POPULATIONS:
            if pop_name not in HARNESS.RHYTHM_FP_POPULATIONS:
                continue
            claims = sum(
                1
                for i in range(20)
                if HARNESS._claims_any(gen(random.Random(1000 * i + 7)), HARNESS.AS_OF, th)
            )
            assert claims == 0, f"{set_name} claims {pop_name}"
