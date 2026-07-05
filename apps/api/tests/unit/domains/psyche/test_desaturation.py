"""Deterministic de-saturation tests for the Psyche Engine (ADR-068 refinement).

Production v1 data (3 months, main user) proved the mood was *confined*: arousal and
dominance were locked positive, only 4 of 14 moods were ever reached, and pride was
the dominant emotion 61% of the time (an automatic self-efficacy pulse re-fired on
every message). These tests pin the mechanisms that de-saturate the engine:

- F3: the automatic pride pulse is gone — pride must be earned via the appraisal.
- F2: the PAD baseline can be damped toward neutral (the raw Mehrabian mapping skewed
      high-conscientiousness personalities to a high dominance baseline).
- F1: the optional per-interaction relaxation is ASYMMETRIC (anti-ratchet only).
- Aggregate: a saturated personality now escapes the 2-mood lock.

Pure engine, no LLM, no DB. F6 (self-report debias) is a prompt change and is
validated separately (Phase 2 blind evaluation).
"""

from __future__ import annotations

import math

import pytest

from src.core.constants import (
    PSYCHE_AD_RELAXATION_DEFAULT,
    PSYCHE_BASELINE_DAMPING_DEFAULT,
    PSYCHE_EMOTION_DECAY_RATE_DEFAULT,
    PSYCHE_EMOTION_MAX_ACTIVE_DEFAULT,
)
from src.domains.psyche.constants import MOOD_EXPRESSION_GRAMMAR, MOOD_LABEL_CENTROIDS
from src.domains.psyche.engine import (
    ExpressionProfile,
    PADVector,
    PersonalityTraits,
    PsycheAppraisal,
    PsycheEngine,
)

pytestmark = pytest.mark.unit

# Cynic = the production power-user's personality (high C → high dominance baseline).
CYNIC = PersonalityTraits(
    openness=0.70,
    conscientiousness=0.55,
    extraversion=0.45,
    agreeableness=0.25,
    neuroticism=0.45,
)

# A realistic, debiased conversation spanning the full palette at low-ish intensities
# (what the F6 self-report should produce). Each item: (emotions, valence, quality).
VARIED_STREAM: list[tuple[list[tuple[str, float]], float, float]] = [
    ([("gratitude", 0.4)], 0.5, 0.8),
    ([("serenity", 0.25)], 0.1, 0.6),
    ([("curiosity", 0.3)], 0.1, 0.7),
    ([("empathy", 0.5), ("concern", 0.4)], -0.5, 0.4),
    ([("tenderness", 0.45), ("empathy", 0.3)], 0.0, 0.7),
    ([("amusement", 0.4), ("playfulness", 0.3)], 0.4, 0.8),
    ([("serenity", 0.2)], 0.0, 0.6),
    ([("pride", 0.5)], 0.5, 0.9),
    ([("relief", 0.35), ("serenity", 0.25)], 0.2, 0.7),
    ([("curiosity", 0.35)], 0.1, 0.7),
    ([("melancholy", 0.45), ("concern", 0.3)], -0.4, 0.4),
    ([("tenderness", 0.4)], -0.1, 0.6),
    ([("serenity", 0.2)], 0.0, 0.6),
    ([("enthusiasm", 0.5), ("joy", 0.35)], 0.6, 0.9),
    ([("determination", 0.4)], 0.2, 0.7),
    ([("gratitude", 0.3)], 0.4, 0.8),
]

# Established-user self-efficacy (would have triggered the old per-message pride pulse).
_HIGH_EFFICACY = {"emotional_support": {"score": 0.9, "weight": 10.0}}


