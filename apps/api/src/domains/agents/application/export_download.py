"""Freeze the exact owned archive before approval; transfer remains a browser action."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_action import _authorize_export
from src.domains.agents.application.export_download_schemas import (
    ExportDownloadPatch,
    ExportDownloadRequest,
)
from src.domains.agents.application.export_download_spec import EXPORT_DOWNLOAD_OPERATION
from src.infrastructure.account_exports import get_account_exports


async def prepare_export_download(
    db: AsyncSession,
    actor_id: UUID,
    request: ExportDownloadRequest,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = ExportDownloadRequest.model_validate(request.model_dump())
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await _authorize_export(db, actor_id, origin)
    snapshot = await get_account_exports().archive_snapshot(db, actor_id, validated.job_id)
    await _authorize_export(db, actor_id, origin)
    if snapshot.expires_at <= datetime.now(UTC):
        raise ResourceConflictError("account_export", detail={"error_code": "STALE_STATE"})
    proposal = ExportDownloadPatch(archive_to_download=snapshot)
    draft = build_action_content(
        actor_id,
        EXPORT_DOWNLOAD_OPERATION,
        proposal,
        {"archive_to_download": None},
        proposal.model_dump(mode="json"),
        command_id=command_id,
    )
    return draft.model_copy(update={"expires_at": min(draft.expires_at, snapshot.expires_at)})
