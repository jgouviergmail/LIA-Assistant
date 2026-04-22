"""
Pydantic schemas for Memories API.

Defines request/response models for the memories management endpoints.
Supports GDPR compliance (export, delete all) and emotional profiling.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Memory categories matching the MemorySchema
MemoryCategoryType = Literal[
    "preference",
    "personal",
    "relationship",
    "event",
    "pattern",
    "sensitivity",
]


class MemoryBase(BaseModel):
    """Base memory fields shared between create/update."""

    content: str = Field(
        ...,
        description="Le fait ou l'information en une phrase concise",
        min_length=3,
        max_length=500,
    )
    category: MemoryCategoryType = Field(
        ...,
        description="Catégorie de la mémoire",
    )
    emotional_weight: int = Field(
        default=0,
        ge=-10,
        le=10,
        description="Poids émotionnel de -10 (trauma) à +10 (joie)",
    )
    trigger_topic: str = Field(
        default="",
        description="Mot-clé déclencheur",
        max_length=100,
    )
    usage_nuance: str = Field(
        default="",
        description="Comment utiliser cette information",
        max_length=300,
    )
    importance: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Score d'importance (0.0-1.0)",
    )


class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""

    pass


class MemoryUpdate(BaseModel):
    """Schema for updating an existing memory (partial)."""

    content: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
    )
    category: MemoryCategoryType | None = None
    emotional_weight: int | None = Field(
        default=None,
        ge=-10,
        le=10,
    )
    trigger_topic: str | None = Field(
        default=None,
        max_length=100,
    )
    usage_nuance: str | None = Field(
        default=None,
        max_length=300,
    )
    importance: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class MemoryResponse(MemoryBase):
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
        max_length=100,
        description="Trigger keyword for this memory.",
    )
    usage_nuance: str | None = Field(
        default=None,
        max_length=300,
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
