"""Initiate one exact archive request under its immutable original HITL receipt."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.continuation_failure import (
    application_continuation_failure as _download_failure,
)
from src.domains.agents.application.export_action import _authorize_export
from src.domains.agents.application.export_download_response import ExportDownloadResponse
from src.domains.agents.application.export_download_schemas import ExportDownloadPatch
from src.domains.agents.application.export_download_spec import EXPORT_DOWNLOAD_OPERATION
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import (
    ExportArchiveRead,
)
from src.infrastructure.account_exports import get_account_exports


async def serve_export_download_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> ExportDownloadResponse:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != EXPORT_DOWNLOAD_OPERATION.operation_id
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("account_export", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    reader: ExportArchiveRead | None = None
    try:
        await note_continuation_claim(db, ticket)
        draft = ticket.command.draft
        selected = ExportDownloadPatch.model_validate(draft.intent)
        if draft.before != {"archive_to_download": None} or draft.after != draft.intent:
            raise ValueError("A download requires its exact approved archive")

        async def check() -> None:
            if origin is None:
                raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
            await _authorize_export(db, actor_id, origin)

        reader = await get_account_exports().open_download(
            db,
            actor_id,
            selected.archive_to_download,
            receipt,
            check=check,
            approved_until=draft.expires_at,
        )
        # This confirms an initiated request, never a saved file or received bytes.
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=receipt.committed,
            values={
                "export_job_id": str(selected.archive_to_download.job_id),
                "download_requested": True,
                "save_confirmed": False,
            },
        )
        response = ExportDownloadResponse(reader)
    except BaseException as error:
        if reader is not None:
            await reader.close()
        await db.rollback()
        await finish_application_continuation(ticket, _download_failure(error, receipt))
        raise
    try:
        await finish_application_continuation(ticket, outcome)
    except BaseException:
        await reader.close()
        raise
    return response
