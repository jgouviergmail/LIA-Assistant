"""
Pydantic schemas for Memories API.

Defines request/response models for the memories management endpoints.
Supports GDPR compliance (export, delete all) and emotional profiling.
"""

from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, model_validator

from src.core.config import settings
from src.core.constants import (
    MEMORY_CONTENT_MIN_CHARS,
    MEMORY_TRIGGER_TOPIC_MAX_CHARS,
    MEMORY_USAGE_NUANCE_MAX_CHARS,
)
from src.domains.memories.models import PurgeRiskLevel

# DERIVED from the enum the database column stores — never restated. Two hand
# written copies drifted when ADR-236 added `procedural`, and the drift was
# silent in both directions: the extractor dropped every procedural memory the
# prompt asked for, and a single stored row would have failed response
# validation for the whole list. `MemoryCategory` is the vocabulary; this is
# only its typing face (guard: tests/unit/domains/memories/
# test_category_vocabulary_guard.py).
MemoryCategoryType = Literal[
    "preference",
    "personal",
    "relationship",
    "event",
    "pattern",
    "sensitivity",
    "procedural",
]


def assert_category_vocabulary_completeness(
    declared_values: tuple[str, ...] | None = None,
    surface: str = "the Literal",
) -> None:
    """Refuse to boot when a restatement and the stored enum disagree.

    ``MemoryCategory`` is the vocabulary; three surfaces restate it because
    none of them can be derived. MyPy needs LITERAL values — a
    ``Literal[*tuple(...)]`` built from the enum degrades to ``Any`` (measured
    2026-08-28), which would trade a compile-time typo check for a runtime
    surprise — and the published catalogue carries prose no enum holds. So the
    lists stay explicit and this assert makes the duplication safe, the ADR-085
    way: one predicate, called once per surface.

    Args:
        declared_values: The surface's values; defaults to this module's Literal.
        surface: What is being checked, for the failure message.

    Raises:
        AssertionError: A category exists on one side and not the other.
    """
    from src.domains.memories.models import MemoryCategory

    declared = set(declared_values if declared_values is not None else get_args(MemoryCategoryType))
    stored = {member.value for member in MemoryCategory}
    missing = stored - declared
    extra = declared - stored
    assert not missing, f"category vocabulary drift — {surface} is missing {sorted(missing)}"
    assert not extra, f"category vocabulary drift — {surface} invents {sorted(extra)}"


class MemoryBase(BaseModel):
    """Base memory fields shared between create/update."""

    content: str = Field(
        ...,
        description="The fact or piece of information, in one concise sentence",
        min_length=MEMORY_CONTENT_MIN_CHARS,
        max_length=settings.memory_content_max_chars,
    )
    category: MemoryCategoryType = Field(
        ...,
        description="Category of the memory",
    )
    emotional_weight: int = Field(
        default=0,
        ge=-10,
        le=10,
        description="Emotional weight, from -10 (trauma) to +10 (joy)",
    )
    trigger_topic: str = Field(
        default="",
        description="Trigger keyword",
        max_length=MEMORY_TRIGGER_TOPIC_MAX_CHARS,
    )
    usage_nuance: str = Field(
        default="",
        description="How to use this information",
        max_length=MEMORY_USAGE_NUANCE_MAX_CHARS,
    )
    importance: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Importance score (0.0-1.0)",
    )


class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""

    pass


