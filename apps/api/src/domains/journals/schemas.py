"""
Pydantic schemas for the Journals domain API.

Schemas:
- JournalEntryResponse: Entry data for API responses
- JournalEntryCreate: Create a new entry manually
- JournalEntryUpdate: Partial update of an entry
- JournalEntryListResponse: Paginated list with size info
- JournalSettingsResponse: User journal settings + size + cost info
- JournalSettingsUpdate: Update user journal settings
- JournalCostInfo: Cost details of last background intervention
- ExtractedJournalEntry: Internal schema for LLM extraction results
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.journals.constants import (
    JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
    JOURNAL_ENTRY_TITLE_MAX_LENGTH,
)
from src.domains.journals.models import (
    JournalEntryConfidence,
    JournalEntryLevel,
    JournalEntryMood,
    JournalEntrySource,
    JournalEntryStatus,
    JournalTheme,
)

# =============================================================================
# Entry Schemas
# =============================================================================


class JournalEntryResponse(BaseModel):
    """Journal entry data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Unique identifier of the journal entry")
    theme: JournalTheme = Field(description="Thematic category of the entry")
    title: str = Field(description="Short descriptive title")
    content: str = Field(description="Full entry content")
    mood: JournalEntryMood = Field(description="Emotional tone of the entry")
    status: JournalEntryStatus = Field(description="Entry lifecycle status (active/archived)")
    source: JournalEntrySource = Field(
        description="Origin of the entry (conversation/consolidation/manual)"
    )
    personality_code: str | None = Field(
        description="Active personality code when entry was created"
    )
    char_count: int = Field(description="Character count of the content")
    search_hints: list[str] | None = Field(
        None,
        description="LLM-generated search keywords bridging user vocabulary to entry content",
    )
    injection_count: int = Field(
        description="Number of times this entry was injected into prompts",
    )
    last_injected_at: datetime | None = Field(
        None,
        description="Last time this entry was injected into a prompt (UTC)",
    )
    confidence: JournalEntryConfidence = Field(
        description="Epistemic status: low (hypothesis), medium (default), high (validated)",
    )
    evidence_count: int = Field(
        description="Times this entry was confirmed by deferred self-evaluation",
    )
    contradiction_count: int = Field(
        description="Times this entry was contradicted by deferred self-evaluation",
    )
    level: JournalEntryLevel = Field(
        description=(
            "Abstraction level: L0 raw observations, L1 operational directives, "
            "L2 transversal patterns, L3 portrait facets"
        ),
    )
    created_at: datetime = Field(description="Creation timestamp (UTC)")
    updated_at: datetime = Field(description="Last modification timestamp (UTC)")


class JournalEntryCreate(BaseModel):
    """Create a new journal entry manually."""

    theme: JournalTheme = Field(
        description="Thematic category for the entry",
    )
    title: str = Field(
        min_length=1,
        max_length=JOURNAL_ENTRY_TITLE_MAX_LENGTH,
        description="Short descriptive title",
    )
    content: str = Field(
        min_length=1,
        max_length=JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        description="Full entry content",
    )
    mood: JournalEntryMood = Field(
        default=JournalEntryMood.REFLECTIVE,
        description="Emotional tone of the entry",
    )
    search_hints: list[str] | None = Field(
        None,
        description="3-5 keywords in user vocabulary for semantic search bridging",
    )


class JournalEntryUpdate(BaseModel):
    """Partial update of a journal entry."""

    title: str | None = Field(
        None,
        min_length=1,
        max_length=JOURNAL_ENTRY_TITLE_MAX_LENGTH,
        description="Short descriptive title",
    )
    content: str | None = Field(
        None,
        min_length=1,
        max_length=JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        description="Full entry content (triggers embedding regeneration)",
    )
    mood: JournalEntryMood | None = Field(
        None,
        description="Emotional tone of the entry",
    )
    search_hints: list[str] | None = Field(
        None,
        description="3-5 keywords in user vocabulary for semantic search bridging",
    )
    confidence: JournalEntryConfidence | None = Field(
        None,
        description=(
            "Epistemic status — user may override the LLM's classification. "
            "Counters (evidence_count, contradiction_count) remain system-managed."
        ),
    )
    level: JournalEntryLevel | None = Field(
        None,
        description=(
            "Abstraction level — user may promote/demote between L0/L1/L2/L3. "
            "L3 entries form the portrait that LIA carries everywhere it speaks."
        ),
    )


