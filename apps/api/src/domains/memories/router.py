"""
Memories router with FastAPI endpoints for user memory management.

Provides CRUD operations for long-term user memories with:
- Emotional profiling support
- Category-based organization
- Automatic embedding generation on create/update
- GDPR compliance (export, delete all)
- Phase 6 pin/unpin for purge protection

Phase: v1.14.0 — Migrated from LangGraph store to PostgreSQL custom
"""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    ResourceNotFoundError,
    raise_memory_not_found,
    raise_memory_store_error,
)
from src.core.export_utils import create_csv_response
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.tools.memory_tools import get_memory_categories
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.memories.retention import RetentionConfig, classify_purge_risk
from src.domains.memories.schemas import (
    MemoryCategoriesResponse,
    MemoryCategoryInfo,
    MemoryCreate,
    MemoryDeleteAllResponse,
    MemoryExportResponse,
    MemoryListResponse,
    MemoryPinRequest,
    MemoryPinResponse,
    MemoryResponse,
    MemoryUpdate,
)
from src.domains.memories.service import MemoryService
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/memories", tags=["Memories"])


def _build_retention_config() -> RetentionConfig:
    """Snapshot the current retention settings for risk classification.

    Returns:
        A frozen ``RetentionConfig`` built from the current settings.
    """
    return RetentionConfig(
        min_age_for_cleanup_days=settings.memory_min_age_for_cleanup_days,
        recency_decay_days=settings.memory_recency_decay_days,
        usage_penalty_age_days=settings.memory_usage_penalty_age_days,
        usage_penalty_factor=settings.memory_usage_penalty_factor,
        purge_threshold=settings.memory_purge_threshold,
        at_risk_margin=settings.memory_purge_at_risk_margin,
        weight_importance=settings.memory_retention_weight_importance,
        weight_recency=settings.memory_retention_weight_recency,
    )


def _memory_to_response(
    memory: Memory,
    now: datetime | None = None,
    config: RetentionConfig | None = None,
) -> MemoryResponse:
    """Convert a Memory ORM object to MemoryResponse (with computed purge risk).

    Args:
        memory: Memory ORM instance.
        now: Current datetime (one snapshot per request; defaults to UTC now).
        config: Retention configuration snapshot (defaults to current settings).
            Pass a shared instance when converting a list to avoid rebuilding it
            per item.

    Returns:
        MemoryResponse with all fields, including read-only purge-risk data.
    """
    now = now or datetime.now(UTC)
    config = config or _build_retention_config()
    purge_risk, retention_score = classify_purge_risk(memory, now, config)
    return MemoryResponse(
        id=str(memory.id),
        content=memory.content or "",
        category=memory.category or "personal",
        emotional_weight=memory.emotional_weight or 0,
        trigger_topic=memory.trigger_topic or "",
        usage_nuance=memory.usage_nuance or "",
        importance=memory.importance or 0.7,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        pinned=memory.pinned or False,
        usage_count=memory.usage_count or 0,
        last_accessed_at=memory.last_accessed_at,
        purge_risk=purge_risk,
        retention_score=retention_score,
    )


@router.get(
    "/categories",
    response_model=MemoryCategoriesResponse,
    summary="Get memory categories",
    description="Get list of available memory categories with descriptions.",
)
async def list_categories() -> MemoryCategoriesResponse:
    """Get available memory categories."""
    categories = get_memory_categories()
    return MemoryCategoriesResponse(categories=[MemoryCategoryInfo(**cat) for cat in categories])


