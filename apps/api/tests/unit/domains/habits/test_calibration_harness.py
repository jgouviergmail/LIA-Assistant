"""The calibration harness stays honest and cannot rot (ADR-214).

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
from collections.abc import Callable
from datetime import timedelta
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
        assert HARNESS.gen_daily_recurrence(random.Random(3), 1.5) == HARNESS.gen_daily_recurrence(
            random.Random(3), 1.5
        )


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

    def test_random_hours_never_lock_at_the_current_r(self) -> None:
        stg = HARNESS._recurrence_settings(0.8)
        locks = sum(
            1
            for i in range(20)
            if HARNESS.evaluate_locks(
                HARNESS.gen_random_recurrence(random.Random(i)), HARNESS.AS_OF, stg
            )
            is not None
        )
        assert locks == 0


class TestTheSweepKeepsItsInvariants:
    @pytest.mark.parametrize(("capture", "selectivity"), HARNESS.RHYTHM_GRID)
    def test_exit_stays_below_entry(self, capture: float, selectivity: float) -> None:
        th = HARNESS._thresholds(capture, selectivity)
        assert th.exit_capture < th.capture_min
        assert th.exit_selectivity < th.selectivity_min

    @pytest.mark.parametrize("r_min", HARNESS.R_GRID)
    def test_split_half_bar_tracks_the_main_bar(self, r_min: float) -> None:
        stg = HARNESS._recurrence_settings(r_min)
        assert stg.recurrence_lock_half_r_min < stg.recurrence_lock_r_min


class TestModerateGenerators:
    """The 2026-09-11 trajectory populations (owner direction: a set must
    serve a hyper-active user AND a moderate-but-targeted one)."""

    def test_same_seed_same_population(self) -> None:
        assert HARNESS.gen_moderate_focused(random.Random(5), 3.0) == HARNESS.gen_moderate_focused(
            random.Random(5), 3.0
        )
        assert HARNESS.gen_few_weekly(random.Random(5), 3.0, 0.75) == HARNESS.gen_few_weekly(
            random.Random(5), 3.0, 0.75
        )
        assert HARNESS.gen_weekly_ritual(random.Random(5), 0.9, 0.75) == HARNESS.gen_weekly_ritual(
            random.Random(5), 0.9, 0.75
        )

    def test_focused_population_is_actually_light_and_targeted(self) -> None:
        """~3 active days a week, and >=85 % of events inside 20-22h."""
        days = HARNESS.gen_moderate_focused(random.Random(11), 3.0)
        assert 12 <= len(days) <= 36  # 3/7 of 56 days, wide tolerance
        events = [(h, n) for hist in days.values() for h, n in hist.items()]
        inside = sum(n for h, n in events if h in (20, 21))
        assert inside / sum(n for _h, n in events) >= 0.85

    def test_weekly_ritual_stays_on_one_weekday(self) -> None:
        days = HARNESS.gen_weekly_ritual(random.Random(11), 0.9, 0.75)
        assert {d.weekday() for d in days} == {6}
        assert 3 <= len(days) <= 6  # 6 slots in 42 days at 90 % reliability

    def test_long_generators_cover_the_largest_swept_window(self) -> None:
        """A window sweep must never read a series shorter than itself."""
        max_window = max(int(spec["window"]) for _n, spec in HARNESS.LOCK_SETS)
        assert HARNESS.RECURRENCE_GEN_DAYS >= max_window
        assert max(HARNESS.RECURRENCE_HORIZONS) <= HARNESS.RECURRENCE_GEN_DAYS
        assert max(HARNESS.RHYTHM_HORIZONS) <= HARNESS.WINDOW_DAYS


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
        AttributeError at best, a stale number at worst)."""
        from src.core import constants as C
        from src.core.config.automation import AutomationSettings
        from src.core.config.habits import HabitsSettings
        from src.domains.habits.rhythm import RhythmThresholds

        rhythm = RhythmThresholds.from_settings(HARNESS.SHIPPED_RHYTHM)
        assert rhythm == RhythmThresholds.from_settings(HabitsSettings())
        shipped = vars(HARNESS.SHIPPED_RECURRENCE)
        live = AutomationSettings()
        for name, value in shipped.items():
            assert getattr(live, name) == value, name
        assert shipped["recurrence_window_days"] == C.RECURRENCE_WINDOW_DAYS_DEFAULT

    @pytest.mark.parametrize(("name", "spec"), HARNESS.LOCK_SETS)
    def test_lock_set_is_coherent(self, name: str, spec: dict[str, float]) -> None:
        stg = HARNESS._lock_set_settings(spec)
        assert stg.recurrence_lock_half_r_min < stg.recurrence_lock_r_min
        assert stg.recurrence_window_days >= stg.recurrence_lock_min_spread_days
        assert stg.recurrence_lock_min_occurrences >= stg.recurrence_min_distinct_days
        # The weekly lock needs its slots to EXIST in the window.
        assert stg.recurrence_weekly_min_same_dow <= stg.recurrence_window_days // 7

    def test_lock_sets_start_from_the_shipped_defaults(self) -> None:
        from src.core import constants as C

        _name, spec = HARNESS.LOCK_SETS[0]
        assert spec["min_occ"] == C.RECURRENCE_LOCK_MIN_OCCURRENCES_DEFAULT
        assert spec["shape_days"] == C.RECURRENCE_SHAPE_MIN_SPAN_DAYS_DEFAULT
        assert spec["wk_dow"] == C.RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT
        assert spec["wk_frac"] == C.RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT
        assert spec["window"] == C.RECURRENCE_WINDOW_DAYS_DEFAULT


