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

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    AuthorizationError,
    BaseAPIException,
    ResourceConflictError,
    ResourceNotFoundError,
    raise_invalid_input,
    raise_memory_not_found,
    raise_memory_store_error,
    raise_payload_too_large,
)
from src.core.i18n_api_messages import APIMessages
from src.core.management_export_file import prepare_management_export_file
from src.core.management_export_response import ManagementExportResponse
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.tools.memory_tools import get_memory_categories
from src.domains.memories.import_commands import import_memories
from src.domains.memories.import_file import MemoryImportFileError, parse_memory_import
from src.domains.memories.management_commands import (
    lock_active_owned_memory,
    lock_memory_actor,
    set_locked_memory_pin,
)
from src.domains.memories.management_embeddings import prepare_managed_embeddings
from src.domains.memories.management_export import MemoryCSVExportRecord, memory_export_rows
from src.domains.memories.read_models import build_retention_config as _build_retention_config
from src.domains.memories.read_models import memory_to_response as _memory_to_response
from src.domains.memories.repository import MemoryRepository
from src.domains.memories.schemas import (
    MemoryCategoriesResponse,
    MemoryCategoryInfo,
    MemoryCreate,
    MemoryDeleteAllResponse,
    MemoryImportResponse,
    MemoryListResponse,
    MemoryPinRequest,
    MemoryPinResponse,
    MemoryResponse,
    MemoryUpdate,
)
from src.domains.memories.service import MemoryService, embedding_texts
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/memories", tags=["Memories"])


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
) -> StreamingResponse:
    """Export all memories for GDPR data portability."""
    try:
        now = datetime.now(UTC)
        reader = await prepare_management_export_file(
            memory_export_rows(db, user.id, export_format, now),
            format=export_format,
            fieldnames=tuple(MemoryCSVExportRecord.model_fields),
            collection="memories",
            metadata={"user_id": str(user.id), "exported_at": now.isoformat()},
            count_key="total_memories",
            max_bytes=settings.account_export_max_bytes,
        )
        logger.info(
            "memories_exported",
            user_id=str(user.id),
            file_size_bytes=reader.file_size_bytes,
            export_format=export_format,
        )

        return ManagementExportResponse(reader, collection="memories", format=export_format)

    except Exception as e:
        logger.error(
            "memories_export_failed",
            user_id=str(user.id),
            error_type=type(e).__name__,
        )
        raise_memory_store_error(
            operation="export",
            detail=APIMessages.failed_to_export_memories(),
        )


#: Bytes read from an uploaded export at a time, so an oversized file is refused early.
_IMPORT_CHUNK_BYTES = 64 * 1024