def _simulate(
    damping: float,
    relaxation: float,
    max_active: int,
    emotion_decay: float,
    *,
    traits: PersonalityTraits = CYNIC,
) -> list[str]:
    """Run the varied stream through the engine mirroring the service per-turn flow.

    Returns the sequence of mood labels (one per turn).
    """
    baseline = PsycheEngine.compute_pad_baseline(traits, damping=damping)
    p, a, d = baseline.pleasure, baseline.arousal, baseline.dominance
    emotions: list[dict] = []
    labels: list[str] = []
    for i, (emos, valence, quality) in enumerate(VARIED_STREAM):
        ts = f"2026-01-01T00:{i:02d}:00+00:00"
        p, a, d, emotions, _ = PsycheEngine.apply_temporal_decay(
            mood_p=p,
            mood_a=a,
            mood_d=d,
            baseline=baseline,
            hours_elapsed=0.1,
            decay_rate=0.1,
            emotions=emotions,
            emotion_decay_rate=emotion_decay,
            warmth=0.7,
            warmth_decay_rate=0.02,
            has_interaction=True,
            traits=traits,
        )
        proactive = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.4,
            drive_engagement=0.8,
            interaction_count=100,
            last_appraisal={"quality": quality},
            self_efficacy=_HIGH_EFFICACY,
            existing_emotions=emotions,
            now_iso=ts,
        )
        if proactive:
            emotions = PsycheEngine.merge_proactive_emotions(emotions, proactive)
        appraisal = PsycheAppraisal(
            valence=valence, arousal=0.4, emotions=list(emos), quality=quality
        )
        p, a, d, emotions = PsycheEngine.apply_appraisal(
            mood_p=p,
            mood_a=a,
            mood_d=d,
            emotions=emotions,
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=max_active,
            now_iso=ts,
            traits=traits,
            baseline=baseline if relaxation > 0 else None,
            relaxation=relaxation,
        )
        labels.append(PsycheEngine.classify_mood(p, a, d))
    return labels


# =============================================================================
# F3 — the automatic pride pulse is removed
# =============================================================================


def test_pride_pulse_removed_from_proactive_emotions() -> None:
    """High self-efficacy must no longer auto-inject a pride pulse (the v1 61% cause)."""
    pulses = PsycheEngine.compute_proactive_emotions(
        drive_curiosity=0.4,
        drive_engagement=0.8,
        interaction_count=100,
        last_appraisal={"quality": 0.9},
        self_efficacy={d: {"score": 0.95, "weight": 12.0} for d in ("planning", "technical")},
        existing_emotions=[],
        now_iso="2026-01-01T00:00:00+00:00",
    )
    assert all(p["name"] != "pride" for p in pulses)


def test_pride_only_present_when_earned() -> None:
    """Across a stream with pride reported only once, pride is never the state's
    permanent resident it was in production (it enters only after it is earned)."""
    baseline = PsycheEngine.compute_pad_baseline(CYNIC, damping=PSYCHE_BASELINE_DAMPING_DEFAULT)
    p, a, d = baseline.pleasure, baseline.arousal, baseline.dominance
    emotions: list[dict] = []
    pride_before_earned = False
    for i, (emos, valence, quality) in enumerate(VARIED_STREAM):
        ts = f"2026-01-01T00:{i:02d}:00+00:00"
        proactive = PsycheEngine.compute_proactive_emotions(
            drive_curiosity=0.4,
            drive_engagement=0.8,
            interaction_count=100,
            last_appraisal={"quality": quality},
            self_efficacy=_HIGH_EFFICACY,
            existing_emotions=emotions,
            now_iso=ts,
        )
        if proactive:
            emotions = PsycheEngine.merge_proactive_emotions(emotions, proactive)
        # Turn 7 is the first (and only) message that reports pride.
        if i < 7 and any(e["name"] == "pride" for e in emotions):
            pride_before_earned = True
        appraisal = PsycheAppraisal(
            valence=valence, arousal=0.4, emotions=list(emos), quality=quality
        )
        p, a, d, emotions = PsycheEngine.apply_appraisal(
            mood_p=p,
            mood_a=a,
            mood_d=d,
            emotions=emotions,
            appraisal=appraisal,
            sensitivity=1.0,
            inertia=1.0,
            max_active=PSYCHE_EMOTION_MAX_ACTIVE_DEFAULT,
            now_iso=ts,
            traits=CYNIC,
        )
    assert not pride_before_earned, "pride appeared before it was ever reported (auto-injected)"


# =============================================================================
# F2 — baseline damping
# =============================================================================


def test_baseline_damping_identity_at_one() -> None:
    """damping=1.0 reproduces the raw Mehrabian baseline (backwards-compatible)."""
    raw = PsycheEngine.compute_pad_baseline(CYNIC)
    same = PsycheEngine.compute_pad_baseline(CYNIC, damping=1.0)
    assert (same.pleasure, same.arousal, same.dominance) == (
        raw.pleasure,
        raw.arousal,
        raw.dominance,
    )


def test_baseline_damping_scales_toward_neutral() -> None:
    """Damping shrinks each axis by the factor, preserving sign and lowering |mood|."""
    raw = PsycheEngine.compute_pad_baseline(CYNIC)
    damped = PsycheEngine.compute_pad_baseline(CYNIC, damping=0.75)
    assert math.isclose(damped.dominance, raw.dominance * 0.75, abs_tol=1e-9)
    assert math.isclose(damped.arousal, raw.arousal * 0.75, abs_tol=1e-9)
    assert math.isclose(damped.pleasure, raw.pleasure * 0.75, abs_tol=1e-9)
    # The production pathology: Cynic dominance baseline was ~0.40; damping pulls it down.
    assert raw.dominance > 0.35
    assert damped.dominance < raw.dominance