class TestRecalibratedAnchors:
    """The 2026-09-11 calibration, pinned on 20 seeded trials (deterministic;
    the 300-trial tables live in the ADR-214 amendment). What these prove:

    - a 3x/week steady hour — the owner's "rare but targeted" shape — LOCKS,
      and is labeled ``intermittent`` (never a false "daily" promise); the 2
      daily labels are trials whose draws genuinely crossed the density bar;
    - a reliable Mon-Fri habit is never demoted by density (eligible-span);
    - a 90 %-reliable weekly ritual survives its missed weeks (the 28-day
      window demanded a perfect 4/4 month: 64 % at 300 trials, now 91 %);
    - a daily habit is recognisable at day 14 (98 % at 300 trials);
    - the light random control locks NOTHING (the intermittent R bar: waking-
      arc uniform hours reach R 0.8 by luck 3 % of the time, 0.3 % at 0.9).
    """

    def _stats(
        self, gen: Callable[[random.Random], Any], horizon: int | None = None
    ) -> tuple[int, dict[str, int]]:
        stg = HARNESS._lock_set_settings(dict(HARNESS.LOCK_SETS)["current"])
        locks, shapes = 0, {}
        for i in range(20):
            days = gen(random.Random(5000 * i + 11))
            as_of = (
                HARNESS.AS_OF
                if horizon is None
                else HARNESS.RECURRENCE_START + timedelta(days=horizon - 1)
            )
            days = {d: h for d, h in days.items() if d <= as_of}
            lock = HARNESS.evaluate_locks(days, as_of, stg)
            if lock:
                locks += 1
                shapes[lock.shape] = shapes.get(lock.shape, 0) + 1
        return locks, shapes

    def test_few_weekly_locks_and_is_labeled_intermittent(self) -> None:
        locks, shapes = self._stats(lambda r: HARNESS.gen_few_weekly(r, 3.0, 0.75))
        assert locks == 20
        assert shapes["intermittent"] == 18
        assert "weekly" not in shapes

    def test_reliable_workdays_is_never_demoted(self) -> None:
        locks, shapes = self._stats(lambda r: HARNESS.gen_workdays_recurrence(r, 0.85, 0.75))
        assert (locks, shapes) == (20, {"workdays": 20})

    def test_weekly_ritual_survives_missed_weeks(self) -> None:
        locks, shapes = self._stats(lambda r: HARNESS.gen_weekly_ritual(r, 0.9, 0.75))
        assert locks == 17
        assert shapes == {"weekly": 17}

    def test_daily_is_recognisable_at_day_14(self) -> None:
        locks, shapes = self._stats(lambda r: HARNESS.gen_daily_long(r, 1.5), horizon=14)
        assert locks == 20
        assert shapes["daily"] >= 15

    def test_light_random_control_locks_nothing(self) -> None:
        locks, _shapes = self._stats(lambda r: HARNESS.gen_sparse_random(r, 2.0))
        assert locks == 0


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

    @pytest.mark.parametrize(
        ("set_name", "spec"),
        [(n, s) for n, s in HARNESS.LOCK_SETS if n in HARNESS.LOCK_SETS_FP_CLEAN],
    )
    def test_fp_clean_lock_sets_never_lock_a_random_population(
        self, set_name: str, spec: dict[str, float]
    ) -> None:
        """wk_relaxed/floor are measured counter-examples (lucky weekly locks
        on the sparse control) — pinned NOT here but in the sweep tables."""
        stg = HARNESS._lock_set_settings(spec)
        for pop_name, gen in HARNESS.RECURRENCE_TRAJECTORY_POPULATIONS:
            if pop_name not in HARNESS.RECURRENCE_FP_POPULATIONS:
                continue
            locks = sum(
                1
                for i in range(20)
                if HARNESS.evaluate_locks(gen(random.Random(5000 * i + 11)), HARNESS.AS_OF, stg)
                is not None
            )
            assert locks == 0, f"{set_name} locks {pop_name}"