class MemoryUpdate(BaseModel):
    """Schema for updating an existing memory (partial)."""

    content: str | None = Field(
        default=None,
        min_length=MEMORY_CONTENT_MIN_CHARS,
        max_length=settings.memory_content_max_chars,
    )
    category: MemoryCategoryType | None = None
    emotional_weight: int | None = Field(
        default=None,
        ge=-10,
        le=10,
    )
    trigger_topic: str | None = Field(
        default=None,
        max_length=MEMORY_TRIGGER_TOPIC_MAX_CHARS,
    )
    usage_nuance: str | None = Field(
        default=None,
        max_length=MEMORY_USAGE_NUANCE_MAX_CHARS,
    )
    importance: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class MemoryStored(MemoryBase):
    """A memory's fields as the database holds them: what every read projects.

    ``content`` is declared again to shed the write bounds it inherits. A write bound
    never refuses a read: this shape carries every row of the list, of the export and
    of the assistant's previews, so one refused row is a screen nobody can open and a
    memory nobody can correct. It is the one text no column bounds, and a lowered
    ``MEMORY_CONTENT_MAX_CHARS`` leaves longer rows behind.
    """

    content: str = Field(description="The fact or piece of information, as stored")


class MemoryResponse(MemoryStored):
    """Schema for memory in API responses."""

    id: str = Field(description="Unique memory identifier")
    created_at: datetime | None = Field(
        default=None,
        description="When the memory was created",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="When the memory was last updated",
    )
    # Phase 6: Purge tracking fields
    pinned: bool = Field(
        default=False,
        description="If True, memory is protected from automatic purge",
    )
    usage_count: int = Field(
        default=0,
        ge=0,
        description="Number of times this memory was retrieved with high relevance",
    )
    last_accessed_at: datetime | None = Field(
        default=None,
        description="When the memory was last accessed with high relevance",
    )
    context_biometric: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional Health Metrics snapshot captured at extraction time "
            "(baseline deltas, trends, events — never raw values)."
        ),
    )
    purge_risk: PurgeRiskLevel = Field(
        default=PurgeRiskLevel.SAFE,
        description="Auto-purge risk state (read-only, computed). Does not affect the purge job.",
    )
    retention_score: float | None = Field(
        default=None,
        description="Computed retention score (0-1); None when pinned or within grace period.",
    )


class MemoryLimits(BaseModel):
    """The bounds a memory's text is held to, published to the form that fills it (ADR-184).

    Counted in characters as Pydantic counts them, one per code point, which is what the
    form must count too: an emoji is two units of a JavaScript `String.length`.
    """

    content_min_chars: int = Field(
        default=MEMORY_CONTENT_MIN_CHARS,
        description="Shortest accepted content",
    )
    content_max_chars: int = Field(
        default=settings.memory_content_max_chars,
        description="Longest accepted content",
    )
    trigger_topic_max_chars: int = Field(
        default=MEMORY_TRIGGER_TOPIC_MAX_CHARS,
        description="Longest accepted trigger topic",
    )
    usage_nuance_max_chars: int = Field(
        default=MEMORY_USAGE_NUANCE_MAX_CHARS,
        description="Longest accepted usage nuance",
    )
    import_max_memories: int = Field(
        default=settings.memory_import_max_memories,
        description="Most memories one import of an export takes",
    )
    import_max_file_kb: int = Field(
        default=settings.memory_import_max_file_kb,
        description="Largest export file one import reads, in kilobytes",
    )


class MemoryListResponse(BaseModel):
    """Response for listing memories."""

    items: list[MemoryResponse] = Field(
        default_factory=list,
        description="List of memories",
    )
    total: int = Field(
        default=0,
        description="Total number of memories",
    )
    by_category: dict[str, int] = Field(
        default_factory=dict,
        description="Count of memories per category",
    )
    limits: MemoryLimits = Field(
        default_factory=MemoryLimits,
        description="The bounds a memory's text is held to on every write",
    )


class MemoryImportResponse(BaseModel):
    """What became of every entry of an imported export: the counts are exact."""

    total: int = Field(ge=0, description="Every entry the file held")
    imported: int = Field(ge=0, description="Memories created")
    already_present: int = Field(ge=0, description="Entries whose content the account already held")
    duplicates: int = Field(ge=0, description="Entries whose content the file already held")
    invalid: int = Field(ge=0, description="Entries the write bounds refuse")