# =============================================================================
# F1 — asymmetric anti-ratchet relaxation
# =============================================================================


def test_relaxation_enabled_by_default() -> None:
    """F1 ships ENABLED (>0): Phase-2 end-to-end testing showed the real LLM keeps
    emitting the personality's high-arousal emotions turn after turn, ratcheting
    arousal/dominance up without it. relaxation=0.0 must still be an exact no-op
    (the knob can be turned off)."""
    assert PSYCHE_AD_RELAXATION_DEFAULT > 0.0
    args: dict = {
        "mood_p": 0.5,
        "mood_a": 0.5,
        "mood_d": 0.5,
        "emotions": [],
        "appraisal": PsycheAppraisal(valence=0.2, arousal=0.4, emotions=[("joy", 0.4)]),
        "sensitivity": 1.0,
        "inertia": 1.0,
        "max_active": 4,
        "now_iso": "2026-01-01T00:00:00+00:00",
        "traits": CYNIC,
    }
    without = PsycheEngine.apply_appraisal(**args)
    with_zero = PsycheEngine.apply_appraisal(
        **args, baseline=PADVector(0.0, 0.0, 0.2), relaxation=0.0
    )
    assert without[:3] == with_zero[:3]


def test_relaxation_is_asymmetric() -> None:
    """Above-baseline axes are pulled down; below-baseline axes are left free."""
    baseline = PADVector(pleasure=0.0, arousal=0.0, dominance=0.3)
    # Arousal ABOVE baseline (0.6 > 0.0) → must be pulled down toward baseline.
    # Dominance BELOW baseline (-0.4 < 0.3) → must be untouched by relaxation.
    no_emotion = PsycheAppraisal(valence=0.0, arousal=0.4, emotions=[])
    p, a, d, _ = PsycheEngine.apply_appraisal(
        mood_p=0.0,
        mood_a=0.6,
        mood_d=-0.4,
        emotions=[],
        appraisal=no_emotion,
        sensitivity=1.0,
        inertia=1.0,
        max_active=4,
        now_iso="2026-01-01T00:00:00+00:00",
        traits=CYNIC,
        baseline=baseline,
        relaxation=0.5,
    )
    # (no emotion, no contagion since valence==mood_p==0) — only relaxation acts.
    assert a < 0.6  # arousal pulled down from above baseline
    assert math.isclose(a, 0.3, abs_tol=1e-6)  # 0.0 + (0.6-0.0)*0.5 = 0.3
    assert math.isclose(d, -0.4, abs_tol=1e-6)  # below baseline → untouched


# =============================================================================
# Aggregate — a saturated personality escapes the lock
# =============================================================================


def test_desaturation_escapes_the_two_mood_lock() -> None:
    """With the shipped defaults, the Cynic mood escapes the production 2-mood lock
    (determined/energized) and reaches at least one calmer/curious/neutral mood."""
    new_labels = _simulate(
        damping=PSYCHE_BASELINE_DAMPING_DEFAULT,
        relaxation=PSYCHE_AD_RELAXATION_DEFAULT,
        max_active=PSYCHE_EMOTION_MAX_ACTIVE_DEFAULT,
        emotion_decay=PSYCHE_EMOTION_DECAY_RATE_DEFAULT,
    )
    old_labels = _simulate(damping=1.0, relaxation=0.0, max_active=7, emotion_decay=0.3)

    new_distinct = set(new_labels)
    old_distinct = set(old_labels)

    # The old engine locks the Cynic into the high-arousal/high-dominance corner.
    assert old_distinct <= {"determined", "energized", "defiant"}
    # The new engine visits strictly more moods and reaches beyond the assertive corner.
    assert len(new_distinct) > len(old_distinct)
    assert new_distinct - {
        "determined",
        "energized",
        "defiant",
    }, f"mood never left the assertive corner: {sorted(new_distinct)}"


