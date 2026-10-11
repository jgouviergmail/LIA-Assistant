"""Prepare metadata only; ZIP generation and transfer wait for original-browser approval."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.document_archive_schemas import (
    DocumentArchiveInput,
    DocumentArchivePatch,
)
from src.domains.agents.application.document_archive_spec import DOCUMENT_ARCHIVE_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.document_archives import read_owned_archive_snapshot


async def prepare_document_archive(
    db: AsyncSession,
    actor_id: UUID,
    request: DocumentArchiveInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = DocumentArchiveInput.model_validate(request.model_dump())
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    snapshot = await read_owned_archive_snapshot(
        db, actor_id, selected.space_id, selected.document_ids
    )
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    return build_action_content(
        actor_id,
        DOCUMENT_ARCHIVE_OPERATION,
        DocumentArchivePatch(archive_to_download=snapshot),
        {"archive_to_download": None},
        {"archive_to_download": snapshot.public_scope()},
        command_id=command_id,
    )