# =============================================================================
# List Schema
# =============================================================================


class ThemeCount(BaseModel):
    """Entry count for a single theme."""

    theme: JournalTheme = Field(description="Theme identifier")
    count: int = Field(description="Number of active entries for this theme")


class JournalEntryListResponse(BaseModel):
    """Paginated journal entry list with size info."""

    entries: list[JournalEntryResponse]
    total: int
    by_theme: list[ThemeCount]
    total_chars: int = Field(description="Total characters across all active entries")
    max_total_chars: int = Field(description="User's configured max total characters")
    usage_pct: float = Field(description="Usage percentage (total_chars / max_total_chars)")


# =============================================================================
# Settings Schemas
# =============================================================================


class JournalCostInfo(BaseModel):
    """Cost details of the last background journal intervention."""

    tokens_in: int | None = Field(None, description="Input tokens consumed by the LLM call")
    tokens_out: int | None = Field(None, description="Output tokens generated by the LLM call")
    cost_eur: Decimal | None = Field(None, description="Total cost in EUR for the intervention")
    timestamp: datetime | None = Field(None, description="When the intervention occurred (UTC)")
    source: str | None = Field(None, description="'extraction' or 'consolidation'")


class JournalSizeInfo(BaseModel):
    """Size usage information for the journal."""

    total_chars: int = Field(description="Total characters across all active entries")
    max_total_chars: int = Field(description="User's configured maximum total characters")
    usage_pct: float = Field(description="Usage percentage (total_chars / max_total_chars * 100)")


class JournalSettingsResponse(BaseModel):
    """User journal settings with size and cost info."""

    journals_enabled: bool = Field(description="Whether journals feature is enabled for this user")
    journal_consolidation_enabled: bool = Field(
        description="Whether background consolidation is enabled"
    )
    journal_consolidation_with_history: bool = Field(
        description="Whether consolidation uses conversation history"
    )
    journal_max_total_chars: int = Field(description="Maximum total characters across all entries")
    journal_context_max_chars: int = Field(
        description="Maximum characters for context injection into prompts"
    )
    journal_max_entry_chars: int = Field(description="Maximum characters per individual entry")
    journal_context_max_results: int = Field(
        description="Maximum entries returned by semantic search"
    )
    size_info: JournalSizeInfo = Field(description="Current size usage information")
    last_cost: JournalCostInfo = Field(
        description="Cost details of the last background intervention"
    )


class JournalSettingsUpdate(BaseModel):
    """Update user journal settings (partial)."""

    journals_enabled: bool | None = Field(
        None, description="Enable or disable journals for this user."
    )
    journal_consolidation_enabled: bool | None = Field(
        None, description="Enable or disable background consolidation."
    )
    journal_consolidation_with_history: bool | None = Field(
        None, description="Whether consolidation should use conversation history."
    )
    journal_max_total_chars: int | None = Field(
        None,
        ge=5000,
        le=200000,
        description="Max total characters. Cannot be set below current total_chars.",
    )
    journal_context_max_chars: int | None = Field(
        None,
        ge=200,
        le=10000,
        description="Max characters for context injection into prompts.",
    )
    journal_max_entry_chars: int | None = Field(
        None,
        ge=100,
        le=2000,
        description="Max characters per individual journal entry.",
    )
    journal_context_max_results: int | None = Field(
        None,
        ge=1,
        le=30,
        description="Max entries returned by semantic search for context injection.",
    )


# =============================================================================
# Themes Response
# =============================================================================


class JournalThemeInfo(BaseModel):
    """Theme information with i18n label."""

    code: str
    label: str


class JournalConsolidationResponse(BaseModel):
    """Result of a manual consolidation triggered by the user."""

    actions_applied: int = Field(
        description="Number of actions (create/update/delete) applied during the consolidation",
    )
    duration_ms: int = Field(
        description="Total duration of the consolidation run in milliseconds",
    )


class JournalPortraitResponse(BaseModel):
    """User-model portrait compiled by the journal consolidation.

    The portrait is a synthesis derived from the L3 portrait facets and the
    other signals (memories, interests, health, usage patterns). It is never
    user-editable directly — users act via the three levers:
    1. Editing/deleting L3 source entries
    2. POSTing feedback that triggers a synchronous re-consolidation
    3. Triggering a fresh consolidation
    """

    full: str | None = Field(
        None,
        description="Compiled portrait in full format (~200 tokens) for response/planner",
    )
    brief: str | None = Field(
        None,
        description="Compiled portrait in brief format (~60 tokens) for secondary flows",
    )
    compiled_at: datetime | None = Field(
        None,
        description="UTC timestamp of the last portrait compilation",
    )