async def _read_import_file(file: UploadFile) -> bytes:
    """Read an uploaded export, refusing it as soon as it passes the size it may have.

    Args:
        file: The uploaded file.

    Returns:
        The file's bytes.

    Raises:
        PayloadTooLargeError: The file is larger than one import reads.
    """
    limit_kb = settings.memory_import_max_file_kb
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_IMPORT_CHUNK_BYTES):
        size += len(chunk)
        if size > limit_kb * 1024:
            raise_payload_too_large(
                APIMessages.memory_import_file_too_large(limit_kb), limit_kb=limit_kb
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _refuse_import_file(refusal: MemoryImportFileError) -> NoReturn:
    """Answer a file refused whole with what refused it.

    Args:
        refusal: Why the file was refused.

    Raises:
        ValidationError: Always — the file holds too many memories, or is no export.
    """
    if refusal.code == "too_many" and refusal.found is not None and refusal.limit is not None:
        raise_invalid_input(
            APIMessages.memory_import_too_many(refusal.found, refusal.limit),
            found=refusal.found,
            limit=refusal.limit,
        )
    raise_invalid_input(APIMessages.memory_import_file_unreadable())


@router.post(
    "/import",
    response_model=MemoryImportResponse,
    summary="Import a memories export",
    description=(
        "Bring the memories of an export (the CSV or the JSON of GET /memories/export) "
        "into the account. A memory whose content the account already holds is left "
        "alone; an import writes everything new or nothing. Every count is exact."
    ),
)
async def import_memories_file(
    file: Annotated[UploadFile, File(description="A memories export, CSV or JSON")],
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MemoryImportResponse:
    """Import an export: read with nothing held, embedded with nothing held, then written."""
    # ADR-304: the authentication read ends here; the file, its parsing and the vectors
    # all happen with no transaction open.
    user_id = user.id
    await db.commit()
    content = await _read_import_file(file)
    try:
        parsed = await asyncio.to_thread(
            parse_memory_import, content, max_memories=settings.memory_import_max_memories
        )
    except MemoryImportFileError as refusal:
        _refuse_import_file(refusal)
    try:
        outcome = await import_memories(db, user_id, parsed)
    except BaseAPIException:
        raise
    except Exception as e:
        logger.error(
            "memories_import_failed",
            user_id=str(user_id),
            error_type=type(e).__name__,
        )
        raise_memory_store_error(
            operation="import",
            detail=APIMessages.failed_to_import_memories(),
        )
    return MemoryImportResponse(
        total=outcome.total,
        imported=outcome.imported,
        already_present=outcome.already_present,
        duplicates=outcome.duplicates,
        invalid=outcome.invalid,
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
            error_type=type(e).__name__,
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

    except BaseAPIException:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_get_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error_type=type(e).__name__,
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
    """Create a new memory: the vectors are computed with nothing held, then written."""
    try:
        # ADR-304: authentication read on this session; its connection goes back BEFORE
        # the provider is called, and the creation embeds before its first write.
        user_id = user.id
        await db.commit()
        prepared = await prepare_managed_embeddings(db, user_id, (data.content, data.trigger_topic))
        await lock_memory_actor(db, user_id)
        service = MemoryService(db, embedder=prepared.resolve)
        memory = await service.create_from_management(user_id, data)
        await db.commit()

        logger.info(
            "memory_created_api",
            user_id=str(user.id),
            memory_id=str(memory.id),
            category=data.category,
        )

        return _memory_to_response(memory)

    except BaseAPIException:
        raise
    except Exception as e:
        logger.error(
            "memory_create_failed",
            user_id=str(user.id),
            error_type=type(e).__name__,
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
    """Update an existing memory: read, embed with nothing held, then write."""
    try:
        repo = MemoryRepository(db)
        memory = await repo.get_by_id_for_user(UUID(memory_id), user.id)

        if not memory:
            raise_memory_not_found(memory_id)

        # ADR-304: the pooled connection goes back BEFORE the provider is called; the
        # edit is then written in a transaction of its own, with the vectors prepared.
        user_id = user.id
        texts = embedding_texts(memory, data.content, data.trigger_topic)
        await db.commit()
        prepared = await prepare_managed_embeddings(db, user_id, texts)
        memory = await lock_active_owned_memory(db, user_id, UUID(memory_id))
        if texts != embedding_texts(memory, data.content, data.trigger_topic):
            raise ResourceConflictError(
                resource_type="memory", detail={"error_code": "MEMORY_CHANGED"}
            )
        service = MemoryService(db, embedder=prepared.resolve)
        updated = await service.update_from_management(memory, data)
        await db.commit()

        logger.info(
            "memory_updated_api",
            user_id=str(user.id),
            memory_id=memory_id,
            updated_fields=list(data.model_dump(exclude_unset=True).keys()),
        )

        return _memory_to_response(updated)

    except BaseAPIException:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_update_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error_type=type(e).__name__,
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
        memory = await lock_active_owned_memory(db, user.id, UUID(memory_id))
        await set_locked_memory_pin(db, memory, data.pinned)
        await db.commit()

        logger.info(
            "memory_pin_toggled",
            user_id=str(user.id),
            memory_id=memory_id,
            pinned=data.pinned,
        )

        return MemoryPinResponse(id=str(memory.id), pinned=data.pinned)

    except AuthorizationError, ResourceNotFoundError:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_pin_toggle_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error_type=type(e).__name__,
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

    except BaseAPIException:
        raise
    except ValueError, AttributeError:
        raise_memory_not_found(memory_id)
    except Exception as e:
        logger.error(
            "memory_delete_failed",
            user_id=str(user.id),
            memory_id=memory_id,
            error_type=type(e).__name__,
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
            error_type=type(e).__name__,
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
