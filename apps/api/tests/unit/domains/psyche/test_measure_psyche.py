"""Unit tests for the pure aggregation core of scripts/measure_psyche.py.

The script is the ADR-104/ADR-142 production measurement instrument. Its I/O
shell (DB queries, CLI) is thin; everything computable is a pure function
tested here without a database. Loaded via importlib because ``scripts/`` is
not a package (same technique as the migration loader in
test_mood_reachability.py).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).parents[4] / "scripts" / "measure_psyche.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_psyche", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: dataclasses resolves cls.__module__ via sys.modules
    # (the canonical importlib recipe; exec alone leaves it unregistered).
    sys.modules["measure_psyche"] = module
    spec.loader.exec_module(module)
    return module


mp = _load_script()

_T0 = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def _row(
    minutes: float = 0.0,
    p: float = 0.1,
    a: float = 0.1,
    d: float = 0.3,
    dominant: str | None = "joy",
    intensity: float = 0.4,
    co_active: int = 3,
) -> object:
    """Build a SnapshotRow with sensible defaults."""
    return mp.SnapshotRow(
        created_at=_T0 + timedelta(minutes=minutes),
        mood_pleasure=p,
        mood_arousal=a,
        mood_dominance=d,
        dominant_emotion=dominant,
        emotion_intensity=intensity,
        active_emotion_count=co_active,
    )


class TestAggregateUserMetrics:
    """Pure per-user aggregation over ordered snapshot rows."""

    def test_empty_rows_yield_zero_metrics_without_crash(self) -> None:
        m = mp.aggregate_user_metrics([])
        assert m.snapshot_count == 0
        assert m.distinct_moods == 0
        assert m.top_mood is None
        assert m.dominant_stickiness is None
        assert m.post_idle_magnitude_mean is None

    def test_mood_labels_recomputed_from_pad(self) -> None:
        """History stores PAD only — labels come from classify_mood."""
        rows = [
            _row(0, p=0.15, a=0.25, d=0.40),  # determined centroid region
            _row(3, p=0.0, a=0.0, d=0.0),  # neutral
            _row(6, p=0.15, a=0.25, d=0.40),
        ]
        m = mp.aggregate_user_metrics(rows)
        assert m.snapshot_count == 3
        assert m.distinct_moods == 2
        assert m.top_mood == "determined"
        assert m.top_mood_share == pytest.approx(2 / 3)

    def test_octant_coverage_counts_sign_combinations(self) -> None:
        rows = [
            _row(0, p=0.2, a=0.2, d=0.2),  # P+A+D+
            _row(3, p=-0.2, a=0.2, d=0.2),  # P-A+D+
            _row(6, p=0.2, a=-0.2, d=-0.2),  # P+A-D-
        ]
        m = mp.aggregate_user_metrics(rows)
        assert m.octants_visited == 3
        assert m.share_dominance_negative == pytest.approx(1 / 3)
        assert m.share_arousal_negative == pytest.approx(1 / 3)

    def test_dominant_emotion_distribution_and_flagged_shares(self) -> None:
        rows = [
            _row(0, dominant="joy"),
            _row(3, dominant="joy"),
            _row(6, dominant="pride"),
            _row(9, dominant="tenderness"),
        ]
        m = mp.aggregate_user_metrics(rows)
        assert m.top_dominant_emotion == "joy"
        assert m.joy_dominant_share == pytest.approx(0.5)
        assert m.pride_dominant_share == pytest.approx(0.25)

    def test_stickiness_is_fraction_of_repeated_consecutive_dominants(self) -> None:
        rows = [
            _row(0, dominant="joy"),
            _row(3, dominant="joy"),
            _row(6, dominant="pride"),
            _row(9, dominant="pride"),
        ]
        m = mp.aggregate_user_metrics(rows)
        # transitions: joy->joy (same), joy->pride (diff), pride->pride (same) = 2/3
        assert m.dominant_stickiness == pytest.approx(2 / 3)

    def test_intensity_share_at_or_above_060(self) -> None:
        rows = [
            _row(0, intensity=0.65),
            _row(3, intensity=0.40),
            _row(6, intensity=0.60),
            _row(9, intensity=0.10),
        ]
        m = mp.aggregate_user_metrics(rows)
        assert m.intensity_ge_060_share == pytest.approx(0.5)

    def test_mean_co_active_emotions(self) -> None:
        rows = [_row(0, co_active=2), _row(3, co_active=4)]
        m = mp.aggregate_user_metrics(rows)
        assert m.mean_co_active_emotions == pytest.approx(3.0)

    def test_post_idle_magnitude_uses_rows_after_long_gaps_only(self) -> None:
        """Only the first snapshot after a >= idle-gap pause is sampled.

        Named 'post-first-message' on purpose: history rows are written after
        the appraisal push, so this is NOT a resting magnitude.
        """
        rows = [
            _row(0, p=0.9, a=0.9, d=0.9),  # first row: no preceding gap
            _row(30, p=0.8, a=0.8, d=0.8),  # 30 min gap: burst, ignored
            _row(30 + 16 * 60, p=0.3, a=0.0, d=0.0),  # 16 h gap: sampled
        ]
        m = mp.aggregate_user_metrics(rows, idle_gap_hours=12.0)
        assert m.post_idle_magnitude_mean == pytest.approx(0.3)
        assert m.post_idle_sample_count == 1

    def test_rows_are_sorted_defensively_by_created_at(self) -> None:
        """Out-of-order input must not corrupt gap/stickiness computations."""
        rows = [
            _row(30 + 16 * 60, p=0.3, a=0.0, d=0.0),
            _row(0, p=0.9, a=0.9, d=0.9),
            _row(30, p=0.8, a=0.8, d=0.8),
        ]
        m = mp.aggregate_user_metrics(rows, idle_gap_hours=12.0)
        assert m.post_idle_sample_count == 1
        assert m.post_idle_magnitude_mean == pytest.approx(0.3)


class TestClassifyCatalogue:
    """Resting-point classification of personality rows."""

    def test_classifies_resting_mood_and_flags_negative_dominance(self) -> None:
        rows = [
            mp.PersonalityRow(
                code="cynic",
                openness=0.70,
                conscientiousness=0.55,
                extraversion=0.45,
                agreeableness=0.25,
                neuroticism=0.45,
                pad_pleasure_override=None,
                pad_arousal_override=None,
                pad_dominance_override=None,
            ),
        ]
        out = mp.classify_catalogue(rows, damping=0.75, dominance_center=0.0)
        assert len(out) == 1
        assert out[0].code == "cynic"
        assert out[0].dominance == pytest.approx(0.3011250000000001, abs=1e-9)
        assert out[0].resting_mood == "determined"

        recentered = mp.classify_catalogue(rows, damping=0.75, dominance_center=0.20)
        assert recentered[0].dominance == pytest.approx(0.1011250000000001, abs=1e-9)

    def test_none_traits_fall_back_to_balanced_defaults(self) -> None:
        rows = [
            mp.PersonalityRow(
                code="untyped",
                openness=None,
                conscientiousness=None,
                extraversion=None,
                agreeableness=None,
                neuroticism=None,
                pad_pleasure_override=None,
                pad_arousal_override=None,
                pad_dominance_override=None,
            ),
        ]
        out = mp.classify_catalogue(rows, damping=0.75, dominance_center=0.0)
        # Balanced personality rests near-neutral, mildly assertive
        assert out[0].resting_mood == "neutral"
        assert 0.0 < out[0].dominance < 0.25

    def test_override_participates_in_blend(self) -> None:
        base_row = mp.PersonalityRow(
            code="x",
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.5,
            agreeableness=0.5,
            neuroticism=0.5,
            pad_pleasure_override=None,
            pad_arousal_override=None,
            pad_dominance_override=None,
        )
        overridden = mp.PersonalityRow(
            code="x-ov",
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.5,
            agreeableness=0.5,
            neuroticism=0.5,
            pad_pleasure_override=None,
            pad_arousal_override=None,
            pad_dominance_override=0.40,
        )
        base = mp.classify_catalogue([base_row], damping=0.75, dominance_center=0.0)[0]
        with_ov = mp.classify_catalogue([overridden], damping=0.75, dominance_center=0.0)[0]
        assert with_ov.dominance > base.dominance
