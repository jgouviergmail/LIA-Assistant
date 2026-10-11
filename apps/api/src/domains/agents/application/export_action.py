"""Exact full-account export intent, executed only through secure continuation."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.exceptions import ValidationError as ApplicationValidationError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_exports import get_account_exports


class AccountExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account_export: Literal[True] = True


EXPORT_REQUEST_OPERATION = ApplicationOperationSpec(
    operation_id="account_export.request",
    tool_name="request_lia_account_export_tool",
    sections=("security-export",),
    input_model=AccountExportRequest,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.SECURE_HANDOFF,
)


async def prepare_account_export(
    db: AsyncSession,
    actor_id: UUID,
    *,
    origin: ApplicationOrigin | None,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    await _authorize_export(db, actor_id, origin)
    if await get_account_exports().has_active(db, actor_id):
        raise AuthorizationError(detail={"error_code": "CONSTRAINT_VIOLATION"})
    await _authorize_export(db, actor_id, origin)
    return build_action_content(
        actor_id,
        EXPORT_REQUEST_OPERATION,
        AccountExportRequest(account_export=True),
        {"account_export": False},
        {"account_export": True},
        command_id=command_id,
    )


async def _authorize_export(db: AsyncSession, actor_id: UUID, origin: ApplicationOrigin) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    if not settings.account_export_enabled:
        raise AuthorizationError(detail={"error_code": "FEATURE_DISABLED"})


async def execute_account_export_request(
    db: AsyncSession,
    draft: ApplicationActionDraftContent,
    origin: ApplicationOrigin | None,
    receipt: PreferenceWriteReceipt,
) -> dict[str, JsonValue]:
    AccountExportRequest.model_validate(draft.intent)
    if draft.before != {"account_export": False} or draft.after != {"account_export": True}:
        raise ValueError("An export requires exact full-account approval")

    async def check() -> None:
        await require_application_tools(db)
        await load_actor(db, draft.actor_id)

    try:
        job = await get_account_exports().request(
            db,
            draft.actor_id,
            draft.command_id,
            origin,
            receipt,
            check=check,
            approved_until=draft.expires_at,
        )
    except ApplicationValidationError:
        raise ResourceConflictError(
            "account export", detail={"error_code": "STALE_STATE"}
        ) from None
    return {"export_job_id": str(job.id), "export_status": job.status}
