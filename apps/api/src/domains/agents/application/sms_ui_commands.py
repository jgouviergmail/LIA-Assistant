"""Closed, browser-bound SMS proposals and explicit once-only confirmations.

This HTTP adapter shares native drafts, source writers and the effect ledger.
Only the authenticated confirmation endpoint may establish its approval scope.
A lost acknowledgement never makes a token secret replayable.
"""

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import (
    cancel_command,
    claim_command,
    close_command,
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.sms_actions import (
    SmsManagementAudience,
    authorize_sms_management,
    prepare_sms_action,
)
from src.domains.agents.application.sms_execution import execute_sms_action
from src.domains.agents.effects.digest import args_digest, draft_digest
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.schemas import IngestionTokenSecret
from src.domains.users.preference_cas import PreferenceWriteReceipt


@dataclass(frozen=True, slots=True)
class SmsUiEffect:
    id: UUID
    token: UUID


class SmsUiProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_id: UUID
    operation_id: str
    content_digest: str
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]
    expires_at: datetime


class SmsUiCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: ApplicationExecutionOutcome
    secret: IngestionTokenSecret | None = None


def _conflict(code: str = "STALE_STATE") -> ResourceConflictError:
    return ResourceConflictError("sms_command", detail={"error_code": code})


async def propose_sms_ui(
    db: AsyncSession,
    owner: UUID,
    operation: str,
    payload: dict[str, JsonValue],
    origin: ApplicationOrigin,
) -> SmsUiProposal:
    await authorize_sms_management(
        db, owner, origin, browser=True, audience=SmsManagementAudience.SETTINGS
    )
    draft = await prepare_sms_action(
        db, owner, operation, payload, origin=origin, audience=SmsManagementAudience.SETTINGS
    )
    await save_command(db, draft, f"ui:sms:{uuid4()}", origin=origin)
    await db.commit()
    return SmsUiProposal(
        command_id=draft.command_id,
        operation_id=draft.operation_id,
        content_digest=draft_digest(draft.model_dump(mode="json")),
        before=draft.before,
        after=draft.after,
        expires_at=draft.expires_at,
    )


async def _claim_ui(
    db: AsyncSession,
    owner: UUID,
    command_id: UUID,
    digest: str,
    origin: ApplicationOrigin,
) -> tuple[ApplicationActionDraftContent, UUID, SmsUiEffect, EffectScope]:
    # The owner fence precedes every command/effect/source lock, including races.
    await lock_active_owner(db, owner)
    command = await get_command(db, command_id, owner, lock=True)
    if command is None or not command.draft_id.startswith("ui:sms:"):
        raise _conflict()
    await require_command_origin(command, origin)
    await authorize_sms_management(
        db, owner, origin, browser=True, audience=SmsManagementAudience.SETTINGS
    )
    if not hmac.compare_digest(command.content_digest, digest):
        raise _conflict()
    if command.phase != ApplicationPhase.PENDING or command.expires_at <= datetime.now(UTC):
        raise _conflict(
            "COMPLETION_UNKNOWN" if command.phase == ApplicationPhase.CLAIMED else "STALE_STATE"
        )
    try:
        draft = ApplicationActionDraftContent.model_validate_json(
            decrypt_data(command.content_encrypted)
        )
    except ValueError:
        raise _conflict("INVALID_DRAFT") from None
    if not matches_command(command, draft, command.draft_id):
        raise _conflict("INVALID_DRAFT")
    scope = EffectScope(
        run_id=str(command_id),
        idempotency_key=f"draft:{command.draft_id}",
        approved=True,
        approval_kind="draft_critique",
        approval_ref=command.draft_id,
        draft_digest=command.content_digest,
    )
    effect = await EffectLedgerRepository(db).claim(
        ClaimRequest(
            user_id=owner,
            thread_id=str(owner),
            run_id=scope.run_id,
            source="user",
            execution_mode="direct",
            tool_name="draft:application_action",
            mutation_policy="draft",
            idempotency_key=scope.idempotency_key,
            args_digest=args_digest(
                "draft:application_action", {"draft": draft.model_dump(mode="json")}
            ),
            approval_kind=scope.approval_kind,
            approval_ref=scope.approval_ref,
            draft_digest=scope.draft_digest,
        )
    )
    if not effect.claimed or effect.claim_token is None:
        raise _conflict("COMPLETION_UNKNOWN")
    ticket = SmsUiEffect(effect.effect.id, effect.claim_token)
    token = await claim_command(db, command_id, owner)
    if token is None:
        raise _conflict("COMPLETION_UNKNOWN")
    return draft, token, ticket, scope


async def _finish_ui(
    db: AsyncSession,
    draft: ApplicationActionDraftContent,
    token: UUID,
    effect: SmsUiEffect,
    outcome: ApplicationExecutionOutcome,
) -> None:
    repo = EffectLedgerRepository(db)
    if outcome.success:
        closed = await repo.close_success(
            effect.id, effect.token, result_payload=outcome.model_dump(mode="json")
        )
    else:
        closed = await repo.close_abandoned(
            effect.id, effect.token, error_code=outcome.error_code or "COMPLETION_UNKNOWN"
        )
    if not closed or not await close_command(
        db, draft.command_id, draft.actor_id, token, outcome, commit=False
    ):
        await db.rollback()
        raise _conflict("COMPLETION_UNKNOWN")
    await db.commit()


async def confirm_sms_ui(
    db: AsyncSession,
    owner: UUID,
    command_id: UUID,
    digest: str,
    origin: ApplicationOrigin,
) -> SmsUiCompletion:
    draft, token, effect, scope = await _claim_ui(db, owner, command_id, digest, origin)
    receipt = PreferenceWriteReceipt()
    try:
        with effect_scope(scope):
            secret = await execute_sms_action(
                db, owner, draft, receipt, origin=origin, audience=SmsManagementAudience.SETTINGS
            )
        outcome = ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=receipt.committed,
            no_op=receipt.no_op,
            values=receipt.values or {},
        )
    except (CommandRejected, BaseAPIException) as exc:
        await db.rollback()
        code = exc.code if isinstance(exc, CommandRejected) else "AUTHORITY_OR_STATE_CHANGED"
        outcome = ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.FAILED,
            committed=receipt.committed,
            error_code=code,
            values=receipt.values or {},
        )
        await _finish_ui(db, draft, token, effect, outcome)
        raise
    await _finish_ui(db, draft, token, effect, outcome)
    # A session withdrawn while settlement awaited cannot receive a new secret.
    await authorize_sms_management(
        db, owner, origin, browser=True, audience=SmsManagementAudience.SETTINGS
    )
    return SmsUiCompletion(outcome=outcome, secret=secret)


async def cancel_sms_ui(
    db: AsyncSession,
    owner: UUID,
    command_id: UUID,
    origin: ApplicationOrigin,
) -> None:
    await lock_active_owner(db, owner)
    command = await get_command(db, command_id, owner, lock=True)
    if command is None or not command.draft_id.startswith("ui:sms:"):
        raise _conflict()
    await require_command_origin(command, origin, allow_expired=True)
    await authorize_sms_management(
        db, owner, origin, browser=True, audience=SmsManagementAudience.SETTINGS
    )
    if not await cancel_command(db, command.draft_id, owner):
        raise _conflict("COMPLETION_UNKNOWN")
