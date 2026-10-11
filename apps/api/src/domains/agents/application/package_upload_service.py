"""One original-browser claim/settlement boundary for native skill and plugin packages."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.continuation_approval import claim_approved_waiting_interaction
from src.domains.agents.application.document_upload_execution import FormParser
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_download_service import _download_failure
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.secure_continuation import (
    finish_application_continuation,
    note_continuation_claim,
)
from src.domains.agents.application.state_changes import publish_preference_change
from src.domains.users.preference_cas import PreferenceWriteReceipt

PackageCheck = Callable[[AsyncSession], Awaitable[None]]


class PackageAcceptor(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        actor_id: UUID,
        draft: ApplicationActionDraftContent,
        receipt: PreferenceWriteReceipt,
        check: PackageCheck,
        *,
        file_confirmed: bool,
        parse_form: FormParser,
    ) -> dict[str, JsonValue]: ...


@dataclass(frozen=True)
class PackageUploadDefinition:
    spec: ApplicationOperationSpec
    field_name: Literal["skill_file_upload", "plugin_file_upload"]
    access: Callable[[AsyncSession, UUID], Awaitable[None]]
    accept: PackageAcceptor


async def serve_package_upload_command(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
    definition: PackageUploadDefinition,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> ApplicationExecutionOutcome:
    status = await read_command_status(db, actor_id, command_id, origin)
    if (
        status.operation_id != definition.spec.operation_id
        or status.phase != ApplicationPhase.WAITING
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        raise ResourceConflictError(definition.field_name, detail={"error_code": "STALE_STATE"})
    draft = ticket.command.draft
    receipt = PreferenceWriteReceipt()

    async def check(session: AsyncSession) -> None:
        await authorize_management_export(session, actor_id, origin)
        await definition.access(session, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    try:
        await note_continuation_claim(db, ticket)
        values = await definition.accept(
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
        failure = _download_failure(error, receipt)
        if receipt.committed and receipt.values is not None:
            failure = failure.model_copy(update={"values": receipt.values})
        await finish_application_continuation(ticket, failure)
        publish_preference_change(draft, receipt)
        raise
    await finish_application_continuation(ticket, outcome)
    publish_preference_change(draft, receipt)
    return outcome
