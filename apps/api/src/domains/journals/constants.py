"""
Constants for the Journals domain.

Centralizes default values and configuration constants
used across journal services, repository, and router.
"""

# =========================================================================
# Entry limits
# =========================================================================

JOURNAL_ENTRY_TITLE_MAX_LENGTH = 200
JOURNAL_ENTRY_CONTENT_MAX_LENGTH = 800

# =========================================================================
# Extraction defaults
# =========================================================================

# Number of context messages around last user message (same pattern as memory_extractor)
JOURNAL_EXTRACTION_CONTEXT_MESSAGES = 4

# Max characters per message in extraction context (truncation)
JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS = 1000

# Semantic pre-filter for extraction (replaces get_all_active)
JOURNAL_EXTRACTION_SEMANTIC_LIMIT = 10  # Top N entries semantically close to user message
JOURNAL_EXTRACTION_RECENT_LIMIT = 3  # K most recent entries (temporal continuity)
JOURNAL_EXTRACTION_DEDUP_MIN_SCORE = 0.4  # Min similarity for pre-filter

# =========================================================================
# Operational injection — level routing
# =========================================================================

# Levels NEVER injected into operational prompts (response/planner/heartbeat/
# reminder/react). L0 = private raw feedstock managed by consolidation only;
# L3 = portrait facets already carried by the compiled portrait
# (build_journal_user_model_block). Only L1/L2 behavioural directives are
# injected operationally. Extraction/consolidation still see ALL levels
# (they call the repository directly, without this exclusion).
JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS: list[str] = ["L0", "L3"]

# =========================================================================
# User-correction feedstock themes
# =========================================================================

# Both feedback levers land an L0 entry that the next consolidation reviews.
# The theme is picked with the introspection prompt's ordered ladder, by
# SUBJECT: feedback on a RESPONSE is a lesson about what the assistant did
# (`learnings`); feedback on the PORTRAIT corrects the model of the user
# (`user_observations`).
#
# Neither is `self_reflection`. That theme is reserved for the assistant's own
# tone/posture and requires a visible user reaction to it — labelling arbitrary
# user feedback `self_reflection` both mislabels it and made the theme's only
# live producer the one path that should never use it.
# Plain literals, not JournalTheme members: models.py imports this module, so
# importing it back would create a cycle.
JOURNAL_RESPONSE_FEEDBACK_THEME = "learnings"
JOURNAL_PORTRAIT_FEEDBACK_THEME = "user_observations"

# =========================================================================
# Embedding
# =========================================================================

# Gemini gemini-embedding-001 dimensions (pgvector Vector column)
JOURNAL_EMBEDDING_DIMENSIONS = 1536

# =========================================================================
# Mood emoji mapping (for context injection formatting)
# =========================================================================

JOURNAL_MOOD_EMOJI: dict[str, str] = {
    "reflective": "\U0001f60c",  # 😌
    "curious": "\U0001f50d",  # 🔍
    "satisfied": "\u2705",  # ✅
    "concerned": "\u26a0\ufe0f",  # ⚠️
    "inspired": "\U0001f4a1",  # 💡
}

# =========================================================================
# Source emoji mapping (for frontend display)
# =========================================================================

JOURNAL_SOURCE_EMOJI: dict[str, str] = {
    "conversation": "\U0001f4ac",  # 💬
    "consolidation": "\U0001f504",  # 🔄
    "manual": "\u270f\ufe0f",  # ✏️
}
