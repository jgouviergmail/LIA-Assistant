"""Single-use original-browser upload under the original notarized HITL approval."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.document_upload_execution import (
    FormParser,
    accept_document_upload,
)
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    ContinuationCompletionUnknown,
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.processing import process_document
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.metrics_rag_spaces import rag_documents_total_count


async def launch_uploaded_document(db: AsyncSession, actor_id: UUID, document_id: UUID) -> None:
    document = await db.scalar(
        select(RAGDocument).where(RAGDocument.id == document_id, RAGDocument.user_id == actor_id)
    )
    if document is None:
        return  # A subsequent user deletion wins; no invented work.
    space_id, filename = document.space_id, document.filename
    original_filename, content_type = document.original_filename, document.content_type
    await db.commit()  # A provider-bound job never borrows this read transaction.
    safe_fire_and_forget(
        process_document(
            document_id=document_id,
            space_id=space_id,
            user_id=actor_id,
            filename=filename,
            original_filename=original_filename,
            content_type=content_type,
            durable_upload=True,
        ),
        name=f"rag_process_{document_id}",
    )


async def serve_document_upload_command(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> ApplicationExecutionOutcome:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != DOCUMENT_UPLOAD_OPERATION.operation_id
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError("document_upload", detail={"error_code": "STALE_STATE"})
    receipt = PreferenceWriteReceipt()
    draft = ticket.command.draft

    async def check() -> None:
        await authorize_management_export(db, actor_id, origin)
        await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    try:
        await note_continuation_claim(db, ticket)
        values = await accept_document_upload(
            db,
            actor_id,
            draft,
            receipt,
            check,
            file_confirmed=file_confirmed,
            parse_form=parse_form,
        )
        outcome = ApplicationExecutionOutcome(
            success=True, phase=ApplicationPhase.COMMITTED, committed=True, values=values
        )
    except BaseException as error:
        await db.rollback()
        failure = (
            CommandRejected("COMPLETION_UNKNOWN")
            if isinstance(error, ContinuationCompletionUnknown)
            else error
        )
        await finish_application_continuation(ticket, _download_failure(failure, receipt))
        publish_preference_change(draft, receipt)
        raise
    rag_documents_total_count.labels(status="pending").inc()
    await finish_application_continuation(ticket, outcome)
    publish_preference_change(draft, receipt)
    await launch_uploaded_document(db, actor_id, command_id)
    return outcome
