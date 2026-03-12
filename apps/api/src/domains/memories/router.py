"""
Memories router with FastAPI endpoints for user memory management.

Provides CRUD operations for long-term user memories with:
- Emotional profiling support
- Category-based organization
- GDPR compliance (export, delete all)
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from langgraph.store.base import Item

from src.core.exceptions import (
    ResourceNotFoundError,
    raise_memory_not_found,
    raise_memory_store_error,
)
from src.core.export_utils import create_csv_response
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.context.store import get_tool_context_store
from src.domains.agents.tools.memory_tools import get_memory_categories
from src.domains.auth.models import User
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
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.store.semantic_store import MemoryNamespace

logger = get_logger(__name__)

router = APIRouter(prefix="/memories", tags=["Memories"])


def _value_to_response(key: str, value: dict) -> MemoryResponse:
    """
    Convert key and value dict to MemoryResponse.

    Args:
        key: Memory identifier
        value: Memory data dictionary

    Returns:
        MemoryResponse with memory data
    """
    return MemoryResponse(
        id=key,
        content=value.get("content", ""),
        category=value.get("category", "personal"),
        emotional_weight=value.get("emotional_weight", 0),
        trigger_topic=value.get("trigger_topic", ""),
        usage_nuance=value.get("usage_nuance", ""),
        importance=value.get("importance", 0.7),
        created_at=value.get("created_at"),
        updated_at=value.get("updated_at"),
        # Phase 6: Purge tracking fields
        pinned=value.get("pinned", False),
        usage_count=value.get("usage_count", 0),
        last_accessed_at=value.get("last_accessed_at"),
    )


def _item_to_response(item: Item) -> MemoryResponse:
    """Convert store Item to MemoryResponse."""
    value = item.value if isinstance(item.value, dict) else {}
    return _value_to_response(item.key, value)


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
    description="Export all memories for the current user. Supports JSON and CSV formats. GDPR data portability.",
)
async def export_memories(
    export_format: Literal["json", "csv"] = Query(
        default="csv",
        alias="format",
        description="Export format (json or csv)",
    ),
    user: User = Depends(get_current_active_session),
) -> MemoryExportResponse | StreamingResponse:
    """Export all memories for GDPR data portability."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        results = await store.asearch(
            namespace.to_tuple(),
            query="",
            limit=1000,
        )

        memories = [_item_to_response(item) for item in results if isinstance(item.value, dict)]

        logger.info(
            "memories_exported",
            user_id=str(user.id),
            total=len(memories),
            export_format=export_format,
        )

        # Return CSV format
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

        # Return JSON format
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
) -> MemoryListResponse:
    """List all memories for the current user."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        # Get all memories
        results = await store.asearch(
            namespace.to_tuple(),
            query="",
            limit=200,
        )

        items = []
        by_category: dict[str, int] = {}

        for item in results:
            if not isinstance(item.value, dict):
                continue

            item_category = item.value.get("category", "personal")

            # Count by category
            by_category[item_category] = by_category.get(item_category, 0) + 1

            # Apply category filter if provided
            if category and item_category != category:
                continue

            items.append(_item_to_response(item))

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
) -> MemoryResponse:
    """Get a specific memory by ID."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        item = await store.aget(namespace.to_tuple(), memory_id)

        if not item:
            raise_memory_not_found(memory_id)

        return _item_to_response(item)

    except ResourceNotFoundError:
        raise
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
) -> MemoryResponse:
    """Create a new memory."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        value = {
            **data.model_dump(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        await store.aput(
            namespace.to_tuple(),
            key=memory_id,
            value=value,
        )

        logger.info(
            "memory_created",
            user_id=str(user.id),
            memory_id=memory_id,
            category=data.category,
        )

        return MemoryResponse(
            id=memory_id,
            **data.model_dump(),
            created_at=now,
            updated_at=now,
        )

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
) -> MemoryResponse:
    """Update an existing memory."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        # Get existing memory
        item = await store.aget(namespace.to_tuple(), memory_id)
        if not item:
            raise_memory_not_found(memory_id)

        # Merge updates (no date change on manual edit)
        existing_value = item.value if isinstance(item.value, dict) else {}
        update_data = data.model_dump(exclude_unset=True)

        updated_value = {
            **existing_value,
            **update_data,
        }

        await store.aput(
            namespace.to_tuple(),
            key=memory_id,
            value=updated_value,
        )

        logger.info(
            "memory_updated",
            user_id=str(user.id),
            memory_id=memory_id,
            updated_fields=list(update_data.keys()),
        )

        return _value_to_response(memory_id, updated_value)

    except ResourceNotFoundError:
        raise
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
) -> MemoryPinResponse:
    """Toggle the pinned state of a memory."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        # Get existing memory
        item = await store.aget(namespace.to_tuple(), memory_id)
        if not item:
            raise_memory_not_found(memory_id)

        # Update pinned state only (no date change)
        existing_value = item.value if isinstance(item.value, dict) else {}
        updated_value = {
            **existing_value,
            "pinned": data.pinned,
        }

        await store.aput(
            namespace.to_tuple(),
            key=memory_id,
            value=updated_value,
        )

        logger.info(
            "memory_pin_toggled",
            user_id=str(user.id),
            memory_id=memory_id,
            pinned=data.pinned,
        )

        return MemoryPinResponse(id=memory_id, pinned=data.pinned)

    except ResourceNotFoundError:
        raise
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
) -> None:
    """Delete a specific memory."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        # Check if exists
        item = await store.aget(namespace.to_tuple(), memory_id)
        if not item:
            raise_memory_not_found(memory_id)

        await store.adelete(namespace.to_tuple(), memory_id)

        logger.info(
            "memory_deleted",
            user_id=str(user.id),
            memory_id=memory_id,
        )

    except ResourceNotFoundError:
        raise
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
) -> MemoryDeleteAllResponse:
    """Delete all memories for the current user (GDPR erasure)."""
    try:
        store = await get_tool_context_store()
        namespace = MemoryNamespace(str(user.id))

        # Get all memories first to count
        results = await store.asearch(
            namespace.to_tuple(),
            query="",
            limit=1000,
        )

        deleted_count = 0
        preserved_count = 0
        for item in results:
            # Skip pinned memories if preserve_pinned is True
            if preserve_pinned and isinstance(item.value, dict) and item.value.get("pinned", False):
                preserved_count += 1
                continue

            try:
                await store.adelete(namespace.to_tuple(), item.key)
                deleted_count += 1
            except Exception as e:
                logger.warning(
                    "memory_delete_item_failed",
                    user_id=str(user.id),
                    memory_id=item.key,
                    error=str(e),
                )

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