@router.get(
    "/export",
    response_model=None,
    summary="Export all memories (GDPR)",
    description="Export all memories for the current user. Supports JSON and CSV formats.",
)
async def export_memories(
    export_format: Literal["json", "csv"] = Query(
        default="csv",
        alias="format",
        description="Export format (json or csv)",
    ),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryExportResponse | StreamingResponse:
    """Export all memories for GDPR data portability."""
    try:
        repo = MemoryRepository(db)
        all_memories = await repo.get_all_for_user(user.id)
        now = datetime.now(UTC)
        config = _build_retention_config()
        memories = [_memory_to_response(m, now, config) for m in all_memories]

        logger.info(
            "memories_exported",
            user_id=str(user.id),
            total=len(memories),
            export_format=export_format,
        )

        if export_format == "csv":
            export_data = [
                {
                    "id": memory.id,
                    "content": memory.content,
                    "category": memory.category,
                    "emotional_weight": memory.emotional_weight,
                    "trigger_topic": memory.trigger_topic or "",
                    "usage_nuance": memory.usage_nuance or "",
                    "importance": memory.importance,
                    "pinned": str(memory.pinned),
                    "usage_count": memory.usage_count,
                    "last_accessed_at": (
                        memory.last_accessed_at.isoformat() if memory.last_accessed_at else ""
                    ),
                    "created_at": memory.created_at.isoformat() if memory.created_at else "",
                    "updated_at": memory.updated_at.isoformat() if memory.updated_at else "",
                }
                for memory in memories
            ]
            return create_csv_response(data=export_data, filename_prefix="memories")

        return MemoryExportResponse(
            user_id=str(user.id),
            exported_at=datetime.now(UTC),
            total_memories=len(memories),
            memories=memories,
        )

    except Exception as e:
        logger.error(
            "memories_export_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_memory_store_error(
            operation="export",
            detail=APIMessages.failed_to_export_memories(),
        )


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List user memories",
    description="Get all memories for the current user with optional category filter.",
)
async def list_memories(
    category: Annotated[
        str | None,
        Query(description="Filter by category"),
    ] = None,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryListResponse:
    """List all memories for the current user."""
    try:
        repo = MemoryRepository(db)

        if category:
            filtered = await repo.get_by_category(user.id, category)
            all_memories = await repo.get_all_for_user(user.id, limit=200)
        else:
            filtered = await repo.get_all_for_user(user.id, limit=200)
            all_memories = filtered

        # Count by category across all memories
        by_category: dict[str, int] = {}
        for m in all_memories:
            cat = m.category or "personal"
            by_category[cat] = by_category.get(cat, 0) + 1

        now = datetime.now(UTC)
        config = _build_retention_config()
        items = [_memory_to_response(m, now, config) for m in filtered]

        logger.info(
            "memories_listed",
            user_id=str(user.id),
            total=len(items),
            filter_category=category,
        )

        return MemoryListResponse(
            items=items,
            total=len(items),
            by_category=by_category,
        )

    except Exception as e:
        logger.error(
            "memories_list_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_memory_store_error(
            operation="list",
            detail=APIMessages.failed_to_retrieve_memories(),
        )


# =============================================================================
# Memory Operations by ID (MUST be after static routes to avoid path collision)
# =============================================================================


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get memory by ID",
    description="Get a specific memory by its ID.",
)
async def get_memory(
    memory_id: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Get a specific memory by ID."""
    try:
        repo = MemoryRepository(db)
        memory = await repo.get_by_id_for_user(UUID(memory_id), user.id)

        if not memory:
            raise_memory_not_found(memory_id)

        return _memory_to_response(memory)

    except ResourceNotFoundError:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_get_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error=str(e),
        )
        raise_memory_store_error(
            operation="get",
            detail=APIMessages.failed_to_retrieve_memory(),
            memory_id=memory_id,
        )


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create memory",
    description="Create a new memory for the current user.",
)
async def create_memory(
    data: MemoryCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Create a new memory."""
    try:
        service = MemoryService(db)
        memory = await service.create_memory(
            user_id=user.id,
            content=data.content,
            category=data.category,
            emotional_weight=data.emotional_weight,
            trigger_topic=data.trigger_topic,
            usage_nuance=data.usage_nuance,
            importance=data.importance,
        )
        await db.commit()

        logger.info(
            "memory_created_api",
            user_id=str(user.id),
            memory_id=str(memory.id),
            category=data.category,
        )

        return _memory_to_response(memory)

    except Exception as e:
        logger.error(
            "memory_create_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_memory_store_error(
            operation="create",
            detail=APIMessages.failed_to_create_memory(),
        )


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Update memory",
    description="Partially update an existing memory.",
)
async def update_memory(
    memory_id: str,
    data: MemoryUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    """Update an existing memory."""
    try:
        repo = MemoryRepository(db)
        memory = await repo.get_by_id_for_user(UUID(memory_id), user.id)

        if not memory:
            raise_memory_not_found(memory_id)

        service = MemoryService(db)
        updated = await service.update_memory(
            memory=memory,
            content=data.content,
            category=data.category,
            emotional_weight=data.emotional_weight,
            trigger_topic=data.trigger_topic,
            usage_nuance=data.usage_nuance,
            importance=data.importance,
        )
        await db.commit()

        logger.info(
            "memory_updated_api",
            user_id=str(user.id),
            memory_id=memory_id,
            updated_fields=list(data.model_dump(exclude_unset=True).keys()),
        )

        return _memory_to_response(updated)

    except ResourceNotFoundError:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_update_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error=str(e),
        )
        raise_memory_store_error(
            operation="update",
            detail=APIMessages.failed_to_update_memory(),
            memory_id=memory_id,
        )


