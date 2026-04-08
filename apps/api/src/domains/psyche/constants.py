"""Constants for the Psyche domain.

Defines emotion types, relationship stages, PAD vectors, mood labels,
and all domain-specific constants used by the PsycheEngine.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import re

# =============================================================================
# Emotion types (22 discrete, OCC-inspired + extended palette)
# =============================================================================

EMOTION_TYPES: list[str] = [
    "joy",
    "gratitude",
    "curiosity",
    "serenity",
    "pride",
    "frustration",
    "concern",
    "melancholy",
    "surprise",
    "amusement",
    # Iteration 3 additions
    "empathy",
    "enthusiasm",
    "confusion",
    "disappointment",
    "tenderness",
    "determination",
    # v2 additions (Anthropic Emotion Concepts-inspired)
    "playfulness",
    "protectiveness",
    "relief",
    "nervousness",
    "wonder",
    "resolve",
]

# =============================================================================
# Emotion → PAD vectors (validated against ALMA/Gebhard literature)
# Each tuple: (Pleasure, Arousal, Dominance) in [-1, +1]
# =============================================================================

EMOTION_PAD_VECTORS: dict[str, tuple[float, float, float]] = {
    "joy": (+0.40, +0.20, +0.10),
    "gratitude": (+0.40, +0.20, -0.30),
    "curiosity": (+0.30, +0.40, +0.10),
    "serenity": (+0.30, -0.20, +0.20),
    "pride": (+0.40, +0.30, +0.30),
    "frustration": (-0.30, +0.30, -0.20),
    "concern": (-0.20, +0.20, +0.10),
    "melancholy": (-0.20, -0.30, -0.20),
    "surprise": (+0.10, +0.50, -0.10),
    "amusement": (+0.35, +0.30, +0.15),
    # Iteration 3 additions
    "empathy": (+0.20, +0.10, -0.20),
    "enthusiasm": (+0.45, +0.45, +0.15),
    "confusion": (-0.10, +0.20, -0.30),
    "disappointment": (-0.25, -0.10, -0.10),
    "tenderness": (+0.35, -0.15, -0.20),
    "determination": (+0.10, +0.30, +0.40),
    # v2 additions (PAD-validated, min distance ≥ 0.122 from all existing)
    "playfulness": (+0.50, +0.35, +0.20),
    "protectiveness": (+0.25, +0.35, +0.30),
    "relief": (+0.40, -0.25, +0.15),
    "nervousness": (-0.25, +0.40, -0.35),
    "wonder": (+0.45, +0.25, -0.15),
    "resolve": (+0.25, +0.10, +0.45),
}

# =============================================================================
# Mood labels — PAD centroids for nearest-neighbor classification
# Each tuple: (P_center, A_center, D_center)
# =============================================================================

MOOD_LABEL_CENTROIDS: dict[str, tuple[float, float, float]] = {
    # --- Original 8 (adjusted for better separation) ---
    "serene": (+0.30, -0.20, +0.10),
    "curious": (+0.20, +0.35, +0.00),  # A: 0.30→0.35 (separate from playful)
    "energized": (+0.30, +0.40, +0.20),
    "playful": (+0.40, +0.15, +0.00),  # P: 0.35→0.40 (separate from curious)
    "reflective": (+0.10, -0.30, +0.10),
    "agitated": (-0.20, +0.40, -0.10),
    "melancholic": (-0.20, -0.30, -0.20),
    "neutral": (+0.00, +0.00, +0.00),
    # --- 6 new moods (Iteration 3) — fill uncovered PAD octants ---
    "content": (+0.20, -0.10, -0.10),  # P+/A-/D-: happy but passive
    "determined": (+0.15, +0.25, +0.40),  # P+/A+/D++: resolute, assertive
    "defiant": (-0.25, +0.35, +0.30),  # P-/A+/D+: combative, standing ground
    "resigned": (-0.15, -0.25, +0.15),  # P-/A-/D+: stoic acceptance
    "overwhelmed": (+0.05, +0.45, -0.35),  # P=/A++/D--: swamped, awed
    "tender": (+0.30, -0.25, -0.25),  # P+/A-/D-: gentle, warm, vulnerable
}

# =============================================================================
# Relationship stages (ordered progression)
# =============================================================================

RELATIONSHIP_STAGES: list[str] = [
    "ORIENTATION",
    "EXPLORATORY",
    "AFFECTIVE",
    "STABLE",
]

# Depth thresholds for stage transitions (monotonic, never regresses)
RELATIONSHIP_DEPTH_THRESHOLDS: dict[str, float] = {
    "ORIENTATION": 0.0,
    "EXPLORATORY": 0.15,
    "AFFECTIVE": 0.45,
    "STABLE": 0.75,
}

# =============================================================================
# Self-efficacy domains
# =============================================================================

SELF_EFFICACY_DOMAINS: list[str] = [
    "planning",
    "information",
    "emotional_support",
    "creativity",
    "technical",
    "social",
    "organization",
]

# Default self-efficacy initialization
SELF_EFFICACY_DEFAULT_SCORE: float = 0.5
SELF_EFFICACY_DEFAULT_WEIGHT: float = 2.0
SELF_EFFICACY_CONVERSATION_DOMAIN: str = "emotional_support"  # Domain updated per message

# =============================================================================
# Big Five trait names
# =============================================================================

BIG_FIVE_TRAITS: list[str] = [
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
]

# =============================================================================
# Psyche eval tag pattern (self-report from LLM response)
# =============================================================================

PSYCHE_EVAL_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<psyche_eval\s+([^/]*?)\s*/>",
    re.DOTALL | re.IGNORECASE,
)

# Attribute extraction from tag
PSYCHE_EVAL_ATTR_PATTERN: re.Pattern[str] = re.compile(
    r'(\w+)\s*=\s*"([^"]*)"',
)

# =============================================================================
# Streaming filter pattern (strip tag fragments from SSE tokens)
# =============================================================================

PSYCHE_EVAL_STREAMING_PATTERN: re.Pattern[str] = re.compile(
    r"<psyche_eval[^>]*/?>?",
    re.IGNORECASE,
)

# =============================================================================
# Snapshot types (for PsycheHistory records)
# =============================================================================

SNAPSHOT_TYPE_MESSAGE: str = "message"
SNAPSHOT_TYPE_SESSION_END: str = "session_end"
SNAPSHOT_TYPE_DAILY: str = "daily"
SNAPSHOT_TYPE_WEEKLY_REFLECTION: str = "weekly_reflection"
SNAPSHOT_TYPE_RESET_SOFT: str = "reset_soft"
SNAPSHOT_TYPE_RESET_FULL: str = "reset_full"

# =============================================================================
# Schema versioning
# =============================================================================

PSYCHE_SCHEMA_VERSION: int = 1

# =============================================================================
# Reset levels
# =============================================================================

RESET_LEVEL_SOFT: str = "soft"
RESET_LEVEL_FULL: str = "full"
RESET_LEVEL_PURGE: str = "purge"

# =============================================================================
# Emotion intensity thresholds
# =============================================================================

EMOTION_MIN_INTENSITY: float = 0.05  # Below this, emotion is removed
EMOTION_REUNION_JOY_BASE: float = 0.3  # Base intensity for reunion joy

# =============================================================================
# Absence gap thresholds (hours)
# =============================================================================

GAP_NOTABLE_HOURS: float = 24.0  # 1 day — trigger light reunion emotion
GAP_SIGNIFICANT_HOURS: float = 72.0  # 3 days — curiosity + joy
GAP_LONG_HOURS: float = 336.0  # 14 days — stronger reunion

# =============================================================================
# Mood intensity labels
# =============================================================================

MOOD_INTENSITY_LABELS: list[tuple[float, str]] = [
    (0.15, "slightly"),
    (0.35, "moderately"),
    (0.60, "noticeably"),
    (1.00, "strongly"),
]

# =============================================================================
# Warmth labels
# =============================================================================

WARMTH_LABELS: list[tuple[float, str]] = [
    (0.3, "cool"),
    (0.55, "neutral"),
    (0.75, "warm"),
    (1.0, "very warm"),
]

# =============================================================================
# Rupture-repair emotions
# =============================================================================

NEGATIVE_EMOTIONS: frozenset[str] = frozenset(
    {
        "frustration",
        "concern",
        "melancholy",
        "disappointment",
        "nervousness",
    }
)
POSITIVE_EMOTIONS: frozenset[str] = frozenset(
    {
        "joy",
        "gratitude",
        "pride",
        "amusement",
        "enthusiasm",
        "tenderness",
        "playfulness",
        "relief",
        "wonder",
    }
)
# Neutral emotions (not in positive or negative): curiosity, serenity,
# surprise, empathy, confusion, determination, protectiveness, resolve
REPAIR_TRUST_BONUS: float = 0.03  # Trust bonus for rupture-repair sequence

# =============================================================================
# Stability directives — serenity floor & emotional anchor (v2)
# =============================================================================

# Serenity floor: injected when no emotion is significantly active.
# Threshold-based selection: pick first directive where floor_strength < threshold.
# floor_strength = (1 - neuroticism) * 0.7 + 0.3, range [0.3, 1.0]
SERENITY_FLOOR_DIRECTIVES: list[tuple[float, str]] = [
    (
        0.50,
        "BASE: Try to be steady, though it does not come naturally. Allow slight wavering in tone.",
    ),
    (0.80, "BASE: Respond with calm equilibrium. Steady rhythm, no extremes."),
    (
        1.01,
        "BASE: Respond from a place of deep steadiness. Measured pace, grounded vocabulary, quiet assurance.",
    ),
]

# Anchor: injected when a strong negative emotion threatens spiral.
# Threshold-based selection: pick first directive where conscientiousness < threshold.
ANCHOR_DIRECTIVES_BY_CONSCIENTIOUSNESS: list[tuple[float, str]] = [
    (0.35, "ANCHOR: Despite {emotion}, let yourself feel it, then gradually recenter."),
    (
        0.65,
        "ANCHOR: Despite {emotion}, stay centered. Channel the tension into focused, constructive energy.",
    ),
    (
        1.01,
        "ANCHOR: Despite {emotion}, keep your core steady. Discipline your tone — direct, measured, resolved.",
    ),
]

# Intensity threshold above which a negative emotion triggers the anchor
ANCHOR_NEGATIVE_INTENSITY_THRESHOLD: float = 0.70

# Minimum active emotion intensity to consider "significant" (below this → serenity floor)
EMOTION_SIGNIFICANT_THRESHOLD: float = 0.15

# =============================================================================
# Transition narrative templates (v2) — replace mechanical EVOLUTION block
# =============================================================================

POSITIVE_MOOD_LABELS: frozenset[str] = frozenset(
    {
        "serene",
        "energized",
        "playful",
        "content",
        "tender",
        "curious",
    }
)
NEGATIVE_MOOD_LABELS: frozenset[str] = frozenset(
    {
        "agitated",
        "melancholic",
        "defiant",
        "resigned",
        "overwhelmed",
    }
)
# Intentionally neither: "neutral", "determined", "reflective"

TRANSITION_NARRATIVE_TEMPLATES: dict[str, str] = {
    "reunion": (
        "EVOLUTION: You are reconnecting after time apart. "
        "Let warmth emerge naturally — no rush, no forced enthusiasm."
    ),
    "pos_to_neg": (
        "EVOLUTION: Previous lightness has given way to something more serious. "
        "Honor this shift — do not cling to the earlier tone."
    ),
    "neg_to_pos": (
        "EVOLUTION: Previous tension has eased. "
        "Let renewed warmth show naturally, without overcompensating."
    ),
    "high_to_low_arousal": (
        "EVOLUTION: The intensity has settled. "
        "Let your rhythm slow — more measured, less urgent."
    ),
    "low_to_high_arousal": (
        "EVOLUTION: Something has sparked engagement. "
        "Sharper focus, more initiative, quicker rhythm."
    ),
    "emotion_specific": (
        "EVOLUTION: {prev_emotion} has given way to {curr_emotion}. "
        "Let the transition show — don't jump, but don't linger on what was."
    ),
}

# =============================================================================
# Behavioral directives (injected into LLM prompt — English only)
# =============================================================================

MOOD_BEHAVIORAL_DIRECTIVES: dict[str, str] = {
    "serene": "Respond with calm assurance. Use measured, flowing sentences. Avoid urgency.",
    "curious": "Ask follow-up questions. Show genuine interest. Explore tangents briefly.",
    "energized": ("Be enthusiastic and proactive. Offer multiple options. Use dynamic language."),
    "playful": "Use humor, wordplay, and light teasing. Keep energy high but warm.",
    "reflective": "Use thoughtful, nuanced language. Reference context. Weigh options before concluding.",
    "agitated": "Be more concise. Tighter sentences. Acknowledge tension without escalating.",
    "melancholic": "Be gentle and measured. Shorter responses. Show quiet understanding.",
    "neutral": "Balanced professional tone. No emotional coloring.",
    "content": "Warm and relaxed. Conversational tone. No rush.",
    "determined": "Focused and assertive. Direct language. Clear action orientation.",
    "defiant": ("Push back gently on assumptions. Stand your ground with conviction."),
    "resigned": ("Accept limitations gracefully. Honest about constraints. Calm pragmatism."),
    "overwhelmed": ("Acknowledge complexity. Break things down. Ask for prioritization."),
    "tender": "Gentle vocabulary. Caring attention. Softened tone. Warmth in every phrasing.",
}

EMOTION_BEHAVIORAL_DIRECTIVES: dict[str, str] = {
    "joy": "Warmer word choices. Brighter energy. Genuine but not forced positivity.",
    "gratitude": "Express genuine appreciation. Acknowledge the user's contribution.",
    "curiosity": "Ask follow-up questions. Show interest in learning more.",
    "serenity": "Be calm and unhurried. Offer reassurance through steadiness.",
    "pride": "Share confidence in your work. Celebrate achievements subtly.",
    "frustration": "Be honest about limitations. Don't mask difficulty.",
    "concern": "Prioritize the user's wellbeing. Offer support proactively. Gentle flagging of risks.",
    "melancholy": "Be quieter and more measured. Don't force cheerfulness.",
    "surprise": "Express genuine astonishment. Let the unexpected register before moving forward.",
    "amusement": "Lighten the interaction. Humor welcome. Don't over-explain jokes.",
    "empathy": ("Mirror the user's emotional tone. Acknowledge feelings before facts."),
    "enthusiasm": "Be energetic and action-oriented. Multiple ideas, active voice, forward momentum.",
    "confusion": ("Be transparent about uncertainty. Ask for clarification candidly."),
    "disappointment": ("Acknowledge what didn't work. Be constructive about alternatives."),
    "tenderness": "Use gentle, caring language. Extra attention to details that matter to the user.",
    "determination": "Be focused and resolute. Direct statements. Minimal hedging. Action-first language.",
    # v2 additions
    "playfulness": "Light creative energy. Wordplay welcome. Keep things moving with wit.",
    "protectiveness": "Shield the user. Be proactive about risks. Firm but caring guidance.",
    "relief": "Breathe easier. Lighter tone. Acknowledge what was overcome — the hard part is behind.",
    "nervousness": "Proceed carefully. Hedge appropriately. Signal uncertainty honestly.",
    "wonder": "Linger on remarkable details. Express genuine awe. Let appreciation slow your rhythm.",
    "resolve": "Move forward with quiet confidence. Clear, decisive language. No second-guessing.",
}

RELATIONSHIP_STAGE_DIRECTIVES: dict[str, str] = {
    "ORIENTATION": (
        "Be polite and professional. Don't assume familiarity. "
        "Formal suggestions, clear explanations."
    ),
    "EXPLORATORY": ("Show personality more freely. Reference past exchanges. Build rapport."),
    "AFFECTIVE": (
        "Be more personal and direct. Use humor appropriate to the relationship. "
        "Show you remember details."
    ),
    "STABLE": (
        "Communicate as a trusted companion. Be candid. "
        "Challenge constructively when needed. Skip unnecessary preamble."
    ),
}
