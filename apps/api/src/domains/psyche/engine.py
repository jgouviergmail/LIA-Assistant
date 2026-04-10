"""
Psyche Engine — Pure computation engine for psychological state dynamics.

This module contains ALL mathematical logic for the Psyche system.
It is stateless, has no DB access, no LLM calls, no async — pure math.
Every method is a @staticmethod for explicit input/output and full testability.

Architecture (ALMA-inspired 3 layers + relationship + drives):
    Layer 1 — Personality: Big Five traits → PAD baseline (permanent)
    Layer 2 — Mood: PAD space with temporal decay toward baseline (hours)
    Layer 3 — Emotion: Discrete emotions with exponential decay (minutes)
    Layer 4 — Relationship: 4-stage depth/warmth tracking (weeks/months)
    Layer 5 — Drives: Curiosity and engagement (session-scale)

References:
    - ALMA (Gebhard, 2005): Layered affect model
    - OCC (Ortony, Clore & Collins, 1988): Appraisal theory
    - Mehrabian (1996): Big Five → PAD mapping
    - WASABI (Becker-Asano, 2008): Mass-spring mood dynamics

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domains.psyche.constants import (
    ANCHOR_DIRECTIVES_BY_CONSCIENTIOUSNESS,
    ANCHOR_NEGATIVE_INTENSITY_THRESHOLD,
    EMOTION_BEHAVIORAL_DIRECTIVES,
    EMOTION_MIN_INTENSITY,
    EMOTION_PAD_VECTORS,
    EMOTION_REUNION_JOY_BASE,
    EMOTION_SIGNIFICANT_THRESHOLD,
    GAP_LONG_HOURS,
    GAP_NOTABLE_HOURS,
    GAP_SIGNIFICANT_HOURS,
    MOOD_BEHAVIORAL_DIRECTIVES,
    MOOD_INTENSITY_LABELS,
    MOOD_LABEL_CENTROIDS,
    NEGATIVE_EMOTIONS,
    NEGATIVE_MOOD_LABELS,
    POSITIVE_EMOTIONS,
    POSITIVE_MOOD_LABELS,
    PSYCHE_EVAL_ATTR_PATTERN,
    PSYCHE_EVAL_TAG_PATTERN,
    RELATIONSHIP_DEPTH_THRESHOLDS,
    RELATIONSHIP_STAGE_DIRECTIVES,
    RELATIONSHIP_STAGES,
    REPAIR_TRUST_BONUS,
    SELF_EFFICACY_DEFAULT_SCORE,
    SELF_EFFICACY_DEFAULT_WEIGHT,
    SELF_EFFICACY_DOMAINS,
    SERENITY_FLOOR_DIRECTIVES,
    TRANSITION_NARRATIVE_TEMPLATES,
    WARMTH_LABELS,
)

# =============================================================================
# Data Structures
# =============================================================================


@dataclass(frozen=True)
class PersonalityTraits:
    """Big Five personality traits [0.0, 1.0]."""

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5


@dataclass(frozen=True)
class PADVector:
    """Point in PAD (Pleasure-Arousal-Dominance) space [-1.0, +1.0]."""

    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0

    @property
    def magnitude(self) -> float:
        """Euclidean distance from origin."""
        return math.sqrt(self.pleasure**2 + self.arousal**2 + self.dominance**2)

    def quadrant_key(self) -> tuple[bool, bool, bool]:
        """Return octant classification (sign of each dimension)."""
        return (self.pleasure >= 0, self.arousal >= 0, self.dominance >= 0)


@dataclass(frozen=True)
class PADOverride:
    """Optional PAD baseline overrides for caricature personalities."""

    pleasure: float | None = None
    arousal: float | None = None
    dominance: float | None = None


@dataclass(frozen=True)
class ActiveEmotion:
    """A discrete emotion with intensity and timestamp."""

    name: str
    intensity: float  # [0.0, 1.0]
    triggered_at: str  # ISO 8601


@dataclass
class PsycheAppraisal:
    """Parsed from <psyche_eval .../> tag in LLM response.

    Represents the LLM's self-evaluation of the interaction.
    Supports both single-emotion (v1) and multi-emotion (v2) formats.
    """

    valence: float = 0.0  # [-1, +1] conversation positivity
    arousal: float = 0.5  # [0, 1] interaction energy
    dominance: float = 0.0  # [-1, +1] who led the exchange
    emotions: list[tuple[str, float]] = field(default_factory=list)  # [(name, intensity)]
    quality: float = 0.5  # [0, 1] overall interaction quality
    # Legacy fields — backward compat for v1 construction and external readers.
    # If `emotion` is set at construction and `emotions` is empty, __post_init__
    # migrates the legacy fields into `emotions`. Do NOT modify after construction.
    emotion: str | None = field(default=None, repr=False)
    intensity: float = field(default=0.5, repr=False)

    def __post_init__(self) -> None:
        """Migrate legacy single-emotion fields to emotions list."""
        if not self.emotions and self.emotion:
            self.emotions = [(self.emotion, self.intensity)]

    @property
    def dominant_emotion(self) -> str | None:
        """First (strongest) emotion name, or None."""
        return self.emotions[0][0] if self.emotions else None

    @property
    def dominant_intensity(self) -> float:
        """First (strongest) emotion intensity, or 0.0."""
        return self.emotions[0][1] if self.emotions else 0.0


@dataclass
class ExpressionProfile:
    """Compiled output injected into the response prompt.

    Derived from all psyche layers, this drives the LLM's tone and style.
    """

    mood_label: str = "neutral"
    mood_intensity: str = "slightly"
    active_emotions: list[tuple[str, float]] = field(default_factory=list)
    relationship_stage: str = "ORIENTATION"
    warmth_label: str = "neutral"
    drive_curiosity: float = 0.5
    drive_engagement: float = 0.5
    confidence_strengths: list[str] = field(default_factory=list)
    confidence_weaknesses: list[str] = field(default_factory=list)
    # Evolution awareness (filled from last_appraisal)
    previous_mood: str | None = None
    previous_emotion: str | None = None
    # v2 additions — graduated directives, stability, transitions
    pad_magnitude: float = 0.0
    current_pad: tuple[float, float, float] | None = None
    previous_pad: tuple[float, float, float] | None = None
    gap_hours: float = 0.0
    neuroticism: float = 0.5
    conscientiousness: float = 0.5


# =============================================================================
# PsycheEngine — Stateless computation
# =============================================================================


class PsycheEngine:
    """Pure computation engine for psyche dynamics.

    All methods are @staticmethod: no instance state, no side effects.
    Input → math → output. Fully deterministic given same inputs.
    """

    # =========================================================================
    # Layer 1 — Personality → PAD Baseline
    # =========================================================================

    @staticmethod
    def compute_pad_baseline(
        traits: PersonalityTraits,
        pad_override: PADOverride | None = None,
    ) -> PADVector:
        """Compute PAD mood baseline from Big Five traits.

        Uses Mehrabian (1996) linear mapping with optional manual overrides
        for caricature personalities where linear mapping produces unrealistic results.

        When override values are present, they dominate (70% override, 30% computed)
        to allow fine-tuning while keeping some trait influence.

        Args:
            traits: Big Five personality traits.
            pad_override: Optional manual PAD overrides (nullable per dimension).

        Returns:
            PAD vector representing the personality's emotional baseline.
        """
        # Mehrabian linear mapping (approximate coefficients)
        o, c, e, a, n = (
            traits.openness,
            traits.conscientiousness,
            traits.extraversion,
            traits.agreeableness,
            traits.neuroticism,
        )
        n_inv = 1.0 - n

        p_computed = 0.21 * e + 0.59 * a + 0.19 * n_inv - 0.33
        a_computed = 0.15 * o + 0.30 * n - 0.57 * (1.0 - c) + 0.12
        d_computed = 0.25 * o + 0.17 * e + 0.60 * c - 0.32 * a - 0.10

        # Apply overrides with blending (70% override, 30% computed)
        p_final = p_computed
        a_final = a_computed
        d_final = d_computed

        if pad_override:
            if pad_override.pleasure is not None:
                p_final = 0.7 * pad_override.pleasure + 0.3 * p_computed
            if pad_override.arousal is not None:
                a_final = 0.7 * pad_override.arousal + 0.3 * a_computed
            if pad_override.dominance is not None:
                d_final = 0.7 * pad_override.dominance + 0.3 * d_computed

        return PADVector(
            pleasure=_clamp(p_final, -1.0, 1.0),
            arousal=_clamp(a_final, -1.0, 1.0),
            dominance=_clamp(d_final, -1.0, 1.0),
        )

    # =========================================================================
    # Layer 2 — Mood Dynamics
    # =========================================================================

    @staticmethod
    def apply_temporal_decay(
        mood_p: float,
        mood_a: float,
        mood_d: float,
        baseline: PADVector,
        hours_elapsed: float,
        decay_rate: float,
        emotions: list[dict],
        emotion_decay_rate: float,
        warmth: float,
        warmth_decay_rate: float,
        has_interaction: bool,
        traits: PersonalityTraits | None = None,
    ) -> tuple[float, float, float, list[dict], float]:
        """Apply temporal decay to mood, emotions, and warmth.

        Mood decays exponentially toward personality baseline.
        Emotions decay exponentially and are removed below threshold.
        Warmth decays toward 0.5 when no interaction.

        Conscientiousness modulates recovery speed (higher C = faster return
        to baseline). At C=0.5, recovery_factor=1.0 (backwards-compatible).

        Args:
            mood_p, mood_a, mood_d: Current PAD values.
            baseline: Personality PAD baseline to decay toward.
            hours_elapsed: Hours since last state update.
            decay_rate: Mood decay rate per hour.
            emotions: List of emotion dicts [{name, intensity, triggered_at}].
            emotion_decay_rate: Emotion intensity decay rate per hour.
            warmth: Current relationship warmth [0, 1].
            warmth_decay_rate: Warmth decay per hour of absence.
            has_interaction: Whether this call includes an interaction.
            traits: Big Five personality traits for modulation (None = defaults).

        Returns:
            Tuple of (new_mood_p, new_mood_a, new_mood_d, surviving_emotions, new_warmth).
        """
        if hours_elapsed <= 0:
            return mood_p, mood_a, mood_d, emotions, warmth

        # Conscientiousness modulates recovery speed
        # C=0.5 → factor=1.0 (backwards-compatible), C=0.9 → 1.24, C=0.1 → 0.76
        t = traits or PersonalityTraits()
        recovery_factor = 0.7 + t.conscientiousness * 0.6
        effective_decay = decay_rate * recovery_factor

        # Mood decay toward baseline
        decay_factor = math.exp(-effective_decay * hours_elapsed)
        new_p = baseline.pleasure + (mood_p - baseline.pleasure) * decay_factor
        new_a = baseline.arousal + (mood_a - baseline.arousal) * decay_factor
        new_d = baseline.dominance + (mood_d - baseline.dominance) * decay_factor

        # Emotion decay
        emotion_decay = math.exp(-emotion_decay_rate * hours_elapsed)
        surviving: list[dict] = []
        for emo in emotions:
            new_intensity = emo.get("intensity", 0.0) * emotion_decay
            if new_intensity >= EMOTION_MIN_INTENSITY:
                surviving.append(
                    {
                        "name": emo["name"],
                        "intensity": round(new_intensity, 4),
                        "triggered_at": emo.get("triggered_at", ""),
                    }
                )

        # Warmth decay (toward 0.5 neutral) when no interaction
        if not has_interaction:
            warmth_decay = math.exp(-warmth_decay_rate * hours_elapsed)
            new_warmth = 0.5 + (warmth - 0.5) * warmth_decay
        else:
            new_warmth = warmth

        return (
            _clamp(new_p, -1.0, 1.0),
            _clamp(new_a, -1.0, 1.0),
            _clamp(new_d, -1.0, 1.0),
            surviving,
            _clamp(new_warmth, 0.0, 1.0),
        )

    @staticmethod
    def apply_circadian(mood_p: float, local_hour: float, amplitude: float) -> float:
        """Apply circadian modulation to pleasure baseline.

        Sinusoidal modulation: peak at ~12h (midday), trough at ~0h (midnight).
        Only affects pleasure (people are generally happier midday).

        Args:
            mood_p: Current pleasure value.
            local_hour: Local time hour [0, 24).
            amplitude: Modulation amplitude (typically 0.05-0.1).

        Returns:
            Modified pleasure value.
        """
        delta = amplitude * math.sin(2 * math.pi * (local_hour - 6.0) / 24.0)
        return _clamp(mood_p + delta, -1.0, 1.0)

    @staticmethod
    def compute_emotional_inertia(
        mood_quadrant_since: datetime | None,
        now: datetime,
        base_inertia: float = 1.0,
    ) -> float:
        """Compute emotional inertia based on time in current mood quadrant.

        Longer in the same quadrant → more resistant to change.
        Inertia increases logarithmically.

        Args:
            mood_quadrant_since: When mood entered current quadrant.
            now: Current timestamp.
            base_inertia: Base inertia value.

        Returns:
            Inertia multiplier (>= 1.0).
        """
        if mood_quadrant_since is None:
            return base_inertia

        hours_in_quadrant = max(0.0, (now - mood_quadrant_since).total_seconds() / 3600.0)
        return base_inertia * (1.0 + 0.2 * math.log1p(hours_in_quadrant))

    # =========================================================================
    # Layer 3 — Emotion Appraisal
    # =========================================================================

    @staticmethod
    def apply_appraisal(
        mood_p: float,
        mood_a: float,
        mood_d: float,
        emotions: list[dict],
        appraisal: PsycheAppraisal,
        sensitivity: float,
        inertia: float,
        max_active: int,
        now_iso: str,
        traits: PersonalityTraits | None = None,
    ) -> tuple[float, float, float, list[dict]]:
        """Apply appraisal to generate emotion and push mood.

        Creates or reinforces an emotion from the appraisal, then pushes
        the mood in PAD space proportionally to the emotion's PAD vector.

        Big Five trait modulation (at traits=0.5, all factors = current behavior):
        - Neuroticism → emotional reactivity (0.6x at N=0.1, 1.4x at N=0.9)
        - Agreeableness → contagion strength (0.08 at A=0.1, 0.32 at A=0.9)
        - Agreeableness → counter-regulation toward neutral for low-A personalities

        Args:
            mood_p, mood_a, mood_d: Current PAD values.
            emotions: Current active emotions.
            appraisal: Parsed self-report from LLM.
            sensitivity: Sensitivity multiplier [0.1, 1.0].
            inertia: Emotional inertia (divides push force).
            max_active: Maximum simultaneous emotions.
            now_iso: Current ISO timestamp for new emotions.
            traits: Big Five personality traits for modulation (None = defaults).

        Returns:
            Tuple of (new_mood_p, new_mood_a, new_mood_d, updated_emotions).
        """
        t = traits or PersonalityTraits()

        # Deep copy to avoid mutating caller's JSONB-backed dicts
        new_emotions = [dict(e) for e in emotions]

        # Neuroticism modulates emotional reactivity
        # N=0.5 → 1.0 (backwards-compatible), N=0.9 → 1.4, N=0.1 → 0.6
        reactivity = 0.5 + t.neuroticism

        # v2: process up to 3 emotions with decreasing weight
        multi_weights = [1.0, 0.5, 0.25]
        for idx, (emo_name, raw_intensity) in enumerate(appraisal.emotions[:3]):
            if emo_name not in EMOTION_PAD_VECTORS:
                continue
            weight = multi_weights[idx] if idx < len(multi_weights) else 0.25
            effective_intensity = _clamp(raw_intensity * sensitivity * reactivity, 0.0, 1.0)

            # Blend or create emotion (60% old + 40% new)
            found = False
            for emo in new_emotions:
                if emo["name"] == emo_name:
                    emo["intensity"] = _clamp(
                        0.6 * emo["intensity"] + 0.4 * effective_intensity, 0.0, 1.0
                    )
                    emo["triggered_at"] = now_iso
                    found = True
                    break
            if not found:
                new_emotions.append(
                    {
                        "name": emo_name,
                        "intensity": effective_intensity,
                        "triggered_at": now_iso,
                    }
                )

            # Push mood via emotion PAD vector (weighted, with headroom)
            pad_vec = EMOTION_PAD_VECTORS[emo_name]
            push_coeff = 0.6 * effective_intensity * weight / max(inertia, 0.5)
            mood_p = _push_with_headroom(mood_p, pad_vec[0] * push_coeff)
            mood_a = _push_with_headroom(mood_a, pad_vec[1] * push_coeff)
            mood_d = _push_with_headroom(mood_d, pad_vec[2] * push_coeff)

        # Emotional contagion from user valence
        # Agreeableness modulates contagion strength:
        # A=0.5 → base=0.20 (backwards-compatible), A=0.1 → 0.08, A=0.9 → 0.32
        contagion_base = 0.05 + t.agreeableness * 0.30
        gap = appraisal.valence - mood_p
        contagion_strength = contagion_base * sensitivity * (1.0 + abs(gap))
        contagion_delta = _clamp(gap * contagion_strength, -0.40, 0.40)
        mood_p = _clamp(mood_p + contagion_delta, -1.0, 1.0)

        # Counter-regulation for low-agreeableness personalities
        counter_strength = max(0.0, (0.5 - t.agreeableness) * 0.25)
        if counter_strength > 0 and mood_p < 0:
            pull = counter_strength * sensitivity * abs(mood_p)
            mood_p = min(mood_p + pull, 0.0)

        # v2: cross-valence suppression accumulated across all reported emotions
        total_pos_suppression = 0.0
        total_neg_suppression = 0.0
        for idx, (emo_name, raw_intensity) in enumerate(appraisal.emotions[:3]):
            if emo_name not in EMOTION_PAD_VECTORS:
                continue
            weight = multi_weights[idx] if idx < len(multi_weights) else 0.25
            eff = _clamp(raw_intensity * sensitivity * reactivity, 0.0, 1.0)
            if emo_name in POSITIVE_EMOTIONS:
                total_pos_suppression += 0.30 * eff * weight
            elif emo_name in NEGATIVE_EMOTIONS:
                total_neg_suppression += 0.30 * eff * weight

        if total_pos_suppression > 0 or total_neg_suppression > 0:
            for emo in new_emotions:
                if emo["name"] in NEGATIVE_EMOTIONS and total_pos_suppression > 0:
                    emo["intensity"] = _clamp(emo["intensity"] - total_pos_suppression, 0.0, 1.0)
                elif emo["name"] in POSITIVE_EMOTIONS and total_neg_suppression > 0:
                    emo["intensity"] = _clamp(emo["intensity"] - total_neg_suppression, 0.0, 1.0)
            new_emotions = [
                e for e in new_emotions if e.get("intensity", 0) >= EMOTION_MIN_INTENSITY
            ]

        # Cap active emotions — evict weakest
        if len(new_emotions) > max_active:
            new_emotions.sort(key=lambda e: e.get("intensity", 0), reverse=True)
            new_emotions = new_emotions[:max_active]

        return mood_p, mood_a, mood_d, new_emotions

    # =========================================================================
    # Layer 4 — Relationship
    # =========================================================================

    @staticmethod
    def update_relationship(
        depth: float,
        warmth: float,
        trust: float,
        interaction_count: int,
        stage: str,
        quality: float,
        gap_hours: float,
        now_iso: str | None = None,
    ) -> tuple[float, float, float, int, str, list[dict]]:
        """Update relationship metrics and check stage transitions.

        Depth grows logarithmically (never regresses).
        Warmth blends with interaction quality.
        Trust updates via Bayesian-style accumulation.
        Stage transitions are based on depth thresholds (one-way).

        Args:
            depth, warmth, trust: Current relationship metrics.
            interaction_count: Total interactions so far.
            stage: Current stage name.
            quality: Interaction quality from appraisal [0, 1].
            gap_hours: Hours since last interaction.
            now_iso: Optional ISO 8601 timestamp for reunion emotions.
                Defaults to current UTC time if None (for testability).

        Returns:
            Tuple of (depth, warmth, trust, count, stage, reunion_emotions).
        """
        new_count = interaction_count + 1
        reunion_emotions: list[dict] = []
        if now_iso is None:
            now_iso = datetime.now(UTC).isoformat()

        # Adaptive learning rate — first interactions are more impactful
        lr = 1.0 / (1.0 + 0.1 * math.sqrt(new_count))

        # Depth: logarithmic growth, proportional to quality
        depth_increment = 0.02 * lr * quality * (1.0 - depth)
        new_depth = _clamp(depth + depth_increment, 0.0, 1.0)

        # Warmth: blend toward quality (fast recovery after absence)
        warmth_blend = 0.15 * lr
        new_warmth = _clamp(warmth + warmth_blend * (quality - warmth), 0.0, 1.0)

        # Trust: slow Bayesian update
        trust_update = 0.01 * lr * (quality - 0.5)  # Centered on 0.5
        new_trust = _clamp(trust + trust_update, 0.0, 1.0)

        # Reunion emotions based on absence gap
        if gap_hours >= GAP_LONG_HOURS:
            reunion_emotions.append(
                {
                    "name": "joy",
                    "intensity": round(EMOTION_REUNION_JOY_BASE + 0.2, 4),
                    "triggered_at": now_iso,
                }
            )
            reunion_emotions.append(
                {
                    "name": "curiosity",
                    "intensity": 0.3,
                    "triggered_at": now_iso,
                }
            )
        elif gap_hours >= GAP_SIGNIFICANT_HOURS:
            reunion_emotions.append(
                {
                    "name": "joy",
                    "intensity": round(EMOTION_REUNION_JOY_BASE + 0.1, 4),
                    "triggered_at": now_iso,
                }
            )
            reunion_emotions.append(
                {
                    "name": "curiosity",
                    "intensity": 0.2,
                    "triggered_at": now_iso,
                }
            )
        elif gap_hours >= GAP_NOTABLE_HOURS:
            reunion_emotions.append(
                {
                    "name": "joy",
                    "intensity": round(EMOTION_REUNION_JOY_BASE, 4),
                    "triggered_at": now_iso,
                }
            )

        # Stage transition check (one-way, based on depth)
        new_stage = stage
        for stage_name in reversed(RELATIONSHIP_STAGES):
            threshold = RELATIONSHIP_DEPTH_THRESHOLDS[stage_name]
            if new_depth >= threshold:
                stage_idx = RELATIONSHIP_STAGES.index(stage_name)
                current_idx = RELATIONSHIP_STAGES.index(stage)
                if stage_idx > current_idx:
                    new_stage = stage_name
                break

        return new_depth, new_warmth, new_trust, new_count, new_stage, reunion_emotions

    @staticmethod
    def detect_rupture_repair(
        prev_emotion_name: str | None,
        curr_emotion_name: str | None,
    ) -> float:
        """Detect rupture-repair sequence and return trust bonus.

        A negative emotion followed by a positive emotion indicates
        a resolved conflict, which strengthens trust beyond normal.

        Args:
            prev_emotion_name: Previous dominant emotion name.
            curr_emotion_name: Current dominant emotion name.

        Returns:
            Trust bonus (0.0 if no repair, REPAIR_TRUST_BONUS if repair detected).
        """
        if (
            prev_emotion_name
            and curr_emotion_name
            and prev_emotion_name in NEGATIVE_EMOTIONS
            and curr_emotion_name in POSITIVE_EMOTIONS
        ):
            return REPAIR_TRUST_BONUS
        return 0.0

    # =========================================================================
    # Layer 5 — Self-Efficacy
    # =========================================================================

    @staticmethod
    def update_self_efficacy(
        efficacy: dict,
        domain: str,
        success: bool,
        prior_weight: float,
    ) -> dict:
        """Bayesian update of self-efficacy for a domain.

        Args:
            efficacy: Current self-efficacy dict {domain: {score, weight}}.
            domain: Domain to update.
            success: Whether the task was successful.
            prior_weight: Bayesian prior weight (caps weight growth).

        Returns:
            Updated self-efficacy dict (new copy).
        """
        new_efficacy = dict(efficacy)

        if domain not in new_efficacy:
            new_efficacy[domain] = {
                "score": SELF_EFFICACY_DEFAULT_SCORE,
                "weight": SELF_EFFICACY_DEFAULT_WEIGHT,
            }

        entry = new_efficacy[domain]
        old_score = entry["score"]
        old_weight = entry["weight"]
        outcome = 1.0 if success else 0.0

        new_score = (old_score * old_weight + outcome) / (old_weight + 1.0)
        new_weight = min(old_weight + 1.0, prior_weight * 2.0)

        new_efficacy[domain] = {
            "score": round(_clamp(new_score, 0.0, 1.0), 4),
            "weight": round(new_weight, 2),
        }
        return new_efficacy

    @staticmethod
    def initialize_self_efficacy() -> dict:
        """Create default self-efficacy dict for all domains.

        Returns:
            Dict mapping each domain to default score and weight.
        """
        return {
            domain: {
                "score": SELF_EFFICACY_DEFAULT_SCORE,
                "weight": SELF_EFFICACY_DEFAULT_WEIGHT,
            }
            for domain in SELF_EFFICACY_DOMAINS
        }

    # =========================================================================
    # Drives Update
    # =========================================================================

    @staticmethod
    def update_drives(
        curiosity: float,
        engagement: float,
        appraisal_arousal: float,
        appraisal_quality: float,
    ) -> tuple[float, float]:
        """Update curiosity and engagement drives from appraisal.

        Curiosity is pulled toward interaction arousal (novelty/energy).
        Engagement is pulled toward interaction quality (satisfaction/flow).
        Both use exponential moving average (20% new, 80% old) for smooth transitions.

        Args:
            curiosity: Current curiosity drive [0, 1].
            engagement: Current engagement drive [0, 1].
            appraisal_arousal: Arousal from self-report [0, 1].
            appraisal_quality: Quality from self-report [0, 1].

        Returns:
            Tuple of (new_curiosity, new_engagement).
        """
        new_curiosity = _clamp(0.80 * curiosity + 0.20 * appraisal_arousal, 0.0, 1.0)
        new_engagement = _clamp(0.80 * engagement + 0.20 * appraisal_quality, 0.0, 1.0)
        return round(new_curiosity, 3), round(new_engagement, 3)

    # =========================================================================
    # Memory Integration — Mood-Congruent Recall
    # =========================================================================

    @staticmethod
    def apply_mood_congruent_boost(
        memory_score: float,
        memory_emotional_weight: float,
        mood_pleasure: float,
    ) -> float:
        """Apply mood-congruent recall boost to memory relevance score.

        When mood and memory valence are the same sign (both positive or both
        negative), the memory gets a small boost in retrieval scoring.

        Args:
            memory_score: Original semantic similarity score.
            memory_emotional_weight: Memory's emotional_weight [-10, +10].
            mood_pleasure: Current mood pleasure [-1, +1].

        Returns:
            Boosted score (never decreases original score).
        """
        memory_valence = memory_emotional_weight / 10.0
        congruence = mood_pleasure * memory_valence
        boost = 0.1 * max(0.0, congruence)
        return memory_score + boost

    # =========================================================================
    # Mood Classification
    # =========================================================================

    @staticmethod
    def classify_mood(mood_p: float, mood_a: float, mood_d: float) -> str:
        """Classify PAD vector into nearest mood label via centroid distance.

        Args:
            mood_p: Pleasure axis [-1, +1].
            mood_a: Arousal axis [-1, +1].
            mood_d: Dominance axis [-1, +1].

        Returns:
            Mood label string (e.g., 'serene', 'curious', 'neutral').
        """
        best_label = "neutral"
        best_dist = float("inf")
        for label, (cp, ca, cd) in MOOD_LABEL_CENTROIDS.items():
            dist = math.sqrt((mood_p - cp) ** 2 + (mood_a - ca) ** 2 + (mood_d - cd) ** 2)
            if dist < best_dist:
                best_dist = dist
                best_label = label
        return best_label

    # =========================================================================
    # Expression Profile Compilation
    # =========================================================================

    @staticmethod
    def compile_expression_profile(
        mood_p: float,
        mood_a: float,
        mood_d: float,
        emotions: list[dict],
        stage: str,
        warmth: float,
        drive_curiosity: float,
        drive_engagement: float,
        top_n: int = 2,
        self_efficacy: dict | None = None,
        traits: PersonalityTraits | None = None,
    ) -> ExpressionProfile:
        """Compile all psyche layers into an expression profile.

        Maps PAD to mood label (nearest centroid), determines intensity,
        selects top emotions, and derives warmth label.

        Args:
            mood_p, mood_a, mood_d: Current PAD values.
            emotions: Active emotions list.
            stage: Relationship stage.
            warmth: Active warmth [0, 1].
            drive_curiosity: Curiosity drive [0, 1].
            drive_engagement: Engagement drive [0, 1].
            top_n: Number of top emotions to include (default 2, rich format uses 3).
            self_efficacy: Domain-level confidence scores.
            traits: Big Five personality traits (for stability/anchor modulation).

        Returns:
            Compiled ExpressionProfile ready for prompt injection.
        """
        # Mood label: nearest centroid in PAD space
        best_label = PsycheEngine.classify_mood(mood_p, mood_a, mood_d)

        # Mood intensity from PAD magnitude
        magnitude = math.sqrt(mood_p**2 + mood_a**2 + mood_d**2)
        intensity_label = "slightly"
        for threshold, label in MOOD_INTENSITY_LABELS:
            if magnitude <= threshold:
                intensity_label = label
                break

        # Top N emotions by intensity
        sorted_emotions = sorted(emotions, key=lambda e: e.get("intensity", 0), reverse=True)
        top_emotions = [
            (e["name"], round(e["intensity"], 2))
            for e in sorted_emotions[:top_n]
            if e.get("intensity", 0) >= EMOTION_MIN_INTENSITY
        ]

        # Warmth label
        warmth_label = "neutral"
        for threshold, label in WARMTH_LABELS:
            if warmth <= threshold:
                warmth_label = label
                break

        # Self-efficacy: extract strengths (>0.65) and weaknesses (<0.35)
        strengths: list[str] = []
        weaknesses: list[str] = []
        if self_efficacy:
            for domain, entry in self_efficacy.items():
                score = entry.get("score", 0.5) if isinstance(entry, dict) else 0.5
                if score > 0.65:
                    strengths.append(domain)
                elif score < 0.35:
                    weaknesses.append(domain)

        profile = ExpressionProfile(
            mood_label=best_label,
            mood_intensity=intensity_label,
            active_emotions=top_emotions,
            relationship_stage=stage,
            warmth_label=warmth_label,
            drive_curiosity=round(drive_curiosity, 2),
            drive_engagement=round(drive_engagement, 2),
            confidence_strengths=strengths,
            confidence_weaknesses=weaknesses,
        )
        # v2: populate fields for graduated directives, stability, transitions
        profile.pad_magnitude = magnitude
        profile.current_pad = (mood_p, mood_a, mood_d)
        if traits:
            profile.neuroticism = traits.neuroticism
            profile.conscientiousness = traits.conscientiousness
        return profile

    # =========================================================================
    # Prompt Injection
    # =========================================================================

    @staticmethod
    def format_prompt_injection(profile: ExpressionProfile) -> str:
        """Format ExpressionProfile as compact XML tag for prompt injection.

        Produces a self-closing XML tag (~25-35 tokens) that the LLM
        interprets as behavioral directives.

        Args:
            profile: Compiled expression profile.

        Returns:
            Compact XML string for system prompt injection.
        """
        emotions_str = ""
        if profile.active_emotions:
            emotions_str = ",".join(
                f"{name}:{intensity}" for name, intensity in profile.active_emotions
            )

        return (
            f'<Psyche mood="{profile.mood_label}" '
            f'intensity="{profile.mood_intensity}" '
            f'emotions="{emotions_str}" '
            f'rel="{profile.relationship_stage}" '
            f'warmth="{profile.warmth_label}" '
            f'curiosity="{profile.drive_curiosity}" '
            f'engagement="{profile.drive_engagement}"/>'
        )

    @staticmethod
    def format_rich_prompt_injection(profile: ExpressionProfile) -> str:
        """Format ExpressionProfile as detailed behavioral directives for LLM.

        Produces a structured block (~100-120 tokens) with mood description,
        emotion directives, relationship stage guidance, and drive levels.
        Used for the main response prompt (Pattern A).

        Args:
            profile: Compiled expression profile (use top_n=3 for richer output).

        Returns:
            Rich directive block for system prompt injection.
        """
        # Mood directive
        mood_directive = MOOD_BEHAVIORAL_DIRECTIVES.get(
            profile.mood_label, "Balanced professional tone."
        )

        # Emotion directives
        emotion_lines: list[str] = []
        for name, intensity in profile.active_emotions:
            directive = EMOTION_BEHAVIORAL_DIRECTIVES.get(name, "")
            pct = round(intensity * 100)
            if directive:
                emotion_lines.append(f"- {name} ({pct}%): {directive}")
            else:
                emotion_lines.append(f"- {name} ({pct}%)")
        emotions_block = "\n".join(emotion_lines) if emotion_lines else "- none"

        # Relationship directive
        stage_directive = RELATIONSHIP_STAGE_DIRECTIVES.get(
            profile.relationship_stage,
            "Be polite and professional.",
        )

        # Evolution awareness: tell the LLM how mood/emotion shifted
        evolution_block = ""
        if profile.previous_mood and profile.previous_mood != profile.mood_label:
            evolution_block += (
                f"EVOLUTION: mood shifted from {profile.previous_mood} "
                f"to {profile.mood_label}.\n"
            )
        if profile.previous_emotion:
            current_top = profile.active_emotions[0][0] if profile.active_emotions else None
            if current_top and current_top != profile.previous_emotion:
                evolution_block += (
                    f"Previous dominant emotion was {profile.previous_emotion}, "
                    f"now {current_top}.\n"
                )
        if evolution_block:
            evolution_block = "\n" + evolution_block

        return (
            f"<PsycheDirectives>\n"
            f"MOOD: {profile.mood_label} ({profile.mood_intensity})\n"
            f"{mood_directive}\n\n"
            f"EMOTIONS:\n"
            f"{emotions_block}\n\n"
            f"RELATIONSHIP: {profile.relationship_stage}\n"
            f"{stage_directive}\n\n"
            f"DRIVES:\n"
            f"- curiosity={profile.drive_curiosity}"
            f"{' — explore new angles, ask questions' if profile.drive_curiosity > 0.6 else ''}\n"
            f"- engagement={profile.drive_engagement}"
            f"{' — in flow, be thorough and proactive' if profile.drive_engagement > 0.6 else ''}\n"
            f"{_format_confidence_block(profile)}"
            f"{evolution_block}"
            f"</PsycheDirectives>"
        )

    # =========================================================================
    # v2: Transition Detection
    # =========================================================================

    @staticmethod
    def detect_transition_type(profile: ExpressionProfile) -> str | None:
        """Detect the type of emotional transition from last interaction.

        Checks profile.previous_pad, profile.current_pad, profile.gap_hours,
        profile.previous_mood, and profile.previous_emotion to determine if a
        significant emotional transition occurred.

        Returns:
            Transition type key for TRANSITION_NARRATIVE_TEMPLATES, or None.
            Priority: reunion > valence shift > arousal shift > emotion change.
        """
        # 1. Reunion: long gap since last interaction
        if profile.gap_hours >= GAP_NOTABLE_HOURS:
            return "reunion"

        # Need previous PAD for valence/arousal transitions
        if profile.previous_pad is not None and profile.current_pad is not None:
            prev_p, prev_a, _prev_d = profile.previous_pad
            _curr_p, curr_a, _curr_d = profile.current_pad

            # 2. Valence shift: positive mood → negative mood (or vice versa)
            if prev_p >= 0.10 and profile.mood_label in NEGATIVE_MOOD_LABELS:
                return "pos_to_neg"
            if prev_p <= -0.05 and profile.mood_label in POSITIVE_MOOD_LABELS:
                return "neg_to_pos"

            # 3. Arousal shift: significant arousal delta (≥ 0.30)
            if prev_a >= 0.20 and curr_a <= -0.10:
                return "high_to_low_arousal"
            if prev_a <= -0.10 and curr_a >= 0.20:
                return "low_to_high_arousal"

        # 4. Emotion-specific: dominant emotion changed
        if profile.previous_emotion:
            current_top = profile.active_emotions[0][0] if profile.active_emotions else None
            if current_top and current_top != profile.previous_emotion:
                return "emotion_specific"

        return None

    # =========================================================================
    # v2: Graduated Prompt Injection
    # =========================================================================

    @staticmethod
    def format_graduated_prompt_injection(
        profile: ExpressionProfile,
    ) -> tuple[str, str]:
        """Format directives with verbosity proportional to emotional intensity.

        Produces four levels of output based on PAD magnitude:
        - Level 1 (slightly, <0.15): Compact XML tag + one-liner
        - Level 2 (moderately, 0.15-0.35): Mood directive + emotion names + relation
        - Level 3 (noticeably, 0.35-0.60): Full rich format with all sections
        - Level 4 (strongly, ≥0.60): Rich format + emphasis reinforcement

        Args:
            profile: Compiled expression profile.

        Returns:
            Tuple of (directives_block, usage_directive_prompt_name).
        """
        stability = _build_stability_blocks(profile)
        magnitude = profile.pad_magnitude

        # Level 1: compact (< 0.15)
        if magnitude < 0.15:
            compact = PsycheEngine.format_prompt_injection(profile)
            block = compact
            if stability:
                block += "\n" + stability
            block += "\nLet this mood subtly color your tone."
            return (block, "psyche_usage_directive_light")

        # Level 2: medium (0.15 - 0.35)
        if magnitude < 0.35:
            mood_dir = MOOD_BEHAVIORAL_DIRECTIVES.get(
                profile.mood_label, "Balanced professional tone."
            )
            emotion_names = (
                ", ".join(name for name, _intensity in profile.active_emotions) or "none"
            )
            stage_dir = RELATIONSHIP_STAGE_DIRECTIVES.get(
                profile.relationship_stage, "Be polite and professional."
            )
            parts = ["<PsycheDirectives>"]
            if stability:
                parts.append(stability.rstrip())
            parts.append(f"MOOD: {profile.mood_label} ({profile.mood_intensity})" f" — {mood_dir}")
            parts.append(f"EMOTIONS: {emotion_names}")
            parts.append(f"RELATIONSHIP: {profile.relationship_stage} — {stage_dir}")
            parts.append("</PsycheDirectives>")
            return ("\n".join(parts), "psyche_usage_directive_light")

        # Level 3 & 4: rich format
        # Reuse existing rich formatter as base, then augment
        mood_directive = MOOD_BEHAVIORAL_DIRECTIVES.get(
            profile.mood_label, "Balanced professional tone."
        )
        emotion_lines: list[str] = []
        for name, intensity in profile.active_emotions:
            directive = EMOTION_BEHAVIORAL_DIRECTIVES.get(name, "")
            pct = round(intensity * 100)
            if directive:
                emotion_lines.append(f"- {name} ({pct}%): {directive}")
            else:
                emotion_lines.append(f"- {name} ({pct}%)")
        emotions_block = "\n".join(emotion_lines) if emotion_lines else "- none"

        stage_directive = RELATIONSHIP_STAGE_DIRECTIVES.get(
            profile.relationship_stage, "Be polite and professional."
        )

        # Narrative transition (replaces mechanical EVOLUTION)
        transition_type = PsycheEngine.detect_transition_type(profile)
        evolution_block = ""
        if transition_type:
            template = TRANSITION_NARRATIVE_TEMPLATES.get(transition_type, "")
            if transition_type == "emotion_specific":
                curr_top = profile.active_emotions[0][0] if profile.active_emotions else "calm"
                template = template.format(
                    prev_emotion=profile.previous_emotion or "the previous state",
                    curr_emotion=curr_top,
                )
            evolution_block = "\n" + template + "\n"

        # Level 4 emphasis
        emphasis = ""
        if magnitude >= 0.60:
            emphasis = (
                f"\nEMPHASIS: Your {profile.mood_label} mood is INTENSE."
                " Let it permeate every sentence.\n"
            )

        block = (
            f"<PsycheDirectives>\n"
            f"{stability}"
            f"MOOD: {profile.mood_label} ({profile.mood_intensity})\n"
            f"{mood_directive}\n\n"
            f"EMOTIONS:\n"
            f"{emotions_block}\n\n"
            f"RELATIONSHIP: {profile.relationship_stage}\n"
            f"{stage_directive}\n\n"
            f"DRIVES:\n"
            f"- curiosity={profile.drive_curiosity}"
            f"{' — explore new angles, ask questions' if profile.drive_curiosity > 0.6 else ''}\n"
            f"- engagement={profile.drive_engagement}"
            f"{' — in flow, be thorough and proactive' if profile.drive_engagement > 0.6 else ''}\n"
            f"{_format_confidence_block(profile)}"
            f"{evolution_block}"
            f"{emphasis}"
            f"</PsycheDirectives>"
        )
        return (block, "psyche_usage_directive")

    # =========================================================================
    # v2: Computed Emotional Resonance
    # =========================================================================

    # Emotions where responding to a negative user is appropriate (not dissonant)
    _APPROPRIATE_NEGATIVE_RESPONSES: frozenset[str] = frozenset(
        {
            "concern",
            "empathy",
            "protectiveness",
            "determination",
            "resolve",
        }
    )

    @staticmethod
    def compute_resonance(
        user_valence: float,
        emotions: list[tuple[str, float]],
    ) -> float:
        """Compute emotional resonance between user state and assistant response.

        Resonance measures alignment: positive when appropriate (empathy with sadness,
        shared joy), negative when misaligned (cheerful with grieving user).

        Args:
            user_valence: User's emotional valence from appraisal [-1, +1].
            emotions: Assistant's reported emotions [(name, intensity), ...].

        Returns:
            Resonance value in [-1.0, +1.0].
        """
        if not emotions:
            return 0.0

        dominant_name, dominant_intensity = emotions[0]
        if dominant_name not in EMOTION_PAD_VECTORS:
            return 0.0

        emotion_pleasure = EMOTION_PAD_VECTORS[dominant_name][0]

        # Neutral zone: no significant resonance signal
        if abs(user_valence) < 0.15 or abs(emotion_pleasure) < 0.10:
            return 0.0

        # Special case: empathic/protective responses to negative user are appropriate
        if user_valence < -0.15 and dominant_name in PsycheEngine._APPROPRIATE_NEGATIVE_RESPONSES:
            return _clamp(min(abs(user_valence), dominant_intensity) * 0.7, 0.0, 1.0)

        # Same sign = resonance, opposite = dissonance
        user_sign = 1.0 if user_valence > 0 else -1.0
        emo_sign = 1.0 if emotion_pleasure > 0 else -1.0
        correlation = user_sign * emo_sign

        return _clamp(correlation * min(abs(user_valence), dominant_intensity), -1.0, 1.0)

    # =========================================================================
    # v2: Proactive Emotions
    # =========================================================================

    @staticmethod
    def compute_proactive_emotions(
        drive_curiosity: float,
        drive_engagement: float,
        interaction_count: int,
        last_appraisal: dict | None,
        self_efficacy: dict | None,
        existing_emotions: list[dict],
        now_iso: str,
    ) -> list[dict]:
        """Compute anticipatory emotion pulses from contextual state.

        Injected in pre-response to prime the assistant's emotional state
        based on drives, relationship history, and confidence.

        Args:
            drive_curiosity: Current curiosity drive [0, 1].
            drive_engagement: Current engagement drive [0, 1].
            interaction_count: Total non-trivial interactions with user.
            last_appraisal: Previous appraisal dict (for quality check).
            self_efficacy: Domain-level confidence scores.
            existing_emotions: Current active emotions (for anti-inflation guard).
            now_iso: Current ISO timestamp.

        Returns:
            List of proactive emotion dicts [{name, intensity, triggered_at}].
        """
        pulses: list[dict] = []

        # Helper: get existing intensity for an emotion name
        def _existing(name: str) -> float:
            for e in existing_emotions:
                if e.get("name") == name:
                    return float(e.get("intensity", 0.0))
            return 0.0

        # Curiosity pulse for new relationships
        if drive_curiosity > 0.7 and interaction_count < 5:
            pulses.append({"name": "curiosity", "intensity": 0.25, "triggered_at": now_iso})

        # Enthusiasm pulse for high engagement (with anti-inflation guard)
        if drive_engagement > 0.8 and _existing("enthusiasm") < 0.50:
            pulses.append({"name": "enthusiasm", "intensity": 0.20, "triggered_at": now_iso})

        # Joy pulse for sustained quality (with anti-inflation guard)
        if (
            last_appraisal
            and last_appraisal.get("quality", 0) > 0.7
            and drive_engagement > 0.7
            and _existing("joy") < 0.50
        ):
            pulses.append({"name": "joy", "intensity": 0.15, "triggered_at": now_iso})

        # Pride pulse for established high self-efficacy
        if self_efficacy:
            for _domain, entry in self_efficacy.items():
                if isinstance(entry, dict):
                    score = entry.get("score", 0.5)
                    weight = entry.get("weight", 2.0)
                    if score > 0.75 and weight > 4.0:
                        pulses.append({"name": "pride", "intensity": 0.15, "triggered_at": now_iso})
                        break  # Only one pride pulse

        return pulses

    @staticmethod
    def merge_proactive_emotions(
        existing_emotions: list[dict],
        proactive: list[dict],
    ) -> list[dict]:
        """Merge proactive pulses into existing emotions (additive, capped at 1.0).

        Args:
            existing_emotions: Current active emotions from state.
            proactive: Proactive pulses to merge.

        Returns:
            Merged emotion list (deep copy, originals not mutated).
        """
        result = [dict(e) for e in existing_emotions]
        existing_names = {e["name"]: i for i, e in enumerate(result)}

        for pulse in proactive:
            name = pulse["name"]
            if name in existing_names:
                idx = existing_names[name]
                result[idx]["intensity"] = min(1.0, result[idx]["intensity"] + pulse["intensity"])
                result[idx]["triggered_at"] = pulse["triggered_at"]
            else:
                result.append(dict(pulse))

        return result

    # =========================================================================
    # Self-Report Tag Parsing
    # =========================================================================

    @staticmethod
    def parse_psyche_eval(content: str) -> tuple[PsycheAppraisal | None, str]:
        """Parse <psyche_eval .../> tag from LLM response and strip it.

        Uses the same pattern as parse_relevant_ids_from_response():
        regex match → extract → re.sub to clean.

        Args:
            content: Raw LLM response content.

        Returns:
            Tuple of (parsed appraisal or None, cleaned content without tag).
        """
        if not content:
            return None, content

        match = PSYCHE_EVAL_TAG_PATTERN.search(content)
        if not match:
            return None, content

        # Parse attributes
        attrs_str = match.group(1)
        attrs: dict[str, str] = {}
        for attr_match in PSYCHE_EVAL_ATTR_PATTERN.finditer(attrs_str):
            attrs[attr_match.group(1).lower()] = attr_match.group(2)

        if not attrs:
            # Tag found but no parseable attributes
            cleaned = PSYCHE_EVAL_TAG_PATTERN.sub("", content).strip()
            return None, cleaned

        # Parse emotions: v2 multi-emotion format takes priority
        emotions_list: list[tuple[str, float]] = []
        if "emotions" in attrs:
            for part in attrs["emotions"].split(","):
                chunks = part.strip().split(":")
                if len(chunks) == 2:
                    name = _validate_emotion(chunks[0].strip())
                    intens = _clamp(_safe_float(chunks[1].strip(), 0.5), 0.0, 1.0)
                    if name:
                        emotions_list.append((name, intens))
            emotions_list = emotions_list[:3]

        # Fallback: v1 single-emotion format
        legacy_emotion = _validate_emotion(attrs.get("emotion"))
        legacy_intensity = _clamp(_safe_float(attrs.get("intensity", "0.5")), 0.0, 1.0)

        # Build appraisal with clamped values
        appraisal = PsycheAppraisal(
            valence=_clamp(_safe_float(attrs.get("valence", "0")), -1.0, 1.0),
            arousal=_clamp(_safe_float(attrs.get("arousal", "0.5")), 0.0, 1.0),
            dominance=_clamp(_safe_float(attrs.get("dominance", "0")), -1.0, 1.0),
            emotions=emotions_list,
            quality=_clamp(_safe_float(attrs.get("quality", "0.5")), 0.0, 1.0),
            # Legacy fields: only set if no multi-emotion parsed (triggers __post_init__)
            emotion=legacy_emotion if not emotions_list else None,
            intensity=legacy_intensity if not emotions_list else 0.5,
        )

        # Strip tag from content
        cleaned = PSYCHE_EVAL_TAG_PATTERN.sub("", content).strip()
        return appraisal, cleaned

    # =========================================================================
    # Mood Color for Frontend
    # =========================================================================

    @staticmethod
    def mood_to_color(mood_label: str) -> str:
        """Map mood label to hex color for frontend mood ring.

        Uses colorblind-safe palette (no pure red/green).

        Args:
            mood_label: Mood label from expression profile.

        Returns:
            Hex color string.
        """
        color_map = {
            "serene": "#38bdf8",  # sky-400
            "curious": "#a78bfa",  # violet-400
            "energized": "#fbbf24",  # amber-400
            "playful": "#f472b6",  # pink-400
            "reflective": "#2dd4bf",  # teal-400
            "agitated": "#f97316",  # orange-500
            "melancholic": "#818cf8",  # indigo-400
            "neutral": "#9ca3af",  # gray-400
            # Iteration 3 additions
            "content": "#34d399",  # emerald-400
            "determined": "#ef4444",  # red-500
            "defiant": "#f43f5e",  # rose-500
            "resigned": "#94a3b8",  # slate-400
            "overwhelmed": "#a855f7",  # purple-500
            "tender": "#ec4899",  # pink-500
        }
        return color_map.get(mood_label, "#9ca3af")


# =============================================================================
# Private Helpers
# =============================================================================


def _format_confidence_block(profile: ExpressionProfile) -> str:
    """Format self-efficacy strengths/weaknesses for rich injection."""
    if not profile.confidence_strengths and not profile.confidence_weaknesses:
        return ""
    lines = ["\nCONFIDENCE:"]
    if profile.confidence_strengths:
        lines.append(f"- Strong in: {', '.join(profile.confidence_strengths)}")
    if profile.confidence_weaknesses:
        lines.append(
            f"- Less confident in: {', '.join(profile.confidence_weaknesses)}"
            " — be more careful and thorough"
        )
    return "\n".join(lines) + "\n"


def _build_stability_blocks(profile: ExpressionProfile) -> str:
    """Build serenity floor and/or emotional anchor blocks.

    Serenity floor: when no emotion is significantly active, inject a baseline
    steadiness directive modulated by neuroticism.
    Anchor: when a strong negative emotion threatens a spiral, inject a grounding
    directive modulated by conscientiousness.

    These are mutually exclusive by construction: floor fires when no emotion
    is strong (< 0.15), anchor fires when a negative is very strong (> 0.70).

    Returns:
        Directive block string (may be empty).
    """
    # Check for significant emotions
    significant = [
        (name, intensity)
        for name, intensity in profile.active_emotions
        if intensity >= EMOTION_SIGNIFICANT_THRESHOLD
    ]

    # B1: Serenity floor — no significant emotion active
    if not significant:
        floor_strength = (1 - profile.neuroticism) * 0.7 + 0.3  # [0.3, 1.0]
        for threshold, directive in SERENITY_FLOOR_DIRECTIVES:
            if floor_strength < threshold:
                return directive + "\n"
        return ""

    # B2+B3: Anchor — strong negative emotion
    anchor_base = (1 - profile.neuroticism) * 0.7 + 0.3
    if anchor_base <= 0.30:
        # Extreme neuroticism (N≈1.0): personality IS the spiral, no anchor
        return ""

    for name, intensity in profile.active_emotions:
        if name in NEGATIVE_EMOTIONS and intensity > ANCHOR_NEGATIVE_INTENSITY_THRESHOLD:
            # Select anchor wording by conscientiousness
            anchor = ""
            for c_threshold, template in ANCHOR_DIRECTIVES_BY_CONSCIENTIOUSNESS:
                if profile.conscientiousness < c_threshold:
                    anchor = template.format(emotion=name)
                    break
            if anchor_base < 0.40:
                anchor += " ...though it may take a moment."
            return anchor + "\n"

    return ""


def _push_with_headroom(current: float, delta: float) -> float:
    """Apply a push with diminishing returns at boundaries.

    Models a spring-at-boundary: the closer the value is to ±1.0 in the
    push direction, the more the push is attenuated. Prevents saturation
    from repeated same-direction pushes.

    Args:
        current: Current value in [-1, +1].
        delta: Raw push amount (positive or negative).

    Returns:
        New value, clamped to [-1, +1].
    """
    if abs(delta) < 1e-10:
        return current
    # Headroom = distance to the boundary in the push direction
    headroom = (1.0 - current) if delta > 0 else (1.0 + current)
    attenuated = delta * _clamp(headroom, 0.0, 1.0)
    return _clamp(current + attenuated, -1.0, 1.0)


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a float value between min and max."""
    return max(min_val, min(max_val, value))


def _safe_float(s: str, default: float = 0.0) -> float:
    """Parse string to float with fallback."""
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _validate_emotion(name: str | None) -> str | None:
    """Validate emotion name against known types."""
    if name and name.lower() in EMOTION_PAD_VECTORS:
        return name.lower()
    return None
