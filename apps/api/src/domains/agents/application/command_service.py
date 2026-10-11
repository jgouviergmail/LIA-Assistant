"""Current authority and canonical command validation before claim or replay."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.command_waiting import expire_waiting_command
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.draft_approval import valid_draft_approval
from src.domains.agents.effects.scope import current_scope
from src.domains.feature_switches.guard import require_capability_fresh
from src.infrastructure.database.session import get_db_context


class CommandRejected(ValueError):
    """A finite refusal code, never raw payloads or dependency diagnostics."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _current_operation(draft: ApplicationActionDraftContent) -> ApplicationOperationSpec:
    """Edits and execution share the same catalogue, canonical intent and expiry fence."""
    try:
        spec = APPLICATION_OPERATIONS.get(draft.operation_id)
    except KeyError as exc:
        raise CommandRejected("UNKNOWN_OPERATION") from exc
    if spec.kind not in {OperationKind.ACTION, OperationKind.SECURE_HANDOFF, OperationKind.DEVICE}:
        raise CommandRejected("INVALID_INPUT")
    if draft.schema_version != spec.version or draft.schema_fingerprint != payload_digest(
        spec.input_model.model_json_schema()
    ):
        raise CommandRejected("SCHEMA_CHANGED")
    parsed = spec.input_model.model_validate(draft.intent)
    if payload_digest(parsed.model_dump(mode="json", exclude_unset=True)) != payload_digest(
        draft.intent
    ):
        raise CommandRejected("SCHEMA_CHANGED")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    return spec


async def validate_execution(
    content: dict[str, object], actor_id: UUID
) -> ApplicationActionDraftContent:
    scope = current_scope()
    if not valid_draft_approval(scope, content):
        raise CommandRejected("CONFIRMATION_MISSING")
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    draft = ApplicationActionDraftContent.model_validate(content)
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    spec = _current_operation(draft)
    async with get_db_context() as db:
        await require_application_tools(db)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)
        await load_actor(db, actor_id, administrative=spec.administrative)
        command = await get_command(db, draft.command_id, actor_id)
        if (
            command is None
            or scope is None
            or not matches_command(command, draft, scope.approval_ref or "")
        ):
            raise CommandRejected("INVALID_DRAFT")
        await _validate_bound_origin(db, command, spec, context.application_origin)
        try:
            await expire_waiting_command(db, command)
        except ValueError:
            raise CommandRejected("INVALID_DRAFT") from None
        if command.phase in {ApplicationPhase.CANCELLED, ApplicationPhase.EXPIRED}:
            raise CommandRejected(command.phase.value.upper())
    return draft


async def validate_pending_proposal(content: dict[str, object], draft_id: str | None) -> None:
    """A pending draft is sensitive state too; check it before another model reads it."""
    context = runtime_context_if_running()
    if context is None:
        raise CommandRejected("FORBIDDEN")
    try:
        draft = ApplicationActionDraftContent.model_validate(content)
    except ValueError:
        raise CommandRejected("INVALID_INPUT") from None
    if draft.actor_id != context.user_id or draft_id is None:
        raise CommandRejected("FORBIDDEN")
    spec = _current_operation(draft)
    async with get_db_context() as db:
        await require_application_tools(db)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)
        await load_actor(db, context.user_id, administrative=spec.administrative)
        row = await get_command(db, draft.command_id, context.user_id)
        if (
            row is None
            or row.phase != ApplicationPhase.PENDING
            or not matches_command(row, draft, draft_id)
        ):
            raise CommandRejected("INVALID_DRAFT")
        await _validate_bound_origin(db, row, spec, context.application_origin)


async def _validate_bound_origin(
    db: AsyncSession,
    command: ApplicationCommand,
    spec: ApplicationOperationSpec,
    origin: ApplicationOrigin | None,
) -> None:
    if command.origin_binding_encrypted is None:
        if spec.interaction_kind is not None:
            raise CommandRejected("SESSION_UNAVAILABLE")
        return
    await require_command_origin(command, origin, require_device=spec.addressed_device)
    # A live transport lookup is asynchronous; stored authority cannot survive it.
    await require_application_tools(db)
    for capability in spec.required_capabilities:
        await require_capability_fresh(db, capability)
    await load_actor(db, command.actor_id, administrative=spec.administrative)