def test_resting_state_is_milder_than_v1() -> None:
    """After a long idle gap the mood settles to a milder resting magnitude than the
    raw baseline (production rested at determined/0.41; damping pulls that down)."""
    raw_base = PsycheEngine.compute_pad_baseline(CYNIC)
    damped_base = PsycheEngine.compute_pad_baseline(CYNIC, damping=PSYCHE_BASELINE_DAMPING_DEFAULT)
    raw_mag = math.sqrt(raw_base.pleasure**2 + raw_base.arousal**2 + raw_base.dominance**2)
    damped_mag = math.sqrt(
        damped_base.pleasure**2 + damped_base.arousal**2 + damped_base.dominance**2
    )
    assert damped_mag < raw_mag
    assert damped_mag < 0.35  # leaves the "rich injection" band at rest


# =============================================================================
# A-E — embodied voice injection
# =============================================================================


def _profile(
    mood: str,
    *,
    intensity: str = "noticeably",
    magnitude: float = 0.45,
    emotions: list | None = None,
) -> ExpressionProfile:
    return ExpressionProfile(
        mood_label=mood,
        mood_intensity=intensity,
        active_emotions=emotions if emotions is not None else [],
        relationship_stage="STABLE",
        warmth_label="warm",
        pad_magnitude=magnitude,
    )


def _embodied(profile: ExpressionProfile) -> str:
    """Combine the engine's dynamic block with the versioned frame template (as the
    service does), so tests assert on the full injected <InnerVoice> block."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    dynamic, key = PsycheEngine.format_embodied_prompt_injection(profile)
    return str(load_prompt(key)).format(dynamic=dynamic)


def test_embodied_covers_every_mood_with_concrete_grammar() -> None:
    """Every mood label yields its concrete expression grammar (no generic fallback)."""
    for mood in MOOD_LABEL_CENTROIDS:
        block = _embodied(_profile(mood))
        assert MOOD_EXPRESSION_GRAMMAR[mood] in block, f"grammar missing for {mood}"
        assert "<InnerVoice>" in block and "</InnerVoice>" in block


def test_embodied_reconciles_with_personality() -> None:
    """The block frames the state as the <Personality>'s voice this turn (lever D)."""
    block = _embodied(_profile("melancholic"))
    assert "You are the assistant described in <Personality>" in block
    assert "melancholic" in block
    assert "IS your voice this turn" in block


def test_embodied_emotion_lead() -> None:
    """A top emotion becomes the explicit lead."""
    block = _embodied(_profile("tender", emotions=[("tenderness", 0.6)]))
    assert "Let tenderness genuinely lead" in block


def test_embodied_keeps_anti_tell_guardrails() -> None:
    """Hard guardrails survive the reframe (never name / attribute / change facts)."""
    block = _embodied(_profile("energized"))
    assert 'NEVER say "I feel"' in block
    assert "NEVER attribute it to the user" in block
    assert "The FACTS of your answer stay the same" in block


def test_embodied_grants_form_authority() -> None:
    """Lever B/E: the state may reshape presentation (length, suggestion count)."""
    block = _embodied(_profile("melancholic"))
    assert "MAY reshape the usual presentation" in block
    assert "how many suggestions" in block


def test_embodied_faint_level_is_compact() -> None:
    """Below 0.20 magnitude the block is the compact 'faint undercurrent' form."""
    block = _embodied(_profile("neutral", intensity="slightly", magnitude=0.1))
    assert "faint" in block
    assert "You are the assistant described in <Personality>" not in block  # full block omitted


def test_embodied_intensity_modulates_lean_in() -> None:
    """Intensity label changes how hard to lean into the voice."""
    strong = _embodied(_profile("determined", intensity="strongly", magnitude=0.7))
    slight = _embodied(_profile("determined", intensity="slightly", magnitude=0.4))
    assert "permeate every line" in strong
    assert "subtle" in slight


def test_embodied_hedges_only_on_weak_confidence() -> None:
    """A genuinely weak domain surfaces a hedging line; a fresh profile does not."""
    weak = _profile("determined")
    weak.confidence_weaknesses = ["technical"]
    assert "Less sure of technical" in _embodied(weak)
    assert "Less sure of" not in _embodied(_profile("determined"))


def test_proactive_embodied_template_renders_grammar() -> None:
    """The proactive channels' embodied frame renders the SAME concrete grammar (A-E),
    in a short-message form, with the anti-tell guardrails intact."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    block = str(load_prompt("psyche_embodied_proactive")).format(
        intensity="noticeably",
        mood="tender",
        lead=" — tenderness colours it",
        grammar=MOOD_EXPRESSION_GRAMMAR["tender"],
    )
    assert "<InnerVoice>" in block and "</InnerVoice>" in block
    assert "noticeably tender" in block
    assert MOOD_EXPRESSION_GRAMMAR["tender"] in block
    assert "never attribute it to the user" in block