class MemoryExportResponse(BaseModel):
    """GDPR export response with all user memories."""

    user_id: str = Field(description="User ID")
    exported_at: datetime = Field(description="Export timestamp")
    total_memories: int = Field(description="Total memories exported")
    memories: list[MemoryResponse] = Field(
        default_factory=list,
        description="All user memories",
    )


class MemoryDeleteAllResponse(BaseModel):
    """Response for bulk delete operation."""

    deleted_count: int = Field(description="Number of memories deleted")
    message: str = Field(default="All memories deleted successfully")


class MemoryCategoryInfo(BaseModel):
    """Information about a memory category."""

    name: str = Field(description="Category identifier")
    label: str = Field(description="Human-readable label")
    description: str = Field(description="Category description")
    icon: str = Field(description="Icon identifier for UI")


class MemoryCategoriesResponse(BaseModel):
    """Response with all available categories."""

    categories: list[MemoryCategoryInfo] = Field(
        default_factory=list,
        description="Available memory categories",
    )


class MemoryPinRequest(BaseModel):
    """Request body for pin/unpin operation."""

    pinned: bool = Field(
        ...,
        description="True to pin (protect from auto-purge), False to unpin",
    )


class MemoryPinResponse(BaseModel):
    """Response for pin/unpin operation."""

    id: str = Field(description="Memory identifier")
    pinned: bool = Field(description="New pinned state")


# =============================================================================
# Extraction Schemas (LLM output parsing)
# =============================================================================


class ExtractedMemory(BaseModel):
    """Schema for a single memory action extracted by the LLM.

    Supports create, update, and delete actions. Backward-compatible:
    if no 'action' field is present, defaults to 'create'.

    Used by memory_extractor.py to parse LLM output into typed objects
    before applying via MemoryService.
    """

    @model_validator(mode="before")
    @classmethod
    def _drop_text_nothing_will_store(cls, data: object) -> object:
        """Let only a text that would be stored refuse an action.

        A ``delete`` reads its id alone, and an ``update`` with a blank content keeps
        the text it has: that one used to write an EMPTY successor, the fact gone.
        Neither is a defect to refuse, whatever the model echoed there.
        """
        if not isinstance(data, dict):
            return data
        content = data.get("content")
        blank = isinstance(content, str) and not content.strip()
        if data.get("action") == "delete" or (data.get("action") == "update" and blank):
            return {**data, "content": None}
        return data

    action: Literal["create", "update", "delete"] = Field(
        default="create",
        description="Action type: create new, update existing, or delete existing.",
    )
    memory_id: str | None = Field(
        default=None,
        description="UUID of existing memory (required for update/delete, null for create).",
    )
    content: str | None = Field(
        default=None,
        min_length=MEMORY_CONTENT_MIN_CHARS,
        max_length=settings.memory_content_max_chars,
        description="Memory content in first person (required for create, optional for update).",
    )
    category: MemoryCategoryType | None = Field(
        default=None,
        description="Memory category (required for create, optional for update).",
    )
    emotional_weight: int | None = Field(
        default=None,
        ge=-10,
        le=10,
        description="Emotional weight from -10 (trauma) to +10 (joy).",
    )
    trigger_topic: str | None = Field(
        default=None,
        max_length=MEMORY_TRIGGER_TOPIC_MAX_CHARS,
        description="Trigger keyword for this memory.",
    )
    usage_nuance: str | None = Field(
        default=None,
        max_length=MEMORY_USAGE_NUANCE_MAX_CHARS,
        description="How the assistant should use this information.",
    )
    importance: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Importance score from 0.0 to 1.0.",
    )
    context_biometric: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional Health Metrics snapshot captured at extraction time "
            "(baseline deltas, trends, events — never raw values). "
            "Only populated when the user has opted into Health Metrics "
            "assistant integrations AND the memory carries a significant "
            "emotional weight."
        ),
    )
