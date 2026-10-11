"""One exact HITL continuation prepares and transfers a transient complete export."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing
from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.management_export_file import prepare_management_export_file
from src.core.management_export_response import ManagementExportResponse
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.interest_creation import interest_creation_fence
from src.domains.agents.application.management_export import (
    authorize_management_export,
)
from src.domains.agents.application.management_export_schemas import (
    ManagementExportPatch,
    ManagementExportSnapshot,
)
from src.domains.agents.application.management_export_sources import (
    MANAGEMENT_EXPORT_SOURCES,
    ManagementExportSource,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.effects.digest import payload_digest
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown


async def _confirmed_export_rows(
    db: AsyncSession,
    actor_id: UUID,
    selected: ManagementExportSnapshot,
    source: ManagementExportSource,
    metadata: Mapping[str, object],
) -> AsyncGenerator[Mapping[str, object]]:
    count, digest = 0, sha256(source.digest_prefix(selected.format))
    if source.metadata is not None:
        digest.update(bytes.fromhex(payload_digest(metadata)))
    async with aclosing(
        source.rows(db, actor_id, selected.format, selected.observed_at, True)
    ) as records:
        async for record in records:
            count += 1
            public = record
            digest.update(bytes.fromhex(payload_digest(public)))
            yield public
    if (count, digest.hexdigest()) != (selected.selected_count, selected.selection_digest):
        raise ResourceConflictError(source.collection, detail={"error_code": "STALE_STATE"})


async def serve_management_export_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> ManagementExportResponse:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id not in MANAGEMENT_EXPORT_SOURCES
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    source = MANAGEMENT_EXPORT_SOURCES[status.operation_id]
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError(source.collection, detail={"error_code": "STALE_STATE"})
    receipt, reader = PreferenceWriteReceipt(), None
    try:
        await note_continuation_claim(db, ticket)
        draft = ticket.command.draft
        selected = ManagementExportPatch.model_validate(draft.intent).management_export
        if draft.before != {"management_export": None} or draft.after != draft.intent:
            raise ValueError("An export requires its exact approved source scope")
        await interest_creation_fence(db, actor_id, draft)
        await authorize_management_export(db, actor_id, origin)
        await source.require_available(db)
        await source.lock_actor(db, actor_id)
        await interest_creation_fence(db, actor_id, draft)
        metadata = await source.export_metadata(
            db, actor_id, selected.format, selected.observed_at, selected.selected_count
        )
        reader = await prepare_management_export_file(
            _confirmed_export_rows(db, actor_id, selected, source, metadata),
            format=selected.format,
            fieldnames=source.csv_fields,
            collection=source.json_collection or source.collection,
            metadata=metadata,
            max_bytes=settings.account_export_max_bytes,
        )
        await authorize_management_export(db, actor_id, origin)
        await source.require_available(db)
        await interest_creation_fence(db, actor_id, draft)
        try:
            await db.commit()
        except SQLAlchemyError as exc:
            raise ExportDownloadCompletionUnknown() from exc
        receipt.committed = True
        response = ManagementExportResponse(
            reader, collection=source.collection, format=selected.format
        )
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=True,
            values={
                "download_requested": True,
                "save_confirmed": False,
                "exported_count": selected.selected_count,
                "format": selected.format,
            },
        )
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
