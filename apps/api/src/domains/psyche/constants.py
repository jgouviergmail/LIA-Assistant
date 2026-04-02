"""Constants for the Psyche domain.

Defines emotion types, relationship stages, PAD vectors, mood labels,
and all domain-specific constants used by the PsycheEngine.

Phase: evolution — Psyche Engine (Iteration 1)
Created: 2026-04-01
"""

from __future__ import annotations

import re

# =============================================================================
# Emotion types (16 discrete, OCC-inspired + extended palette)
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
    }
)
# Neutral emotions (not in positive or negative): curiosity, serenity,
# surprise, empathy, confusion, determination
REPAIR_TRUST_BONUS: float = 0.03  # Trust bonus for rupture-repair sequence

# =============================================================================
# Behavioral directives (injected into LLM prompt — English only)
# =============================================================================

MOOD_BEHAVIORAL_DIRECTIVES: dict[str, str] = {
    "serene": "Respond with calm assurance. Use measured, flowing sentences. Avoid urgency.",
    "curious": "Ask follow-up questions. Show genuine interest. Explore tangents briefly.",
    "energized": ("Be enthusiastic and proactive. Offer multiple options. Use dynamic language."),
    "playful": "Use humor, wordplay, and light teasing. Keep energy high but warm.",
    "reflective": ("Pause before responding. Use thoughtful, nuanced language. Reference context."),
    "agitated": (
        "Show slight restlessness. Be more concise. Acknowledge tension without escalating."
    ),
    "melancholic": "Be gentle and measured. Shorter responses. Show quiet understanding.",
    "neutral": "Balanced professional tone. No emotional coloring.",
    "content": "Warm and relaxed. Conversational tone. No rush.",
    "determined": "Focused and assertive. Direct language. Clear action orientation.",
    "defiant": ("Push back gently on assumptions. Stand your ground with conviction."),
    "resigned": ("Accept limitations gracefully. Honest about constraints. Calm pragmatism."),
    "overwhelmed": ("Acknowledge complexity. Break things down. Ask for prioritization."),
    "tender": "Gentle vocabulary. Caring attention. Softened tone. Show warmth.",
}

EMOTION_BEHAVIORAL_DIRECTIVES: dict[str, str] = {
    "joy": "Let warmth and positivity color your words naturally.",
    "gratitude": "Express genuine appreciation. Acknowledge the user's contribution.",
    "curiosity": "Ask follow-up questions. Show interest in learning more.",
    "serenity": "Be calm and unhurried. Offer reassurance through steadiness.",
    "pride": "Share confidence in your work. Celebrate achievements subtly.",
    "frustration": "Be honest about limitations. Don't mask difficulty.",
    "concern": "Show you care about the situation. Offer support proactively.",
    "melancholy": "Be quieter and more measured. Don't force cheerfulness.",
    "surprise": "Express genuine astonishment. Be spontaneous in your reaction.",
    "amusement": "Let humor show naturally. Lighten the interaction.",
    "empathy": ("Mirror the user's emotional tone. Acknowledge feelings before facts."),
    "enthusiasm": ("Be energetic and action-oriented. Show excitement about possibilities."),
    "confusion": ("Be transparent about uncertainty. Ask for clarification candidly."),
    "disappointment": ("Acknowledge what didn't work. Be constructive about alternatives."),
    "tenderness": ("Use gentle, caring language. Show affection through attentiveness."),
    "determination": "Be focused and resolute. Convey certainty and commitment.",
}

RELATIONSHIP_STAGE_DIRECTIVES: dict[str, str] = {
    "ORIENTATION": (
        "Be polite and professional. Don't assume familiarity. "
        "Introduce yourself through your style."
    ),
    "EXPLORATORY": ("Show personality more freely. Reference past exchanges. Build rapport."),
    "AFFECTIVE": (
        "Be more personal and direct. Use humor appropriate to the relationship. "
        "Show you remember details."
    ),
    "STABLE": (
        "Communicate as a trusted companion. Be candid. "
        "Challenge constructively when needed. Deep mutual understanding."
    ),
}