@router.patch(
    "/{memory_id}/pin",
    response_model=MemoryPinResponse,
    summary="Pin/unpin memory",
    description="Toggle the pinned state of a memory. Pinned memories are protected from automatic purge.",
)
async def toggle_pin_memory(
    memory_id: str,
    data: MemoryPinRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryPinResponse:
    """Toggle the pinned state of a memory."""
    try:
        repo = MemoryRepository(db)
        memory = await repo.get_by_id_for_user(UUID(memory_id), user.id)

        if not memory:
            raise_memory_not_found(memory_id)

        memory.pinned = data.pinned
        await repo.update(memory)
        await db.commit()

        logger.info(
            "memory_pin_toggled",
            user_id=str(user.id),
            memory_id=memory_id,
            pinned=data.pinned,
        )

        return MemoryPinResponse(id=str(memory.id), pinned=data.pinned)

    except ResourceNotFoundError:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_pin_toggle_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error=str(e),
        )
        raise_memory_store_error(
            operation="toggle_pin",
            detail=APIMessages.failed_to_toggle_pin(),
            memory_id=memory_id,
        )


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete memory",
    description="Delete a specific memory.",
)
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific memory."""
    try:
        repo = MemoryRepository(db)
        memory = await repo.get_by_id_for_user(UUID(memory_id), user.id)

        if not memory:
            raise_memory_not_found(memory_id)

        await repo.delete(memory)
        await db.commit()

        logger.info(
            "memory_deleted",
            user_id=str(user.id),
            memory_id=memory_id,
        )

    except ResourceNotFoundError:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_delete_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error=str(e),
        )
        raise_memory_store_error(
            operation="delete",
            detail=APIMessages.failed_to_delete_memory(),
            memory_id=memory_id,
        )


@router.delete(
    "",
    response_model=MemoryDeleteAllResponse,
    summary="Delete all memories (GDPR)",
    description="Delete all memories for the current user. GDPR right to erasure.",
)
async def delete_all_memories(
    preserve_pinned: Annotated[
        bool,
        Query(description="If True, pinned memories are preserved"),
    ] = False,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryDeleteAllResponse:
    """Delete all memories for the current user (GDPR erasure)."""
    try:
        repo = MemoryRepository(db)
        deleted_count = await repo.delete_all_for_user(user.id, preserve_pinned=preserve_pinned)
        await db.commit()

        # Count preserved for logging
        preserved_count = 0
        if preserve_pinned:
            preserved_count = await repo.get_count_for_user(user.id)

        logger.info(
            "memories_deleted_all",
            user_id=str(user.id),
            deleted_count=deleted_count,
            preserved_count=preserved_count,
            preserve_pinned=preserve_pinned,
        )

        return MemoryDeleteAllResponse(
            deleted_count=deleted_count,
            message=APIMessages.memories_deleted_successfully(
                deleted_count=deleted_count,
                preserved_count=preserved_count,
            ),
        )

    except Exception as e:
        logger.error(
            "memories_delete_all_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_memory_store_error(
            operation="delete_all",
            detail=APIMessages.failed_to_delete_all_memories(),
        )


@router.get(
    "/{memory_id}/provenance",
    response_model=ProvenanceResponse,
    summary="Why LIA thinks this",
    description=(
        "The bounded signals behind one memory, resolved LIVE. A reference "
        "whose conversation the reader has since deleted comes back as a "
        "tombstone: dated, sourceless and textless — a deletion elsewhere is "
        "never undone here."
    ),
)
async def get_memory_provenance(
    memory_id: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ProvenanceResponse:
    """The signals behind one memory.

    Args:
        memory_id: The memory being questioned.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The references, newest first, and the cap the trail is kept at.

    Raises:
        ResourceNotFoundError: Unknown memory, or one belonging to another
            account — the two answer identically, so the route cannot be used
            to probe for someone else's memories.
    """
    # Guarded like the four routes above it: a malformed identifier means "no
    # such memory", not "the server broke". Bare `UUID(...)` raised ValueError
    # and surfaced as a 500 — a different answer, from a different code path,
    # for the same client mistake.
    try:
        identifier = UUID(memory_id)
    except ValueError:
        raise_memory_not_found(memory_id)

    memory = await MemoryRepository(db).get_by_id_for_user(identifier, user.id)
    if not memory:
        raise_memory_not_found(memory_id)

    references = await ProvenanceRepository(db).resolve_for(user_id=user.id, memory_id=identifier)
    return ProvenanceResponse.from_references(references)
