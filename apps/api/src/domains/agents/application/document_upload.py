"""Freeze public destination, source constraints and whole-row private comparison before picking."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadPatch,
    DocumentUploadSelection,
)
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.space_update import _source_row
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.ui_queries import owned_space


async def read_document_upload_selection(
    db: AsyncSession, actor_id: UUID, request: DocumentUploadInput
) -> DocumentUploadSelection:
    space = await owned_space(db, actor_id, request.space_id)
    count = int(
        await db.scalar(select(func.count(RAGDocument.id)).where(RAGDocument.space_id == space.id))
        or 0
    )
    if count >= settings.rag_spaces_max_docs_per_space:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return DocumentUploadSelection(
        space=SpaceUpdateTarget.model_validate(space),
        document_count=count,
        max_documents=settings.rag_spaces_max_docs_per_space,
        max_file_size_bytes=settings.rag_spaces_max_file_size_mb * 1024 * 1024,
        allowed_content_types=tuple(
            value.strip() for value in settings.rag_spaces_allowed_types.split(",") if value.strip()
        ),
        state_digest=payload_digest(await _source_row(db, actor_id, space.id)),
    )


async def prepare_document_upload(
    db: AsyncSession,
    actor_id: UUID,
    request: DocumentUploadInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = DocumentUploadInput.model_validate(request.model_dump())
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    selected = await read_document_upload_selection(db, actor_id, request)
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    return build_action_content(
        actor_id,
        DOCUMENT_UPLOAD_OPERATION,
        DocumentUploadPatch(document_to_upload=selected),
        {"document_to_upload": None},
        {"document_to_upload": selected.public_scope()},
        command_id=command_id,
    )
