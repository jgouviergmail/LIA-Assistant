"""
Journals configuration module.

Contains settings for the Personal Journals (Carnets de Bord) feature:
- Feature toggles (extraction, consolidation)
- Extraction parameters (min messages)
- Consolidation parameters (interval, cooldown, history)
- Size constraints (max total chars, max entry chars)
- Context injection parameters (max chars, max results)

Phase: evolution — Personal Journals (Assistant Logbooks)
Created: 2026-03-19
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    JOURNAL_CONSOLIDATION_COOLDOWN_HOURS_DEFAULT,
    JOURNAL_CONSOLIDATION_HISTORY_MAX_DAYS_DEFAULT,
    JOURNAL_CONSOLIDATION_HISTORY_MAX_MESSAGES_DEFAULT,
    JOURNAL_CONSOLIDATION_INTERVAL_HOURS_DEFAULT,
    JOURNAL_CONSOLIDATION_MIN_ENTRIES_DEFAULT,
    JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION_DEFAULT,
    JOURNAL_CONTEXT_MAX_CHARS_DEFAULT,
    JOURNAL_CONTEXT_MAX_RESULTS_DEFAULT,
    JOURNAL_CONTEXT_MIN_SCORE_DEFAULT,
    JOURNAL_CONTEXT_RECENT_ENTRIES_DEFAULT,
    JOURNAL_EMBEDDING_DIMENSIONS_DEFAULT,
    JOURNAL_EMBEDDING_MODEL_DEFAULT,
    JOURNAL_EXTRACTION_MIN_MESSAGES_DEFAULT,
    JOURNAL_MAX_ENTRY_CHARS_DEFAULT,
    JOURNAL_MAX_TOTAL_CHARS_DEFAULT,
    JOURNAL_PORTRAIT_BRIEF_MAX_TOKENS_DEFAULT,
    JOURNAL_PORTRAIT_FULL_MAX_TOKENS_DEFAULT,
    JOURNAL_REACT_CONTEXT_MAX_ENTRIES_DEFAULT,
    JOURNAL_SEARCH_MAX_RESULTS_DEFAULT,
)


class JournalsSettings(BaseSettings):
    """Settings for the Personal Journals (Carnets de Bord) feature."""

    # ========================================================================
    # Feature Toggles (system-level, .env)
    # ========================================================================

    journals_enabled: bool = Field(
        default=True,
        description=(
            "Global feature flag for Personal Journals. "
            "When false, the entire domain is disabled (no router, no extraction, no consolidation)."
        ),
    )

    journal_extraction_enabled: bool = Field(
        default=True,
        description=(
            "Enable post-conversation journal extraction. "
            "When false, the assistant does not write journal entries after conversations."
        ),
    )

    # ========================================================================
    # Extraction Parameters
    # ========================================================================

    journal_extraction_min_messages: int = Field(
        default=JOURNAL_EXTRACTION_MIN_MESSAGES_DEFAULT,
        ge=1,
        le=20,
        description="Minimum number of messages in conversation before extraction triggers.",
    )

    # ========================================================================
    # Consolidation Parameters (system-level intervals)
    # ========================================================================

    journal_consolidation_interval_hours: int = Field(
        default=JOURNAL_CONSOLIDATION_INTERVAL_HOURS_DEFAULT,
        ge=1,
        le=48,
        description="APScheduler interval in hours between consolidation runs.",
    )

    journal_consolidation_cooldown_hours: int = Field(
        default=JOURNAL_CONSOLIDATION_COOLDOWN_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="Minimum hours between two consolidations for the same user.",
    )

    journal_consolidation_min_entries: int = Field(
        default=JOURNAL_CONSOLIDATION_MIN_ENTRIES_DEFAULT,
        ge=1,
        le=50,
        description="Minimum number of active entries before consolidation is eligible.",
    )

    journal_consolidation_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=1800,
        description="Hard bound for a consolidation operation, including maintenance settlement.",
    )

    journal_consolidation_history_max_messages: int = Field(
        default=JOURNAL_CONSOLIDATION_HISTORY_MAX_MESSAGES_DEFAULT,
        ge=10,
        le=200,
        description="Max conversation messages loaded when history analysis is enabled.",
    )

    journal_consolidation_history_max_days: int = Field(
        default=JOURNAL_CONSOLIDATION_HISTORY_MAX_DAYS_DEFAULT,
        ge=1,
        le=30,
        description="Max lookback days for conversation history (bounds null/old last_consolidated_at).",
    )

    # ========================================================================
    # Portrait compilation — budgets and the nine sources it reads
    # (2026-09-16 design, part B; ADR-343)
    # ========================================================================

    journal_portrait_full_max_tokens: int = Field(
        default=JOURNAL_PORTRAIT_FULL_MAX_TOKENS_DEFAULT,
        ge=100,
        le=1000,
        description=(
            "Token target the consolidation prompt states for the full portrait "
            "(response and planner flows); the publication keeps every verified claim "
            "whole. Read by the prompt, never written in prose."
        ),
    )

    journal_portrait_brief_max_tokens: int = Field(
        default=JOURNAL_PORTRAIT_BRIEF_MAX_TOKENS_DEFAULT,
        ge=30,
        le=300,
        description="Token budget the consolidation prompt states for the brief portrait.",
    )

    journal_consolidation_sources_window_fraction: float = Field(
        default=JOURNAL_CONSOLIDATION_SOURCES_WINDOW_FRACTION_DEFAULT,
        gt=0.0,
        le=0.9,
        description=(
            "Share of the journal_consolidation slot's effective context window the "
            "portrait sources may occupy; sections keep their order, every item is whole, "
            "and a cut at the end of the last sections is stated in the provenance."
        ),
    )

    # ========================================================================
    # Size Constraints (defaults for user settings)
    # ========================================================================

    journal_default_max_total_chars: int = Field(
        default=JOURNAL_MAX_TOTAL_CHARS_DEFAULT,
        ge=5000,
        le=200000,
        description="Default max total characters across all active entries per user.",
    )

    journal_default_context_max_chars: int = Field(
        default=JOURNAL_CONTEXT_MAX_CHARS_DEFAULT,
        ge=200,
        le=10000,
        description="Default max characters for journal context injection into prompts.",
    )

    journal_max_entry_chars: int = Field(
        default=JOURNAL_MAX_ENTRY_CHARS_DEFAULT,
        ge=100,
        le=2000,
        description="Maximum characters per individual journal entry.",
    )

    # ========================================================================
    # Context Injection Parameters
    # ========================================================================

    journal_context_max_results: int = Field(
        default=JOURNAL_CONTEXT_MAX_RESULTS_DEFAULT,
        ge=1,
        le=30,
        description="Max entries returned by semantic search for context injection.",
    )

    journal_react_context_max_entries: int = Field(
        default=JOURNAL_REACT_CONTEXT_MAX_ENTRIES_DEFAULT,
        ge=0,
        le=15,
        description=(
            "Max L1/L2 behavioural directives injected into the ReAct reasoning loop "
            "(once, at react_setup). Count cap with no truncation — entries are injected "
            "in full. Set to 0 to disable directive injection in ReAct (portrait only)."
        ),
    )

    journal_search_max_results: int = Field(
        default=JOURNAL_SEARCH_MAX_RESULTS_DEFAULT,
        ge=1,
        le=30,
        description=(
            "Most entries one journal lookup (search_journal_tool, ADR-318) returns. "
            "Published to the planner and the ReAct loop as the parameter's maximum."
        ),
    )

    journal_context_recent_entries: int = Field(
        default=JOURNAL_CONTEXT_RECENT_ENTRIES_DEFAULT,
        ge=0,
        le=5,
        description=(
            "Number of most recent journal entries to always inject, regardless of "
            "semantic score. Provides temporal continuity for the assistant's reflections. "
            "These count toward max_results and max_chars budgets."
        ),
    )

    # ========================================================================
    # Embedding Configuration
    # ========================================================================

    journal_embedding_model: str = Field(
        default=JOURNAL_EMBEDDING_MODEL_DEFAULT,
        description=(
            "Gemini embedding model for journal entry indexing and search. "
            "Default: gemini-embedding-001 (1536d)."
        ),
    )

    journal_embedding_dimensions: int = Field(
        default=JOURNAL_EMBEDDING_DIMENSIONS_DEFAULT,
        ge=256,
        le=4096,
        description=(
            "Embedding vector dimensions for journal entries. "
            "Must match the chosen embedding model output dimensions."
        ),
    )

    journal_context_min_score: float = Field(
        default=JOURNAL_CONTEXT_MIN_SCORE_DEFAULT,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum cosine similarity score to include a journal entry in context injection. "
            "Entries below this threshold are discarded before being sent to the LLM. "
            "The LLM then decides relevance among the remaining entries based on scores."
        ),
    )
