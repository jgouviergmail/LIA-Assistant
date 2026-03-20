"""
Constants for the Journals domain.

Centralizes default values and configuration constants
used across journal services, repository, and router.
"""

# =========================================================================
# Entry limits
# =========================================================================

JOURNAL_ENTRY_TITLE_MAX_LENGTH = 200
JOURNAL_ENTRY_CONTENT_MAX_LENGTH = 2000

# =========================================================================
# Extraction defaults
# =========================================================================

# Number of recent entries loaded in full for extraction context (continuity + dedup)
JOURNAL_EXTRACTION_RECENT_ENTRIES_FULL = 10

# Number of context messages around last user message (same pattern as memory_extractor)
JOURNAL_EXTRACTION_CONTEXT_MESSAGES = 4

# Max characters per message in extraction context (truncation)
JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS = 1000

# =========================================================================
# Embedding
# =========================================================================

# E5-small embedding dimensions (same as UserInterest.embedding)
JOURNAL_EMBEDDING_DIMENSIONS = 384

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
