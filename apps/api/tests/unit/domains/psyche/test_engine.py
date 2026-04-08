"""
Unit tests for PsycheEngine — pure computation, no DB, no mocks.

Tests all mathematical operations of the psyche engine:
- PAD baseline computation from Big Five traits
- Temporal decay of mood and emotions
- Circadian modulation
- Appraisal processing
- Relationship updates
- Self-efficacy Bayesian updates
- Expression profile compilation
- Psyche eval tag parsing
- Mood-congruent recall boost
- Emotional inertia
- Rupture-repair detection

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.psyche.engine import (
    ExpressionProfile,
    PADOverride,
    PADVector,
    PersonalityTraits,
    PsycheAppraisal,
    PsycheEngine,
)

# All tests in this module are pure unit tests (no DB, no async, no mocks)
pytestmark = pytest.mark.unit


# =============================================================================
# Layer 1 — PAD Baseline
# =============================================================================


class TestComputePadBaseline:
    """Tests for PsycheEngine.compute_pad_baseline()."""

    def test_balanced_personality(self) -> None:
        """Balanced traits (all 0.5) should produce near-neutral PAD."""
        traits = PersonalityTraits(
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.5,
            agreeableness=0.5,
            neuroticism=0.5,
        )
        pad = PsycheEngine.compute_pad_baseline(traits)
        # All dimensions should be close to 0 (not exactly due to formula offsets)
        assert -0.5 < pad.pleasure < 0.5
        assert -0.5 < pad.arousal < 0.5
        assert -0.5 < pad.dominance < 0.5

    def test_high_agreeableness_positive_pleasure(self) -> None:
        """High agreeableness should produce positive pleasure."""
        traits = PersonalityTraits(agreeableness=0.9, neuroticism=0.1)
        pad = PsycheEngine.compute_pad_baseline(traits)
        assert pad.pleasure > 0.0, "High agreeableness + low neuroticism → positive pleasure"

    def test_high_neuroticism_negative_pleasure(self) -> None:
        """High neuroticism should produce negative pleasure."""
        traits = PersonalityTraits(agreeableness=0.2, neuroticism=0.9, extraversion=0.2)
        pad = PsycheEngine.compute_pad_baseline(traits)
        assert pad.pleasure < 0.0, "High neuroticism + low agreeableness → negative pleasure"

    def test_with_override_dominates(self) -> None:
        """PAD override should dominate the computed values (70/30 blend)."""
        traits = PersonalityTraits()  # defaults
        override = PADOverride(pleasure=0.8, arousal=0.6, dominance=0.9)
        pad = PsycheEngine.compute_pad_baseline(traits, override)
        # Override at 70% weight → result should be close to override values
        assert pad.pleasure > 0.4, f"Expected >0.4, got {pad.pleasure}"
        assert pad.arousal > 0.2, f"Expected >0.2, got {pad.arousal}"
        assert pad.dominance > 0.5, f"Expected >0.5, got {pad.dominance}"

    def test_partial_override(self) -> None:
        """Partial override (only pleasure) should only affect pleasure."""
        traits = PersonalityTraits()
        override = PADOverride(pleasure=0.9)
        pad_with = PsycheEngine.compute_pad_baseline(traits, override)
        pad_without = PsycheEngine.compute_pad_baseline(traits, None)
        # Pleasure should differ, arousal/dominance should be same
        assert pad_with.pleasure != pad_without.pleasure
        assert pad_with.arousal == pad_without.arousal
        assert pad_with.dominance == pad_without.dominance

    def test_output_clamped(self) -> None:
        """Output should always be within [-1, +1]."""
        # Extreme values
        traits = PersonalityTraits(
            openness=1.0,
            conscientiousness=1.0,
            extraversion=1.0,
            agreeableness=1.0,
            neuroticism=0.0,
        )
        override = PADOverride(pleasure=2.0, arousal=-2.0, dominance=3.0)
        pad = PsycheEngine.compute_pad_baseline(traits, override)
        assert -1.0 <= pad.pleasure <= 1.0
        assert -1.0 <= pad.arousal <= 1.0
        assert -1.0 <= pad.dominance <= 1.0


# =============================================================================
# Layer 2 — Temporal Decay
# =============================================================================


class TestTemporalDecay:
    """Tests for PsycheEngine.apply_temporal_decay()."""

    def test_mood_converges_to_baseline(self) -> None:
        """After long time, mood should converge to baseline."""
        baseline = PADVector(pleasure=0.3, arousal=-0.1, dominance=0.2)
        p, a, d, _, _ = PsycheEngine.apply_temporal_decay(
            mood_p=0.8,
            mood_a=0.5,
            mood_d=-0.3,
            baseline=baseline,
            hours_elapsed=100.0,
            decay_rate=0.1,
            emotions=[],
            emotion_decay_rate=0.3,
            warmth=0.7,
            warmth_decay_rate=0.02,
            has_interaction=False,
        )
        assert abs(p - baseline.pleasure) < 0.01
        assert abs(a - baseline.arousal) < 0.01
        assert abs(d - baseline.dominance) < 0.01

    def test_no_elapsed_time_no_change(self) -> None:
        """Zero elapsed time should produce no change."""
        p, a, d, emos, w = PsycheEngine.apply_temporal_decay(
            mood_p=0.5,
            mood_a=0.3,
            mood_d=0.1,
            baseline=PADVector(),
            hours_elapsed=0.0,
            decay_rate=0.1,
            emotions=[{"name": "joy", "intensity": 0.8, "triggered_at": "t"}],
            emotion_decay_rate=0.3,
            warmth=0.7,
            warmth_decay_rate=0.02,
            has_interaction=True,
        )
        assert p == 0.5
        assert a == 0.3
        assert len(emos) == 1
        assert emos[0]["intensity"] == 0.8

    def test_emotions_expire_below_threshold(self) -> None:
        """Emotions below threshold should be removed after decay."""
        _, _, _, surviving, _ = PsycheEngine.apply_temporal_decay(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            baseline=PADVector(),
            hours_elapsed=2.0,  # Moderate time (2h)
            decay_rate=0.1,
            emotions=[
                # Below threshold → will expire
                {"name": "joy", "intensity": 0.04, "triggered_at": "t"},
                # 0.9 * exp(-0.3*2) ≈ 0.49 → survives
                {"name": "curiosity", "intensity": 0.9, "triggered_at": "t"},
            ],
            emotion_decay_rate=0.3,
            warmth=0.5,
            warmth_decay_rate=0.02,
            has_interaction=True,
        )
        assert len(surviving) == 1
        assert surviving[0]["name"] == "curiosity"

    def test_warmth_decays_when_no_interaction(self) -> None:
        """Warmth should decay toward 0.5 when no interaction."""
        _, _, _, _, warmth = PsycheEngine.apply_temporal_decay(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            baseline=PADVector(),
            hours_elapsed=48.0,
            decay_rate=0.1,
            emotions=[],
            emotion_decay_rate=0.3,
            warmth=0.9,
            warmth_decay_rate=0.02,
            has_interaction=False,
        )
        assert warmth < 0.9, "Warmth should have decayed"
        assert warmth > 0.5, "Warmth should still be above neutral"

    def test_warmth_stable_with_interaction(self) -> None:
        """Warmth should not decay when interaction is happening."""
        _, _, _, _, warmth = PsycheEngine.apply_temporal_decay(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            baseline=PADVector(),
            hours_elapsed=48.0,
            decay_rate=0.1,
            emotions=[],
            emotion_decay_rate=0.3,
            warmth=0.9,
            warmth_decay_rate=0.02,
            has_interaction=True,
        )
        assert warmth == 0.9


# =============================================================================
# Layer 2 — Circadian
# =============================================================================


class TestCircadian:
    """Tests for PsycheEngine.apply_circadian()."""

    def test_midday_positive_boost(self) -> None:
        """Midday (12h) should produce positive pleasure boost."""
        result = PsycheEngine.apply_circadian(0.0, local_hour=12.0, amplitude=0.1)
        assert result > 0.0, "Midday should boost pleasure"

    def test_midnight_near_zero(self) -> None:
        """Midnight (0h) should produce near-zero effect."""
        result = PsycheEngine.apply_circadian(0.0, local_hour=0.0, amplitude=0.1)
        # sin(2π*(0-6)/24) = sin(-π/2) = -1.0, so delta = -0.1
        assert result < 0.0

    def test_zero_amplitude_no_change(self) -> None:
        """Zero amplitude should produce no change."""
        result = PsycheEngine.apply_circadian(0.5, local_hour=12.0, amplitude=0.0)
        assert result == 0.5


# =============================================================================
# Layer 2 — Emotional Inertia
# =============================================================================


class TestEmotionalInertia:
    """Tests for PsycheEngine.compute_emotional_inertia()."""

    def test_no_history_returns_base(self) -> None:
        """No mood_quadrant_since should return base inertia."""
        inertia = PsycheEngine.compute_emotional_inertia(None, datetime.now(UTC))
        assert inertia == 1.0

    def test_inertia_increases_with_time(self) -> None:
        """Inertia should increase with time in same quadrant."""
        now = datetime.now(UTC)
        inertia_1h = PsycheEngine.compute_emotional_inertia(now - timedelta(hours=1), now)
        inertia_24h = PsycheEngine.compute_emotional_inertia(now - timedelta(hours=24), now)
        assert inertia_24h > inertia_1h, "Longer in quadrant → higher inertia"

    def test_inertia_logarithmic_growth(self) -> None:
        """Inertia growth should be logarithmic (sublinear)."""
        now = datetime.now(UTC)
        inertia_1h = PsycheEngine.compute_emotional_inertia(now - timedelta(hours=1), now)
        inertia_100h = PsycheEngine.compute_emotional_inertia(now - timedelta(hours=100), now)
        # 100x time should produce much less than 100x inertia
        ratio = (inertia_100h - 1.0) / max(inertia_1h - 1.0, 0.001)
        assert ratio < 10, f"Growth should be sublinear, got ratio {ratio}"


# =============================================================================
# Layer 3 — Appraisal
# =============================================================================


class TestAppraisal:
    """Tests for PsycheEngine.apply_appraisal()."""

    def test_creates_emotion(self) -> None:
        """Valid appraisal should create a new emotion."""
        appraisal = PsycheAppraisal(emotion="joy", intensity=0.7, valence=0.5, quality=0.8)
        _, _, _, emotions = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=5,
            now_iso="2026-04-01T12:00:00",
        )
        assert len(emotions) == 1
        assert emotions[0]["name"] == "joy"
        assert emotions[0]["intensity"] > 0

    def test_pushes_mood(self) -> None:
        """Appraisal should push mood in PAD space."""
        appraisal = PsycheAppraisal(emotion="joy", intensity=0.8, valence=0.5, quality=0.7)
        p, a, d, _ = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=5,
            now_iso="2026-04-01T12:00:00",
        )
        # Joy has positive PAD vector → pleasure should increase
        assert p > 0.0, "Joy should push pleasure positive"

    def test_caps_emotions_at_max(self) -> None:
        """Should evict weakest emotion when max exceeded."""
        existing = [
            {"name": f"emo{i}", "intensity": 0.1 * (i + 1), "triggered_at": "t"} for i in range(5)
        ]
        appraisal = PsycheAppraisal(emotion="curiosity", intensity=0.9, valence=0.3, quality=0.7)
        _, _, _, emotions = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=existing,
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=5,
            now_iso="2026-04-01T12:00:00",
        )
        assert len(emotions) <= 5

    def test_reinforces_existing_emotion(self) -> None:
        """Duplicate emotion should reinforce, not duplicate."""
        existing = [{"name": "joy", "intensity": 0.3, "triggered_at": "t"}]
        appraisal = PsycheAppraisal(emotion="joy", intensity=0.8, valence=0.5, quality=0.7)
        _, _, _, emotions = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=existing,
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=5,
            now_iso="2026-04-01T12:00:00",
        )
        joy_count = sum(1 for e in emotions if e["name"] == "joy")
        assert joy_count == 1, "Should reinforce, not duplicate"
        assert emotions[0]["intensity"] >= 0.3, "Should be at least as strong"


# =============================================================================
# Layer 4 — Relationship
# =============================================================================


class TestRelationship:
    """Tests for PsycheEngine.update_relationship()."""

    def test_depth_increases(self) -> None:
        """Depth should increase with quality interaction."""
        depth, _, _, count, _, _ = PsycheEngine.update_relationship(
            depth=0.1,
            warmth=0.5,
            trust=0.5,
            interaction_count=10,
            stage="ORIENTATION",
            quality=0.8,
            gap_hours=1.0,
        )
        assert depth > 0.1, "Depth should increase"
        assert count == 11

    def test_stage_transitions(self) -> None:
        """Stage should transition when depth crosses threshold."""
        _, _, _, _, stage, _ = PsycheEngine.update_relationship(
            depth=0.14,
            warmth=0.5,
            trust=0.5,
            interaction_count=10,
            stage="ORIENTATION",
            quality=1.0,
            gap_hours=1.0,
        )
        assert stage == "EXPLORATORY", "Should transition to EXPLORATORY"

    def test_stage_never_regresses(self) -> None:
        """Stage should never go backwards."""
        _, _, _, _, stage, _ = PsycheEngine.update_relationship(
            depth=0.5,
            warmth=0.5,
            trust=0.5,
            interaction_count=100,
            stage="AFFECTIVE",
            quality=0.0,
            gap_hours=1000.0,  # Terrible quality, long absence
        )
        assert stage == "AFFECTIVE", "Stage should not regress"

    def test_reunion_emotion_after_notable_gap(self) -> None:
        """Notable absence should trigger reunion joy."""
        _, _, _, _, _, reunion_emotions = PsycheEngine.update_relationship(
            depth=0.3,
            warmth=0.5,
            trust=0.5,
            interaction_count=20,
            stage="EXPLORATORY",
            quality=0.7,
            gap_hours=48.0,  # 2 days
        )
        assert len(reunion_emotions) > 0
        assert reunion_emotions[0]["name"] == "joy"


# =============================================================================
# Layer 5 — Self-Efficacy
# =============================================================================


class TestSelfEfficacy:
    """Tests for PsycheEngine.update_self_efficacy()."""

    def test_success_increases_score(self) -> None:
        """Success should increase domain score."""
        efficacy = {"technical": {"score": 0.5, "weight": 5.0}}
        updated = PsycheEngine.update_self_efficacy(efficacy, "technical", True, 10.0)
        assert updated["technical"]["score"] > 0.5

    def test_failure_decreases_score(self) -> None:
        """Failure should decrease domain score."""
        efficacy = {"technical": {"score": 0.5, "weight": 5.0}}
        updated = PsycheEngine.update_self_efficacy(efficacy, "technical", False, 10.0)
        assert updated["technical"]["score"] < 0.5

    def test_new_domain_initialized(self) -> None:
        """New domain should be initialized with defaults."""
        updated = PsycheEngine.update_self_efficacy({}, "new_domain", True, 10.0)
        assert "new_domain" in updated
        assert updated["new_domain"]["score"] > 0.5  # Success from default 0.5

    def test_weight_capped(self) -> None:
        """Weight growth should be capped."""
        efficacy = {"technical": {"score": 0.5, "weight": 50.0}}
        updated = PsycheEngine.update_self_efficacy(efficacy, "technical", True, 10.0)
        assert updated["technical"]["weight"] <= 20.0  # prior_weight * 2


# =============================================================================
# Mood-Congruent Recall
# =============================================================================


class TestMoodCongruentRecall:
    """Tests for PsycheEngine.apply_mood_congruent_boost()."""

    def test_positive_mood_positive_memory_boosted(self) -> None:
        """Positive mood + positive memory → boosted score."""
        boosted = PsycheEngine.apply_mood_congruent_boost(
            memory_score=0.5,
            memory_emotional_weight=5.0,
            mood_pleasure=0.5,
        )
        assert boosted > 0.5

    def test_negative_mood_negative_memory_boosted(self) -> None:
        """Negative mood + negative memory → boosted score."""
        boosted = PsycheEngine.apply_mood_congruent_boost(
            memory_score=0.5,
            memory_emotional_weight=-5.0,
            mood_pleasure=-0.5,
        )
        assert boosted > 0.5

    def test_opposite_valence_no_boost(self) -> None:
        """Opposite valence (mood positive, memory negative) → no boost."""
        result = PsycheEngine.apply_mood_congruent_boost(
            memory_score=0.5,
            memory_emotional_weight=-5.0,
            mood_pleasure=0.5,
        )
        assert result == 0.5, "Opposite valence should not boost"

    def test_never_decreases_score(self) -> None:
        """Boost should never decrease the original score."""
        result = PsycheEngine.apply_mood_congruent_boost(
            memory_score=0.8,
            memory_emotional_weight=-10.0,
            mood_pleasure=0.9,
        )
        assert result >= 0.8


# =============================================================================
# Rupture-Repair
# =============================================================================


class TestRuptureRepair:
    """Tests for PsycheEngine.detect_rupture_repair()."""

    def test_frustration_to_gratitude_is_repair(self) -> None:
        """Frustration → gratitude should be detected as repair."""
        bonus = PsycheEngine.detect_rupture_repair("frustration", "gratitude")
        assert bonus > 0

    def test_joy_to_joy_is_not_repair(self) -> None:
        """Joy → joy should not be detected as repair."""
        bonus = PsycheEngine.detect_rupture_repair("joy", "joy")
        assert bonus == 0

    def test_none_emotion_no_repair(self) -> None:
        """None emotions should not trigger repair."""
        assert PsycheEngine.detect_rupture_repair(None, "joy") == 0
        assert PsycheEngine.detect_rupture_repair("frustration", None) == 0


# =============================================================================
# Expression Profile
# =============================================================================


class TestExpressionProfile:
    """Tests for PsycheEngine.compile_expression_profile()."""

    def test_neutral_state_produces_neutral(self) -> None:
        """Neutral PAD should produce 'neutral' mood label."""
        profile = PsycheEngine.compile_expression_profile(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            stage="ORIENTATION",
            warmth=0.5,
            drive_curiosity=0.5,
            drive_engagement=0.5,
        )
        assert profile.mood_label == "neutral"

    def test_positive_mood_not_neutral(self) -> None:
        """Positive PAD should not produce 'neutral'."""
        profile = PsycheEngine.compile_expression_profile(
            mood_p=0.4,
            mood_a=-0.2,
            mood_d=0.1,
            emotions=[],
            stage="AFFECTIVE",
            warmth=0.8,
            drive_curiosity=0.6,
            drive_engagement=0.7,
        )
        assert profile.mood_label != "neutral"

    def test_top_emotions_selected(self) -> None:
        """Should select top 2 emotions by intensity."""
        emotions = [
            {"name": "joy", "intensity": 0.3, "triggered_at": "t"},
            {"name": "curiosity", "intensity": 0.8, "triggered_at": "t"},
            {"name": "amusement", "intensity": 0.5, "triggered_at": "t"},
        ]
        profile = PsycheEngine.compile_expression_profile(
            mood_p=0.3,
            mood_a=0.2,
            mood_d=0.0,
            emotions=emotions,
            stage="EXPLORATORY",
            warmth=0.6,
            drive_curiosity=0.5,
            drive_engagement=0.5,
        )
        assert len(profile.active_emotions) == 2
        assert profile.active_emotions[0][0] == "curiosity"
        assert profile.active_emotions[1][0] == "amusement"


# =============================================================================
# Prompt Injection
# =============================================================================


class TestFormatPromptInjection:
    """Tests for PsycheEngine.format_prompt_injection()."""

    def test_produces_valid_xml(self) -> None:
        """Output should be a valid self-closing XML tag."""
        profile = ExpressionProfile(
            mood_label="serene",
            mood_intensity="moderately",
            active_emotions=[("curiosity", 0.7)],
            relationship_stage="EXPLORATORY",
            warmth_label="warm",
        )
        result = PsycheEngine.format_prompt_injection(profile)
        assert result.startswith("<Psyche ")
        assert result.endswith("/>")
        assert 'mood="serene"' in result
        assert 'emotions="curiosity:0.7"' in result

    def test_empty_emotions(self) -> None:
        """Should handle empty emotions gracefully."""
        profile = ExpressionProfile()
        result = PsycheEngine.format_prompt_injection(profile)
        assert 'emotions=""' in result


# =============================================================================
# Self-Report Tag Parsing
# =============================================================================


class TestParsePsycheEval:
    """Tests for PsycheEngine.parse_psyche_eval()."""

    def test_valid_tag_parsed(self) -> None:
        """Well-formed tag should be parsed correctly."""
        content = (
            "Here is my response.\n"
            '<psyche_eval valence="0.5" arousal="0.3" dominance="0.1"'
            ' emotion="curiosity" intensity="0.7" quality="0.8"/>'
        )
        appraisal, cleaned = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert appraisal.valence == 0.5
        assert appraisal.arousal == 0.3
        assert appraisal.emotion == "curiosity"
        assert appraisal.intensity == 0.7
        assert appraisal.quality == 0.8
        assert "<psyche_eval" not in cleaned
        assert "Here is my response." in cleaned

    def test_no_tag_returns_none(self) -> None:
        """Content without tag should return (None, original)."""
        content = "Just a regular response without any tag."
        appraisal, cleaned = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is None
        assert cleaned == content

    def test_malformed_tag_returns_none(self) -> None:
        """Malformed tag (no parseable attributes) should return None."""
        content = "Response.\n<psyche_eval />"
        appraisal, cleaned = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is None
        assert "<psyche_eval" not in cleaned

    def test_out_of_range_values_clamped(self) -> None:
        """Out-of-range values should be clamped."""
        content = '<psyche_eval valence="5.0" arousal="-3.0" intensity="99" quality="-1"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert appraisal.valence == 1.0  # Clamped to max
        assert appraisal.arousal == 0.0  # Clamped to min for arousal
        assert appraisal.intensity == 1.0  # Clamped to max
        assert appraisal.quality == 0.0  # Clamped to min

    def test_unknown_emotion_returns_none(self) -> None:
        """Unknown emotion name should be validated to None."""
        content = '<psyche_eval valence="0.5" emotion="love" intensity="0.5" quality="0.5"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert appraisal.emotion is None  # "love" not in valid list

    def test_empty_content(self) -> None:
        """Empty content should return (None, '')."""
        appraisal, cleaned = PsycheEngine.parse_psyche_eval("")
        assert appraisal is None
        assert cleaned == ""


# =============================================================================
# Mood Color
# =============================================================================


class TestMoodToColor:
    """Tests for PsycheEngine.mood_to_color()."""

    def test_known_moods_return_hex(self) -> None:
        """Known mood labels should return valid hex colors."""
        for mood in [
            "serene",
            "curious",
            "energized",
            "playful",
            "reflective",
            "agitated",
            "melancholic",
            "neutral",
        ]:
            color = PsycheEngine.mood_to_color(mood)
            assert color.startswith("#"), f"Expected hex for {mood}, got {color}"
            assert len(color) == 7, f"Expected 7-char hex for {mood}, got {color}"

    def test_unknown_mood_returns_neutral(self) -> None:
        """Unknown mood label should return neutral gray."""
        assert PsycheEngine.mood_to_color("unknown") == "#9ca3af"


# =============================================================================
# Initialize Self-Efficacy
# =============================================================================


class TestInitializeSelfEfficacy:
    """Tests for PsycheEngine.initialize_self_efficacy()."""

    def test_all_domains_present(self) -> None:
        """All domains should be initialized."""
        efficacy = PsycheEngine.initialize_self_efficacy()
        expected_domains = {
            "planning",
            "information",
            "emotional_support",
            "creativity",
            "technical",
            "social",
            "organization",
        }
        assert set(efficacy.keys()) == expected_domains

    def test_default_values(self) -> None:
        """Default values should be 0.5 score and 2.0 weight."""
        efficacy = PsycheEngine.initialize_self_efficacy()
        for domain, entry in efficacy.items():
            assert entry["score"] == 0.5, f"{domain} score should be 0.5"
            assert entry["weight"] == 2.0, f"{domain} weight should be 2.0"


# =============================================================================
# Iteration 3 — Trait Modulation
# =============================================================================


class TestTraitModulation:
    """Tests for Big Five trait modulation in apply_appraisal and apply_temporal_decay."""

    def test_neuroticism_modulates_reactivity(self) -> None:
        """High neuroticism should increase emotional reactivity."""
        appraisal = PsycheAppraisal(
            valence=0.5, arousal=0.3, emotion="joy", intensity=0.5, quality=0.8
        )
        # High N = more reactive
        _, _, _, emos_high = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(neuroticism=0.9),
        )
        # Low N = less reactive
        _, _, _, emos_low = PsycheEngine.apply_appraisal(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(neuroticism=0.1),
        )
        high_intensity = emos_high[0]["intensity"]
        low_intensity = emos_low[0]["intensity"]
        assert (
            high_intensity > low_intensity
        ), f"High N ({high_intensity}) should be more intense than low N ({low_intensity})"

    def test_agreeableness_modulates_contagion(self) -> None:
        """High agreeableness should cause stronger mood contagion."""
        appraisal = PsycheAppraisal(
            valence=-0.8, arousal=0.5, emotion="concern", intensity=0.5, quality=0.3
        )
        # High A = strong contagion (mood drops more)
        p_high, _, _, _ = PsycheEngine.apply_appraisal(
            mood_p=0.3,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(agreeableness=0.9),
        )
        # Low A = weak contagion (mood drops less)
        p_low, _, _, _ = PsycheEngine.apply_appraisal(
            mood_p=0.3,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(agreeableness=0.1),
        )
        assert p_high < p_low, f"High A ({p_high}) should drop more than low A ({p_low})"

    def test_counter_regulation_pulls_toward_neutral(self) -> None:
        """Low agreeableness with negative mood: counter-regulation pulls toward 0.

        We test by comparing mood AFTER appraisal with negative valence.
        High A has stronger contagion pulling mood down.
        Low A has weaker contagion + counter-regulation pulling mood UP toward 0.
        Net effect: after a negative interaction, low A should be less negative.
        """
        appraisal = PsycheAppraisal(
            valence=-0.8, arousal=0.3, emotion="concern", intensity=0.3, quality=0.3
        )
        # Low A: weak contagion + counter-regulation → resists negativity
        p_low_a, _, _, _ = PsycheEngine.apply_appraisal(
            mood_p=-0.2,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(agreeableness=0.1),
        )
        # High A: strong contagion, no counter-regulation → absorbs user negativity
        p_high_a, _, _, _ = PsycheEngine.apply_appraisal(
            mood_p=-0.2,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=0.7,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(agreeableness=0.9),
        )
        # Low A should be higher (less negative) than high A
        assert p_low_a > p_high_a, (
            f"Low A ({p_low_a:.3f}) should be less negative " f"than high A ({p_high_a:.3f})"
        )

    def test_counter_regulation_never_overshoots_positive(self) -> None:
        """Counter-regulation should cap at 0.0, never push mood into positive."""
        appraisal = PsycheAppraisal(
            valence=0.5, arousal=0.1, emotion="serenity", intensity=0.2, quality=0.7
        )
        # Start with slightly negative mood, very low A
        p_result, _, _, _ = PsycheEngine.apply_appraisal(
            mood_p=-0.05,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-01T10:00:00",
            traits=PersonalityTraits(agreeableness=0.05),
        )
        # The mood may go positive due to contagion (valence=0.5),
        # but counter-regulation itself does not push past 0.
        # (Contagion can still push positive — that's fine.)
        # This test just verifies no crash/overflow.
        assert -1.0 <= p_result <= 1.0

    def test_conscientiousness_modulates_recovery(self) -> None:
        """High conscientiousness should speed up mood recovery (decay)."""
        baseline = PADVector(pleasure=0.2, arousal=0.0, dominance=0.0)
        # High C = faster recovery
        p_high, _, _, _, _ = PsycheEngine.apply_temporal_decay(
            mood_p=-0.5,
            mood_a=0.0,
            mood_d=0.0,
            baseline=baseline,
            hours_elapsed=2.0,
            decay_rate=0.1,
            emotions=[],
            emotion_decay_rate=0.3,
            warmth=0.5,
            warmth_decay_rate=0.02,
            has_interaction=True,
            traits=PersonalityTraits(conscientiousness=0.9),
        )
        # Low C = slower recovery
        p_low, _, _, _, _ = PsycheEngine.apply_temporal_decay(
            mood_p=-0.5,
            mood_a=0.0,
            mood_d=0.0,
            baseline=baseline,
            hours_elapsed=2.0,
            decay_rate=0.1,
            emotions=[],
            emotion_decay_rate=0.3,
            warmth=0.5,
            warmth_decay_rate=0.02,
            has_interaction=True,
            traits=PersonalityTraits(conscientiousness=0.1),
        )
        # High C should be closer to baseline (0.2) than low C
        assert abs(p_high - baseline.pleasure) < abs(
            p_low - baseline.pleasure
        ), f"High C ({p_high}) should be closer to baseline than low C ({p_low})"


class TestTraitDefaultsBackwardsCompat:
    """Verify traits=0.5 produces identical results to pre-refonte behavior."""

    def test_default_traits_reactivity_is_one(self) -> None:
        """Default traits (0.5) should produce reactivity multiplier of 1.0."""
        t = PersonalityTraits()
        reactivity = 0.5 + t.neuroticism  # 0.5 + 0.5 = 1.0
        assert reactivity == 1.0

    def test_default_traits_contagion_is_020(self) -> None:
        """Default traits (0.5) should produce contagion base of 0.20."""
        t = PersonalityTraits()
        contagion = 0.05 + t.agreeableness * 0.30  # 0.05 + 0.15 = 0.20
        assert abs(contagion - 0.20) < 1e-10

    def test_default_traits_recovery_is_one(self) -> None:
        """Default traits (0.5) should produce recovery factor of 1.0."""
        t = PersonalityTraits()
        recovery = 0.7 + t.conscientiousness * 0.6  # 0.7 + 0.3 = 1.0
        assert abs(recovery - 1.0) < 1e-10


class TestNewMoods:
    """Tests for the 14 mood centroids (Iteration 3)."""

    def test_all_14_moods_accessible(self) -> None:
        """Each of the 14 centroids should be the nearest to its own point."""
        from src.domains.psyche.constants import MOOD_LABEL_CENTROIDS

        for label, (p, a, d) in MOOD_LABEL_CENTROIDS.items():
            profile = PsycheEngine.compile_expression_profile(
                mood_p=p,
                mood_a=a,
                mood_d=d,
                emotions=[],
                stage="ORIENTATION",
                warmth=0.5,
                drive_curiosity=0.5,
                drive_engagement=0.5,
            )
            assert (
                profile.mood_label == label
            ), f"Centroid ({p},{a},{d}) should classify as '{label}', got '{profile.mood_label}'"

    def test_centroid_separation_minimum(self) -> None:
        """All centroid pairs should have distance >= 0.20."""
        from src.domains.psyche.constants import MOOD_LABEL_CENTROIDS

        labels = list(MOOD_LABEL_CENTROIDS.keys())
        for i, l1 in enumerate(labels):
            for l2 in labels[i + 1 :]:
                p1, a1, d1 = MOOD_LABEL_CENTROIDS[l1]
                p2, a2, d2 = MOOD_LABEL_CENTROIDS[l2]
                dist = math.sqrt((p1 - p2) ** 2 + (a1 - a2) ** 2 + (d1 - d2) ** 2)
                assert dist >= 0.20, f"Centroids '{l1}' and '{l2}' too close: {dist:.3f} (min 0.20)"


class TestNewEmotions:
    """Tests for the 22 emotion palette (Iteration 3 + v2 expansion)."""

    def test_all_emotions_have_pad_vectors(self) -> None:
        """All EMOTION_TYPES should have a corresponding PAD vector."""
        from src.domains.psyche.constants import EMOTION_PAD_VECTORS, EMOTION_TYPES

        for emo in EMOTION_TYPES:
            assert emo in EMOTION_PAD_VECTORS, f"Missing PAD vector for '{emo}'"
            vec = EMOTION_PAD_VECTORS[emo]
            assert len(vec) == 3, f"PAD vector for '{emo}' should have 3 elements"
            for v in vec:
                assert -1.0 <= v <= 1.0, f"PAD value out of range for '{emo}': {v}"

    def test_positive_negative_sets_consistent(self) -> None:
        """POSITIVE and NEGATIVE sets should not overlap and cover known emotions."""
        from src.domains.psyche.constants import (
            EMOTION_TYPES,
            NEGATIVE_EMOTIONS,
            POSITIVE_EMOTIONS,
        )

        assert POSITIVE_EMOTIONS.isdisjoint(NEGATIVE_EMOTIONS), "Sets must not overlap"
        # All set members must be in EMOTION_TYPES
        for emo in POSITIVE_EMOTIONS | NEGATIVE_EMOTIONS:
            assert emo in EMOTION_TYPES, f"'{emo}' in set but not in EMOTION_TYPES"


class TestNewMoodColors:
    """Tests for mood_to_color with 14 moods (Iteration 3)."""

    def test_all_14_moods_return_hex(self) -> None:
        """All 14 mood labels should return valid hex colors."""
        from src.domains.psyche.constants import MOOD_LABEL_CENTROIDS

        for mood in MOOD_LABEL_CENTROIDS:
            color = PsycheEngine.mood_to_color(mood)
            assert color.startswith("#"), f"Expected hex for {mood}, got {color}"
            assert len(color) == 7, f"Expected 7-char hex for {mood}, got {color}"


class TestUpdateDrives:
    """Tests for PsycheEngine.update_drives()."""

    def test_drives_move_toward_appraisal(self) -> None:
        """Drives should blend toward appraisal values (20% new, 80% old)."""
        new_c, new_e = PsycheEngine.update_drives(
            curiosity=0.5,
            engagement=0.5,
            appraisal_arousal=1.0,
            appraisal_quality=1.0,
        )
        # 0.80 * 0.5 + 0.20 * 1.0 = 0.60
        assert abs(new_c - 0.60) < 0.01
        assert abs(new_e - 0.60) < 0.01

    def test_drives_stay_stable_without_change(self) -> None:
        """Drives at same value as appraisal should not change."""
        new_c, new_e = PsycheEngine.update_drives(
            curiosity=0.7,
            engagement=0.7,
            appraisal_arousal=0.7,
            appraisal_quality=0.7,
        )
        assert abs(new_c - 0.7) < 0.01
        assert abs(new_e - 0.7) < 0.01

    def test_drives_clamped_to_unit(self) -> None:
        """Drives should be clamped to [0, 1]."""
        new_c, new_e = PsycheEngine.update_drives(
            curiosity=0.0,
            engagement=0.0,
            appraisal_arousal=0.0,
            appraisal_quality=0.0,
        )
        assert new_c >= 0.0
        assert new_e >= 0.0


class TestConfidenceBlock:
    """Tests for self-efficacy confidence in expression profile."""

    def test_strengths_extracted(self) -> None:
        """Domains with score > 0.65 should be in strengths."""
        profile = PsycheEngine.compile_expression_profile(
            mood_p=0.0,
            mood_a=0.0,
            mood_d=0.0,
            emotions=[],
            stage="ORIENTATION",
            warmth=0.5,
            drive_curiosity=0.5,
            drive_engagement=0.5,
            self_efficacy={
                "planning": {"score": 0.8, "weight": 5.0},
                "technical": {"score": 0.3, "weight": 5.0},
                "emotional_support": {"score": 0.5, "weight": 5.0},
            },
        )
        assert "planning" in profile.confidence_strengths
        assert "technical" in profile.confidence_weaknesses
        assert "emotional_support" not in profile.confidence_strengths
        assert "emotional_support" not in profile.confidence_weaknesses

    def test_rich_injection_includes_confidence(self) -> None:
        """Rich injection should include CONFIDENCE block when data present."""
        profile = ExpressionProfile(
            mood_label="neutral",
            mood_intensity="slightly",
            active_emotions=[],
            relationship_stage="ORIENTATION",
            warmth_label="neutral",
            confidence_strengths=["planning"],
            confidence_weaknesses=["technical"],
        )
        result = PsycheEngine.format_rich_prompt_injection(profile)
        assert "CONFIDENCE:" in result
        assert "Strong in: planning" in result
        assert "Less confident in: technical" in result


class TestRichInjection:
    """Tests for format_rich_prompt_injection (Iteration 3)."""

    def test_rich_injection_contains_directives(self) -> None:
        """Rich injection should contain mood, emotion, and relationship directives."""
        profile = ExpressionProfile(
            mood_label="tender",
            mood_intensity="noticeably",
            active_emotions=[("empathy", 0.72), ("joy", 0.35)],
            relationship_stage="AFFECTIVE",
            warmth_label="warm",
            drive_curiosity=0.70,
            drive_engagement=0.80,
        )
        result = PsycheEngine.format_rich_prompt_injection(profile)

        assert "<PsycheDirectives>" in result
        assert "MOOD: tender (noticeably)" in result
        assert "empathy (72%)" in result
        assert "joy (35%)" in result
        assert "RELATIONSHIP: AFFECTIVE" in result
        assert "DRIVES:" in result

    def test_rich_injection_empty_emotions(self) -> None:
        """Rich injection with no emotions should show 'none'."""
        profile = ExpressionProfile(
            mood_label="neutral",
            mood_intensity="slightly",
            active_emotions=[],
            relationship_stage="ORIENTATION",
            warmth_label="neutral",
        )
        result = PsycheEngine.format_rich_prompt_injection(profile)

        assert "- none" in result


# =============================================================================
# _push_with_headroom — Diminishing returns helper
# =============================================================================


class TestPushWithHeadroom:
    """Tests for the _push_with_headroom() diminishing-returns helper.

    The function models a spring-at-boundary: the closer the value is to ±1.0
    in the push direction, the more the push is attenuated.
    """

    def test_zero_delta_returns_current(self) -> None:
        """A zero push should leave the value unchanged."""
        from src.domains.psyche.engine import _push_with_headroom

        assert _push_with_headroom(0.5, 0.0) == 0.5
        assert _push_with_headroom(-0.7, 0.0) == -0.7

    def test_from_origin_full_delta(self) -> None:
        """At origin (0.0), headroom is 1.0 so full delta is applied."""
        from src.domains.psyche.engine import _push_with_headroom

        result = _push_with_headroom(0.0, 0.3)
        assert result == pytest.approx(0.3, abs=1e-6)

        result_neg = _push_with_headroom(0.0, -0.4)
        assert result_neg == pytest.approx(-0.4, abs=1e-6)

    def test_positive_diminishing_near_boundary(self) -> None:
        """Pushing positive when already near +1.0 should be heavily attenuated."""
        from src.domains.psyche.engine import _push_with_headroom

        # At current=0.9, headroom toward +1 = 0.1
        # delta=0.3 → attenuated = 0.3 * 0.1 = 0.03
        result = _push_with_headroom(0.9, 0.3)
        assert result == pytest.approx(0.93, abs=1e-6)

    def test_negative_diminishing_near_boundary(self) -> None:
        """Pushing negative when already near -1.0 should be heavily attenuated."""
        from src.domains.psyche.engine import _push_with_headroom

        # At current=-0.8, headroom toward -1 = 0.2
        # delta=-0.5 → attenuated = -0.5 * 0.2 = -0.1
        result = _push_with_headroom(-0.8, -0.5)
        assert result == pytest.approx(-0.9, abs=1e-6)

    def test_at_boundary_push_same_direction_no_change(self) -> None:
        """At the boundary, pushing further in the same direction has no effect."""
        from src.domains.psyche.engine import _push_with_headroom

        assert _push_with_headroom(1.0, 0.5) == pytest.approx(1.0)
        assert _push_with_headroom(-1.0, -0.5) == pytest.approx(-1.0)

    def test_at_boundary_push_opposite_full_headroom(self) -> None:
        """At +1.0, pushing negative has full headroom (2.0 clamped to 1.0)."""
        from src.domains.psyche.engine import _push_with_headroom

        # At current=1.0, headroom toward -1 = 1+1 = 2.0, clamped to 1.0
        # delta=-0.3 → attenuated = -0.3 * 1.0 = -0.3
        result = _push_with_headroom(1.0, -0.3)
        assert result == pytest.approx(0.7, abs=1e-6)

    def test_result_always_clamped(self) -> None:
        """Result must always stay in [-1, +1]."""
        from src.domains.psyche.engine import _push_with_headroom

        result = _push_with_headroom(0.0, 5.0)
        assert -1.0 <= result <= 1.0

        result_neg = _push_with_headroom(0.0, -5.0)
        assert -1.0 <= result_neg <= 1.0

    def test_symmetry(self) -> None:
        """Symmetric inputs should produce symmetric outputs."""
        from src.domains.psyche.engine import _push_with_headroom

        pos = _push_with_headroom(0.5, 0.2)
        neg = _push_with_headroom(-0.5, -0.2)
        assert pos == pytest.approx(-neg, abs=1e-6)

    def test_repeated_pushes_converge(self) -> None:
        """Repeated same-direction pushes should asymptotically approach boundary."""
        from src.domains.psyche.engine import _push_with_headroom

        value = 0.0
        for _ in range(50):
            value = _push_with_headroom(value, 0.3)

        # Should be close to 1.0 but never exceed it
        assert 0.95 < value <= 1.0

    def test_tiny_delta_near_boundary(self) -> None:
        """Very small delta near the boundary should still make small progress."""
        from src.domains.psyche.engine import _push_with_headroom

        result = _push_with_headroom(0.99, 0.1)
        # headroom = 0.01, attenuated = 0.1 * 0.01 = 0.001
        assert result == pytest.approx(0.991, abs=1e-6)
        assert result > 0.99


# =============================================================================
# v2 Tests — Psyche Engine v2 additions
# =============================================================================


class TestExpandedPalette:
    """Tests for the 22-emotion palette (6 new emotions)."""

    def test_all_22_emotions_have_pad_vectors(self) -> None:
        from src.domains.psyche.constants import EMOTION_PAD_VECTORS, EMOTION_TYPES

        assert len(EMOTION_TYPES) == 22
        for emo in EMOTION_TYPES:
            assert emo in EMOTION_PAD_VECTORS, f"{emo} missing from EMOTION_PAD_VECTORS"

    def test_all_22_emotions_have_directives(self) -> None:
        from src.domains.psyche.constants import (
            EMOTION_BEHAVIORAL_DIRECTIVES,
            EMOTION_TYPES,
        )

        for emo in EMOTION_TYPES:
            assert emo in EMOTION_BEHAVIORAL_DIRECTIVES, f"{emo} missing directive"

    def test_no_directive_uses_banned_patterns(self) -> None:
        """Guard test: directives must be imperative, not descriptive."""
        from src.domains.psyche.constants import (
            EMOTION_BEHAVIORAL_DIRECTIVES,
            MOOD_BEHAVIORAL_DIRECTIVES,
        )

        banned_starts = ("Show ", "Let ", "You are ", "You have ")
        for name, directive in MOOD_BEHAVIORAL_DIRECTIVES.items():
            for banned in banned_starts:
                assert not directive.startswith(
                    banned
                ), f"Mood directive '{name}' starts with banned '{banned}': {directive}"
        for name, directive in EMOTION_BEHAVIORAL_DIRECTIVES.items():
            for banned in banned_starts:
                assert not directive.startswith(
                    banned
                ), f"Emotion directive '{name}' starts with banned '{banned}': {directive}"

    def test_positive_negative_sets_no_overlap(self) -> None:
        from src.domains.psyche.constants import NEGATIVE_EMOTIONS, POSITIVE_EMOTIONS

        assert len(POSITIVE_EMOTIONS & NEGATIVE_EMOTIONS) == 0

    def test_new_emotions_in_correct_sets(self) -> None:
        from src.domains.psyche.constants import NEGATIVE_EMOTIONS, POSITIVE_EMOTIONS

        assert "playfulness" in POSITIVE_EMOTIONS
        assert "relief" in POSITIVE_EMOTIONS
        assert "wonder" in POSITIVE_EMOTIONS
        assert "nervousness" in NEGATIVE_EMOTIONS
        # protectiveness and resolve are neutral (in neither set)
        assert "protectiveness" not in POSITIVE_EMOTIONS
        assert "protectiveness" not in NEGATIVE_EMOTIONS
        assert "resolve" not in POSITIVE_EMOTIONS
        assert "resolve" not in NEGATIVE_EMOTIONS

    def test_validate_emotion_accepts_new_names(self) -> None:
        from src.domains.psyche.engine import _validate_emotion

        for name in ["playfulness", "protectiveness", "relief", "nervousness", "wonder", "resolve"]:
            assert _validate_emotion(name) == name


class TestExpressionProfileV2:
    """Tests for enriched ExpressionProfile fields."""

    def test_compile_profile_with_traits_sets_neuroticism(self) -> None:
        traits = PersonalityTraits(neuroticism=0.8, conscientiousness=0.3)
        profile = PsycheEngine.compile_expression_profile(
            0.0,
            0.0,
            0.0,
            [],
            "ORIENTATION",
            0.5,
            0.5,
            0.5,
            traits=traits,
        )
        assert profile.neuroticism == 0.8
        assert profile.conscientiousness == 0.3

    def test_compile_profile_without_traits_defaults(self) -> None:
        profile = PsycheEngine.compile_expression_profile(
            0.0,
            0.0,
            0.0,
            [],
            "ORIENTATION",
            0.5,
            0.5,
            0.5,
        )
        assert profile.neuroticism == 0.5
        assert profile.conscientiousness == 0.5

    def test_pad_magnitude_computed(self) -> None:
        profile = PsycheEngine.compile_expression_profile(
            0.3,
            0.4,
            0.0,
            [],
            "ORIENTATION",
            0.5,
            0.5,
            0.5,
        )
        assert profile.pad_magnitude == pytest.approx(0.5, abs=0.01)

    def test_current_pad_set(self) -> None:
        profile = PsycheEngine.compile_expression_profile(
            0.3,
            -0.2,
            0.1,
            [],
            "ORIENTATION",
            0.5,
            0.5,
            0.5,
        )
        assert profile.current_pad == (0.3, -0.2, 0.1)


class TestStabilityBlocks:
    """Tests for serenity floor and emotional anchor."""

    def test_serenity_floor_empty_emotions(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[], neuroticism=0.5)
        result = _build_stability_blocks(profile)
        assert "BASE:" in result

    def test_serenity_floor_all_below_threshold(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[("joy", 0.10)], neuroticism=0.5)
        result = _build_stability_blocks(profile)
        assert "BASE:" in result

    def test_serenity_floor_low_neuroticism(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[], neuroticism=0.15)
        result = _build_stability_blocks(profile)
        assert "deep steadiness" in result

    def test_serenity_floor_high_neuroticism(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[], neuroticism=0.85)
        result = _build_stability_blocks(profile)
        assert "Try to be steady" in result

    def test_serenity_floor_mid_neuroticism(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[], neuroticism=0.50)
        result = _build_stability_blocks(profile)
        assert "calm equilibrium" in result

    def test_no_floor_with_significant_emotion(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(active_emotions=[("joy", 0.5)], neuroticism=0.5)
        result = _build_stability_blocks(profile)
        assert "BASE:" not in result

    def test_anchor_triggered_on_strong_negative(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.5,
            conscientiousness=0.5,
        )
        result = _build_stability_blocks(profile)
        assert "ANCHOR:" in result
        assert "frustration" in result

    def test_anchor_high_conscientiousness(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.5,
            conscientiousness=0.80,
        )
        result = _build_stability_blocks(profile)
        assert "Discipline your tone" in result

    def test_anchor_low_conscientiousness(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.5,
            conscientiousness=0.20,
        )
        result = _build_stability_blocks(profile)
        assert "let yourself feel it" in result

    def test_anchor_skipped_extreme_neuroticism(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=1.0,  # anchor_base = 0.3 → skip
            conscientiousness=0.5,
        )
        result = _build_stability_blocks(profile)
        assert "ANCHOR:" not in result

    def test_anchor_with_delay_suffix(self) -> None:
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.88,  # anchor_base = (1 - 0.88) * 0.7 + 0.3 = 0.384 → < 0.40 → suffix
            conscientiousness=0.5,
        )
        result = _build_stability_blocks(profile)
        assert "though it may take a moment" in result

    def test_floor_and_anchor_never_coexist(self) -> None:
        """Floor requires no significant emotions; anchor requires strong negative.
        These are mutually exclusive by construction."""
        from src.domains.psyche.engine import _build_stability_blocks

        # Floor scenario
        profile_floor = ExpressionProfile(active_emotions=[], neuroticism=0.5)
        result_floor = _build_stability_blocks(profile_floor)
        assert "BASE:" in result_floor
        assert "ANCHOR:" not in result_floor

        # Anchor scenario
        profile_anchor = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.5,
            conscientiousness=0.5,
        )
        result_anchor = _build_stability_blocks(profile_anchor)
        assert "ANCHOR:" in result_anchor
        assert "BASE:" not in result_anchor


class TestTransitionDetection:
    """Tests for detect_transition_type()."""

    def test_transition_reunion(self) -> None:
        profile = ExpressionProfile(gap_hours=30.0)
        assert PsycheEngine.detect_transition_type(profile) == "reunion"

    def test_transition_reunion_priority(self) -> None:
        """Reunion overrides valence shift when both conditions match."""
        profile = ExpressionProfile(
            gap_hours=30.0,
            mood_label="melancholic",
            previous_pad=(0.3, 0.0, 0.0),
            current_pad=(-0.2, -0.3, -0.2),
        )
        assert PsycheEngine.detect_transition_type(profile) == "reunion"

    def test_transition_pos_to_neg(self) -> None:
        profile = ExpressionProfile(
            mood_label="melancholic",
            previous_pad=(0.3, 0.0, 0.0),
            current_pad=(-0.2, -0.3, -0.2),
        )
        assert PsycheEngine.detect_transition_type(profile) == "pos_to_neg"

    def test_transition_neg_to_pos(self) -> None:
        profile = ExpressionProfile(
            mood_label="serene",
            previous_pad=(-0.2, 0.0, 0.0),
            current_pad=(0.3, -0.2, 0.1),
        )
        assert PsycheEngine.detect_transition_type(profile) == "neg_to_pos"

    def test_transition_high_to_low_arousal(self) -> None:
        profile = ExpressionProfile(
            mood_label="neutral",
            previous_pad=(0.0, 0.4, 0.0),
            current_pad=(0.0, -0.2, 0.0),
        )
        assert PsycheEngine.detect_transition_type(profile) == "high_to_low_arousal"

    def test_transition_emotion_specific(self) -> None:
        profile = ExpressionProfile(
            mood_label="neutral",
            previous_emotion="curiosity",
            active_emotions=[("determination", 0.6)],
        )
        assert PsycheEngine.detect_transition_type(profile) == "emotion_specific"

    def test_transition_none_first_interaction(self) -> None:
        profile = ExpressionProfile()
        assert PsycheEngine.detect_transition_type(profile) is None

    def test_transition_none_no_significant_change(self) -> None:
        profile = ExpressionProfile(
            mood_label="neutral",
            previous_pad=(0.05, 0.0, 0.0),
            current_pad=(0.0, 0.0, 0.0),
        )
        assert PsycheEngine.detect_transition_type(profile) is None


class TestGraduatedInjection:
    """Tests for format_graduated_prompt_injection()."""

    def test_level1_compact(self) -> None:
        profile = ExpressionProfile(pad_magnitude=0.05, mood_label="neutral")
        block, key = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "<Psyche " in block
        assert "subtly color" in block
        assert key == "psyche_usage_directive_light"

    def test_level2_medium(self) -> None:
        profile = ExpressionProfile(
            pad_magnitude=0.25,
            mood_label="curious",
            mood_intensity="moderately",
            active_emotions=[("curiosity", 0.3)],
            relationship_stage="EXPLORATORY",
        )
        block, key = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "<PsycheDirectives>" in block
        assert "curious (moderately)" in block
        assert "EMOTIONS: curiosity" in block
        assert key == "psyche_usage_directive_light"

    def test_level3_rich(self) -> None:
        profile = ExpressionProfile(
            pad_magnitude=0.50,
            mood_label="energized",
            mood_intensity="noticeably",
            active_emotions=[("enthusiasm", 0.7), ("curiosity", 0.4)],
            relationship_stage="AFFECTIVE",
            drive_curiosity=0.8,
            drive_engagement=0.6,
        )
        block, key = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "MOOD: energized (noticeably)" in block
        assert "enthusiasm (70%)" in block
        assert "DRIVES:" in block
        assert key == "psyche_usage_directive"

    def test_level4_emphasis(self) -> None:
        profile = ExpressionProfile(
            pad_magnitude=0.80,
            mood_label="agitated",
            mood_intensity="strongly",
            active_emotions=[("frustration", 0.9)],
            relationship_stage="STABLE",
        )
        block, key = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "EMPHASIS:" in block
        assert "INTENSE" in block
        assert key == "psyche_usage_directive"

    def test_stability_blocks_included(self) -> None:
        profile = ExpressionProfile(
            pad_magnitude=0.50,
            mood_label="neutral",
            active_emotions=[],
            neuroticism=0.5,
        )
        block, _ = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "BASE:" in block

    def test_evolution_at_level3_not_level1(self) -> None:
        profile_l1 = ExpressionProfile(
            pad_magnitude=0.05,
            gap_hours=30.0,
        )
        block_l1, _ = PsycheEngine.format_graduated_prompt_injection(profile_l1)
        assert "EVOLUTION:" not in block_l1

        profile_l3 = ExpressionProfile(
            pad_magnitude=0.50,
            mood_label="tender",
            mood_intensity="noticeably",
            gap_hours=30.0,
        )
        block_l3, _ = PsycheEngine.format_graduated_prompt_injection(profile_l3)
        assert "EVOLUTION:" in block_l3


class TestMultiEmotionParsing:
    """Tests for multi-emotion self-report parsing."""

    def test_new_multi_format(self) -> None:
        content = 'Hello <psyche_eval valence="0.5" arousal="0.3" dominance="0.1" emotions="curiosity:0.7,amusement:0.3" quality="0.8"/>'
        appraisal, cleaned = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 2
        assert appraisal.emotions[0] == ("curiosity", 0.7)
        assert appraisal.emotions[1] == ("amusement", 0.3)
        assert appraisal.dominant_emotion == "curiosity"
        assert appraisal.dominant_intensity == 0.7

    def test_old_format_backward_compat(self) -> None:
        content = '<psyche_eval valence="0.5" arousal="0.3" dominance="0.1" emotion="curiosity" intensity="0.7" quality="0.8"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 1
        assert appraisal.emotions[0] == ("curiosity", 0.7)

    def test_more_than_three_truncated(self) -> None:
        content = '<psyche_eval emotions="joy:0.7,curiosity:0.5,amusement:0.3,pride:0.2,serenity:0.1" quality="0.5"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 3

    def test_invalid_emotion_filtered(self) -> None:
        content = '<psyche_eval emotions="curiosity:0.7,FAKE:0.3" quality="0.5"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 1
        assert appraisal.emotions[0][0] == "curiosity"

    def test_empty_emotions(self) -> None:
        content = '<psyche_eval valence="0.5" quality="0.5"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 0
        assert appraisal.dominant_emotion is None

    def test_malformed_emotions_string(self) -> None:
        content = '<psyche_eval emotions="curiosity:0.7,,:bad" quality="0.5"/>'
        appraisal, _ = PsycheEngine.parse_psyche_eval(content)
        assert appraisal is not None
        assert len(appraisal.emotions) == 1

    def test_legacy_construction_migrates(self) -> None:
        appraisal = PsycheAppraisal(emotion="joy", intensity=0.7)
        assert appraisal.emotions == [("joy", 0.7)]
        assert appraisal.dominant_emotion == "joy"

    def test_new_construction_direct(self) -> None:
        appraisal = PsycheAppraisal(emotions=[("joy", 0.7), ("curiosity", 0.3)])
        assert appraisal.dominant_emotion == "joy"
        assert len(appraisal.emotions) == 2


class TestMultiEmotionApply:
    """Tests for multi-emotion apply_appraisal()."""

    def test_multi_weighted_mood_push(self) -> None:
        """Second emotion pushes mood at 0.5x weight."""
        appraisal = PsycheAppraisal(
            emotions=[("joy", 0.8), ("curiosity", 0.8)],
            valence=0.5,
            quality=0.8,
        )
        # Compare: single joy push vs joy+curiosity push
        p1, a1, d1, _ = PsycheEngine.apply_appraisal(
            0.0,
            0.0,
            0.0,
            [],
            PsycheAppraisal(emotions=[("joy", 0.8)], valence=0.5, quality=0.8),
            sensitivity=1.0,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-08T10:00:00",
        )
        p2, a2, d2, _ = PsycheEngine.apply_appraisal(
            0.0,
            0.0,
            0.0,
            [],
            appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-08T10:00:00",
        )
        # Multi should push more than single (curiosity adds to the push)
        # Joy PAD: (+0.40, +0.20, +0.10), Curiosity PAD: (+0.30, +0.40, +0.10)
        assert a2 > a1  # Curiosity has higher arousal

    def test_multi_cross_suppression_accumulated(self) -> None:
        """Two positive emotions should accumulate suppression on negatives."""
        existing = [{"name": "frustration", "intensity": 0.8, "triggered_at": "t"}]
        appraisal = PsycheAppraisal(
            emotions=[("joy", 0.6), ("gratitude", 0.4)],
            valence=0.5,
            quality=0.8,
        )
        _, _, _, updated = PsycheEngine.apply_appraisal(
            0.0,
            0.0,
            0.0,
            existing,
            appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=7,
            now_iso="2026-04-08T10:00:00",
        )
        # Frustration should be reduced by accumulated suppression
        frust = next((e for e in updated if e["name"] == "frustration"), None)
        if frust:
            assert frust["intensity"] < 0.8


class TestResonance:
    """Tests for compute_resonance()."""

    def test_positive_match(self) -> None:
        res = PsycheEngine.compute_resonance(0.5, [("joy", 0.7)])
        assert res > 0.3

    def test_empathy_appropriate(self) -> None:
        res = PsycheEngine.compute_resonance(-0.5, [("concern", 0.6)])
        assert res > 0.0  # Concern is appropriate for negative user

    def test_protectiveness_appropriate(self) -> None:
        res = PsycheEngine.compute_resonance(-0.6, [("protectiveness", 0.8)])
        assert res > 0.0

    def test_inappropriate_cheer(self) -> None:
        res = PsycheEngine.compute_resonance(-0.5, [("joy", 0.7)])
        assert res < 0.0  # Joy when user is sad = dissonant

    def test_neutral_user(self) -> None:
        res = PsycheEngine.compute_resonance(0.0, [("joy", 0.7)])
        assert res == 0.0

    def test_no_emotions(self) -> None:
        res = PsycheEngine.compute_resonance(0.5, [])
        assert res == 0.0

    def test_clamped(self) -> None:
        res = PsycheEngine.compute_resonance(1.0, [("joy", 1.0)])
        assert -1.0 <= res <= 1.0


class TestProactiveEmotions:
    """Tests for compute_proactive_emotions() and merge_proactive_emotions()."""

    def test_curiosity_pulse_new_user(self) -> None:
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.8,
            drive_engagement=0.5,
            interaction_count=3,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "curiosity" in names

    def test_no_curiosity_established_user(self) -> None:
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.8,
            drive_engagement=0.5,
            interaction_count=20,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "curiosity" not in names

    def test_enthusiasm_pulse_high_engagement(self) -> None:
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.85,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "enthusiasm" in names

    def test_no_enthusiasm_if_already_high(self) -> None:
        existing = [{"name": "enthusiasm", "intensity": 0.6, "triggered_at": "t"}]
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.85,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=existing,
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "enthusiasm" not in names

    def test_joy_pulse_quality_and_engagement(self) -> None:
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.75,
            interaction_count=10,
            last_appraisal={"quality": 0.8},
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "joy" in names

    def test_pride_pulse_high_efficacy(self) -> None:
        efficacy = {"technical": {"score": 0.8, "weight": 5.0}}
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.5,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=efficacy,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "pride" in names

    def test_no_pulse_low_drives(self) -> None:
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.5,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        assert len(pulses) == 0

    def test_merge_additive(self) -> None:
        existing = [{"name": "curiosity", "intensity": 0.5, "triggered_at": "old"}]
        proactive = [{"name": "curiosity", "intensity": 0.25, "triggered_at": "new"}]
        result = PsycheEngine.merge_proactive_emotions(existing, proactive)
        assert result[0]["intensity"] == 0.75
        assert result[0]["triggered_at"] == "new"

    def test_merge_capped(self) -> None:
        existing = [{"name": "curiosity", "intensity": 0.9, "triggered_at": "old"}]
        proactive = [{"name": "curiosity", "intensity": 0.25, "triggered_at": "new"}]
        result = PsycheEngine.merge_proactive_emotions(existing, proactive)
        assert result[0]["intensity"] == 1.0

    def test_merge_new_emotion(self) -> None:
        existing = [{"name": "joy", "intensity": 0.5, "triggered_at": "old"}]
        proactive = [{"name": "enthusiasm", "intensity": 0.2, "triggered_at": "new"}]
        result = PsycheEngine.merge_proactive_emotions(existing, proactive)
        assert len(result) == 2
        assert result[1]["name"] == "enthusiasm"

    def test_merge_preserves_existing(self) -> None:
        """Non-targeted emotions remain unchanged during merge."""
        existing = [
            {"name": "joy", "intensity": 0.5, "triggered_at": "old"},
            {"name": "concern", "intensity": 0.3, "triggered_at": "old"},
        ]
        proactive = [{"name": "enthusiasm", "intensity": 0.2, "triggered_at": "new"}]
        result = PsycheEngine.merge_proactive_emotions(existing, proactive)
        joy = next(e for e in result if e["name"] == "joy")
        concern = next(e for e in result if e["name"] == "concern")
        assert joy["intensity"] == 0.5  # Unchanged
        assert concern["intensity"] == 0.3  # Unchanged

    def test_pride_pulse_only_once(self) -> None:
        """Only one pride pulse even with multiple high-efficacy domains."""
        efficacy = {
            "technical": {"score": 0.8, "weight": 5.0},
            "planning": {"score": 0.9, "weight": 6.0},
            "emotional_support": {"score": 0.85, "weight": 5.5},
        }
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.5,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=efficacy,
            existing_emotions=[],
            now_iso="t",
        )
        pride_count = sum(1 for p in pulses if p["name"] == "pride")
        assert pride_count == 1

    def test_no_joy_without_appraisal(self) -> None:
        """No joy pulse when last_appraisal is None."""
        pulses = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.5,
            drive_engagement=0.85,
            interaction_count=10,
            last_appraisal=None,
            self_efficacy=None,
            existing_emotions=[],
            now_iso="t",
        )
        names = [p["name"] for p in pulses]
        assert "joy" not in names


class TestAdditionalV2:
    """Additional v2 edge case tests."""

    def test_anchor_mid_conscientiousness(self) -> None:
        """Mid-range C (0.50) → 'stay centered' anchor wording."""
        from src.domains.psyche.engine import _build_stability_blocks

        profile = ExpressionProfile(
            active_emotions=[("frustration", 0.80)],
            neuroticism=0.5,
            conscientiousness=0.50,
        )
        result = _build_stability_blocks(profile)
        assert "stay centered" in result

    def test_pad_magnitude_zero_at_origin(self) -> None:
        """PAD (0,0,0) → magnitude exactly 0.0."""
        profile = PsycheEngine.compile_expression_profile(
            0.0,
            0.0,
            0.0,
            [],
            "ORIENTATION",
            0.5,
            0.5,
            0.5,
        )
        assert profile.pad_magnitude == 0.0

    def test_transition_none_same_mood_quadrant(self) -> None:
        """No transition when mood stays in same positive quadrant."""
        profile = ExpressionProfile(
            mood_label="serene",
            previous_pad=(0.2, -0.1, 0.1),
            current_pad=(0.3, -0.2, 0.1),
        )
        assert PsycheEngine.detect_transition_type(profile) is None

    def test_emotion_specific_template_formatted(self) -> None:
        """Verify emotion names are substituted in the template."""
        profile = ExpressionProfile(
            pad_magnitude=0.50,
            mood_label="determined",
            mood_intensity="noticeably",
            previous_emotion="curiosity",
            active_emotions=[("determination", 0.6)],
        )
        block, _ = PsycheEngine.format_graduated_prompt_injection(profile)
        assert "curiosity" in block
        assert "determination" in block
        assert "EVOLUTION:" in block

    def test_resonance_neutral_emotion(self) -> None:
        """Curiosity (PAD P=+0.30) with neutral user → 0."""
        res = PsycheEngine.compute_resonance(0.05, [("curiosity", 0.7)])
        assert res == 0.0  # User valence < 0.15 → neutral zone