class JournalPortraitFeedbackRequest(BaseModel):
    """User-initiated feedback signal on the compiled portrait (lever 2)."""

    comment: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Free-text correction signal — what is wrong / inaccurate / outdated. "
            "Will be persisted as a journal entry (level=L0, source=user_correction) "
            "and trigger a synchronous re-consolidation that prioritizes this signal."
        ),
    )
    highlighted_section: str | None = Field(
        None,
        max_length=500,
        description="Optional excerpt from the portrait the user highlighted as problematic",
    )


class JournalThemesResponse(BaseModel):
    """Available journal themes."""

    themes: list[JournalThemeInfo]


# =============================================================================
# Internal Schemas (LLM extraction/consolidation)
# =============================================================================


class ExtractedJournalEntry(BaseModel):
    """Internal schema for LLM extraction/consolidation results.

    Used to parse and validate JSON output from the introspection
    and consolidation prompts.
    """

    action: Literal["create", "update", "delete"] = Field(
        description="Action to perform on the journal",
    )
    entry_id: str | None = Field(
        None,
        description="Existing entry ID (required for update/delete, null for create)",
    )

    @field_validator("entry_id", mode="before")
    @classmethod
    def validate_entry_id_is_valid_uuid(cls, v: str | None) -> str | None:
        """Reject malformed UUIDs produced by LLM hallucination."""
        if v is None:
            return v
        try:
            UUID(str(v))
        except (ValueError, AttributeError) as err:
            raise ValueError(f"Invalid UUID for entry_id: {v!r}") from err
        return str(v)

    theme: JournalTheme | None = Field(
        None,
        description="Thematic category (required for create)",
    )
    title: str | None = Field(
        None,
        max_length=JOURNAL_ENTRY_TITLE_MAX_LENGTH,
        description="Entry title (required for create, optional for update)",
    )
    content: str | None = Field(
        None,
        max_length=JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        description="Entry content (required for create, optional for update)",
    )
    mood: JournalEntryMood | None = Field(
        None,
        description="Emotional tone (optional, defaults to reflective)",
    )
    search_hints: list[str] | None = Field(
        None,
        description=(
            "3-5 keywords in the USER's vocabulary that would make this entry relevant. "
            "Optional — LLM may omit for backward compatibility."
        ),
    )
    confidence: JournalEntryConfidence | None = Field(
        None,
        description=(
            "Epistemic status: low (single observation, untested hypothesis), "
            "medium (default for new entries), high (confirmed by repeated evidence). "
            "Optional on create (defaults to medium). On update, the LLM can promote "
            "to high after evidence accumulates, or downgrade after contradictions."
        ),
    )
    evidence_outcome: Literal["evidence", "contradiction"] | None = Field(
        None,
        description=(
            "Deferred self-evaluation signal — set on update actions only when the LLM "
            "observes that an injected directive from the previous turn was either confirmed "
            "(evidence) or contradicted (contradiction) by the user's reaction. "
            "The service atomically increments the corresponding counter on the entry. "
            "Never set the absolute counts directly — the LLM only signals the outcome."
        ),
    )
    level: JournalEntryLevel | None = Field(
        None,
        description=(
            "Abstraction level. L0 raw observations (transient), L1 directives "
            "(WHEN→DO BECAUSE — the legacy default), L2 transversal patterns synthesizing "
            "multiple convergent L1, L3 portrait facets (always-injected). On create, "
            "default is L1. On update, you may promote (L0→L1, L1→L2, L2→L3) when the "
            "evidence supports it, or demote when a synthesis loses its grounding."
        ),
    )


class ConsolidationParseResult(BaseModel):
    """Internal: parsed result of a consolidation LLM call.

    The consolidation prompt may return either:
    - A bare JSON array of actions (legacy format, before commit 3) — backwards
      compatible.
    - A JSON object ``{actions, portrait_full, portrait_brief}`` (commit 3+) —
      enriches the response with the compiled portraits.
    """

    actions: list[ExtractedJournalEntry] = Field(default_factory=list)
    portrait_full: str | None = None
    portrait_brief: str | None = None
