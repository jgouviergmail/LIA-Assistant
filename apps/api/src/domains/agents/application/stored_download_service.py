"""One claimed original-browser transfer for source documents and selected ZIP archives."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown
from src.infrastructure.file_transfer import LocalFileRead

Check = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class StoredDownload:
    reader: LocalFileRead
    filename: str
    content_type: str
    values: dict[str, JsonValue]


async def serve_stored_download_command(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
    *,
    operation: ApplicationOperationSpec,
    prepare: Callable[[ApplicationActionDraftContent, Check], Awaitable[StoredDownload]],
) -> StoredFileResponse:
    status = await read_command_status(db, actor_id, command_id, origin)
    if status.operation_id != operation.operation_id or status.phase != ApplicationPhase.WAITING:
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("download", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    transfer: StoredDownload | None = None
    try:
        await note_continuation_claim(db, ticket)
        draft = ticket.command.draft

        async def check() -> None:
            await authorize_management_export(db, actor_id, origin)
            for capability in operation.required_capabilities:
                await require_capability_fresh(db, capability)
            if datetime.now(UTC) >= draft.expires_at:
                raise CommandRejected("EXPIRED")

        await check()
        transfer = await prepare(draft, check)
        await check()
        response = StoredFileResponse(
            transfer.reader, filename=transfer.filename, content_type=transfer.content_type
        )
        try:
            await db.commit()
        except (Exception, asyncio.CancelledError) as exc:
            raise ExportDownloadCompletionUnknown() from exc
        receipt.committed = True
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values={**transfer.values, "download_requested": True, "save_confirmed": False},
        )
    except BaseException as error:
        if transfer is not None:
            await transfer.reader.close()
        await db.rollback()
        await finish_application_continuation(ticket, _download_failure(error, receipt))
        raise
    try:
        await finish_application_continuation(ticket, outcome)
    except BaseException:
        await transfer.reader.close()
        raise
    return response
