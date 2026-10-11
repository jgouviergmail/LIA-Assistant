"""Execute the finite secure family under the original approval, never replay a lost result."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError, RateLimitError, ResourceConflictError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.command_status import (
    ApplicationCommandStatus,
    read_command_status,
)
from src.domains.agents.application.continuation_approval import (
    ApprovedInteractionClaim,
    claim_approved_waiting_interaction,
)
from src.domains.agents.application.continuation_settlement import settle_continuation
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_action import execute_account_export_request
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.session_bulk_operations import (
    SESSION_FLEET_OPERATION,
    OtherSessionsRevokePatch,
)
from src.domains.agents.effects.decision_recorder import CANCELLATION_GRACE_ATTEMPTS
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.models import AgentEffect
from src.domains.auth.session_bulk_commands import revoke_owned_other_device_sessions
from src.domains.auth.session_commands import SessionRevocationCompletionUnknown
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_effects import (
    effect_claims_total,
    effect_ledger_failures_total,
    effect_outcomes_total,
)

logger = structlog.get_logger(__name__)


class ContinuationCompletionUnknown(RuntimeError):
    """The committed attempt may have run; observe status, never automatically retry it."""


class _CancelledSecureAttempt(asyncio.CancelledError):
    def __init__(self, outcome: ApplicationExecutionOutcome) -> None:
        super().__init__()
        self.outcome = outcome


async def note_continuation_claim(db: AsyncSession, ticket: ApprovedInteractionClaim) -> None:
    effect = await db.get(AgentEffect, ticket.effect_id)
    if effect is None or effect.user_id != ticket.command.draft.actor_id:
        raise AuthorizationError(detail={"error_code": "INVALID_APPROVAL"})
    effect_claims_total.labels(
        policy="draft", source=effect.source.value, execution_mode=effect.execution_mode
    ).inc()


async def _execute_fleet_revocation(
    db: AsyncSession,
    draft: ApplicationActionDraftContent,
    origin: ApplicationOrigin | None,
    receipt: PreferenceWriteReceipt,
) -> dict[str, JsonValue]:
    intent = OtherSessionsRevokePatch.model_validate(draft.intent)
    before = OtherSessionsRevokePatch.model_validate(draft.before)
    if (
        intent != before
        or draft.after != {"other_sessions_to_revoke": None}
        or draft.expected_digest != payload_digest(draft.before)
    ):
        raise ValueError("A secure action requires its exact approved selection")

    async def check() -> None:
        await require_application_tools(db)
        await load_actor(db, draft.actor_id)

    await check()
    removed = await revoke_owned_other_device_sessions(
        db,
        draft.actor_id,
        intent.other_sessions_to_revoke,
        origin,
        receipt,
        check=check,
        approved_until=draft.expires_at,
    )
    return {
        "revoked_sessions": removed,
        "approved_sessions": len(intent.other_sessions_to_revoke.sessions),
    }


async def _attempt_secure_action(
    db: AsyncSession, ticket: ApprovedInteractionClaim, origin: ApplicationOrigin | None
) -> ApplicationExecutionOutcome:
    receipt = PreferenceWriteReceipt()
    try:
        values = await _SECURE_ACTIONS[ticket.command.draft.operation_id](
            db, ticket.command.draft, origin, receipt
        )
        return ApplicationExecutionOutcome(
            success=True,
            phase=ApplicationPhase.COMMITTED,
            committed=receipt.committed,
            no_op=receipt.no_op,
            values=values,
        )
    except ResourceConflictError:
        return ApplicationExecutionOutcome(
            success=False, phase=ApplicationPhase.CONFLICT, error_code="STALE_STATE"
        )
    except asyncio.CancelledError:
        raise _CancelledSecureAttempt(
            ApplicationExecutionOutcome(
                success=False,
                phase=ApplicationPhase.FAILED,
                committed=receipt.committed,
                error_code="COMPLETION_UNKNOWN",
            )
        ) from None
    except SessionRevocationCompletionUnknown:
        code = "COMPLETION_UNKNOWN"
    except RateLimitError:
        code = "RATE_LIMIT_EXCEEDED"
    except AuthorizationError as exc:
        code = application_access_error_code(exc)
    except ValueError:
        code = "INVALID_INPUT"
    except Exception as exc:
        logger.warning(
            "application_continuation_failed",
            operation=ticket.command.draft.operation_id,
            exception_type=type(exc).__name__,
            committed=receipt.committed,
        )
        code = "EXECUTION_FAILED"
    return ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.FAILED,
        committed=receipt.committed,
        error_code="POST_COMMIT_FAILURE" if receipt.committed else code,
    )


async def resume_secure_application_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> ApplicationCommandStatus:
    status = await read_command_status(db, actor_id, command_id, origin)
    if status.operation_id not in _SECURE_ACTIONS:
        raise AuthorizationError(detail={"error_code": "INVALID_INPUT"})
    ticket = await claim_approved_waiting_interaction(db, actor_id, command_id, origin)
    if ticket is None:
        return await read_command_status(db, actor_id, command_id, origin)
    try:
        await note_continuation_claim(db, ticket)
        outcome = await _attempt_secure_action(db, ticket, origin)
    except _CancelledSecureAttempt as exc:
        await finish_application_continuation(ticket, exc.outcome)
        raise
    except asyncio.CancelledError:
        await finish_application_continuation(
            ticket,
            ApplicationExecutionOutcome(
                success=False, phase=ApplicationPhase.FAILED, error_code="COMPLETION_UNKNOWN"
            ),
        )
        raise
    await finish_application_continuation(ticket, outcome)
    return await read_command_status(db, actor_id, command_id, origin)


_SECURE_ACTIONS: dict[
    str,
    Callable[
        [
            AsyncSession,
            ApplicationActionDraftContent,
            ApplicationOrigin | None,
            PreferenceWriteReceipt,
        ],
        Awaitable[dict[str, JsonValue]],
    ],
] = {
    SESSION_FLEET_OPERATION.operation_id: _execute_fleet_revocation,
    "account_export.request": execute_account_export_request,
}


async def finish_application_continuation(
    ticket: ApprovedInteractionClaim, outcome: ApplicationExecutionOutcome
) -> None:
    async def write() -> None:
        # The write may outlive request cancellation. It owns its session;
        # the request must never close a session still used by this shielded task.
        async with get_db_context() as db:
            closed = await settle_continuation(db, ticket, outcome)
        if not closed:
            raise ContinuationCompletionUnknown()
        effect_outcomes_total.labels(
            policy="draft", status="succeeded" if outcome.success else "failed"
        ).inc()

    try:
        cancelled = await write_through_cancellation(
            write, attempts=CANCELLATION_GRACE_ATTEMPTS, label="application_continuation_settle"
        )
    except Exception:
        effect_ledger_failures_total.labels(operation="close").inc()
        raise ContinuationCompletionUnknown() from None
    if cancelled:
        raise asyncio.CancelledError()
