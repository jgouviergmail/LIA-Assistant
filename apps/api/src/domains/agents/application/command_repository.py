"""Owner-conditioned command reads, canonical checks and fenced completion."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_origin_binding import (
    capture_command_origin,
    command_has_device_binding,
    require_command_origin,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.effects.digest import draft_digest


async def save_command(
    db: AsyncSession,
    content: ApplicationActionDraftContent,
    draft_id: str,
    *,
    origin: ApplicationOrigin | None = None,
    bind_device: bool = False,
) -> None:
    db.add(
        ApplicationCommand(
            id=content.command_id,
            actor_id=content.actor_id,
            draft_id=draft_id,
            operation_id=content.operation_id,
            content_digest=draft_digest(content.model_dump(mode="json")),
            content_encrypted=encrypt_data(content.model_dump_json()),
            expires_at=content.expires_at,
            phase=ApplicationPhase.PENDING,
            origin_binding_encrypted=await capture_command_origin(
                content, origin, bind_device=bind_device
            ),
        )
    )
    await db.flush()


async def get_command(
    db: AsyncSession, command_id: UUID, actor_id: UUID, *, lock: bool = False
) -> ApplicationCommand | None:
    query = (
        select(ApplicationCommand)
        .where(ApplicationCommand.id == command_id, ApplicationCommand.actor_id == actor_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    command: ApplicationCommand | None = await db.scalar(query)
    return command


def matches_command(
    command: ApplicationCommand, content: ApplicationActionDraftContent, draft_id: str
) -> bool:
    canonical = content.model_dump(mode="json")
    try:
        stored = ApplicationActionDraftContent.model_validate_json(
            decrypt_data(command.content_encrypted)
        )
    except ValueError:
        return False
    return (
        command.actor_id == content.actor_id
        and command.id == content.command_id
        and command.draft_id == draft_id
        and command.operation_id == content.operation_id
        and command.content_digest == draft_digest(canonical)
        and stored == content
    )


async def claim_command(db: AsyncSession, command_id: UUID, actor_id: UUID) -> UUID | None:
    token = uuid4()
    claimed: UUID | None = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == command_id,
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase == ApplicationPhase.PENDING,
            ApplicationCommand.expires_at > datetime.now(UTC),
        )
        .values(phase=ApplicationPhase.CLAIMED, claim_token=token)
        .returning(ApplicationCommand.claim_token)
    )
    await db.commit()
    return claimed


async def cancel_command(db: AsyncSession, draft_id: str, actor_id: UUID) -> bool:
    cancelled: UUID | None = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.draft_id == draft_id,
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase == ApplicationPhase.PENDING,
        )
        .values(phase=ApplicationPhase.CANCELLED)
        .returning(ApplicationCommand.id)
    )
    if cancelled is None:
        cancelled = await db.scalar(
            select(ApplicationCommand.id).where(
                ApplicationCommand.draft_id == draft_id,
                ApplicationCommand.actor_id == actor_id,
                ApplicationCommand.phase == ApplicationPhase.CANCELLED,
            )
        )
    await db.commit()
    return cancelled is not None


async def close_command(
    db: AsyncSession,
    command_id: UUID,
    actor_id: UUID,
    token: UUID,
    outcome: ApplicationExecutionOutcome,
    *,
    commit: bool = True,
) -> bool:
    interaction = outcome.interaction
    if interaction is not None:
        if interaction.interaction_id != command_id or interaction.expires_at <= datetime.now(UTC):
            return False
        return await _close_waiting_command(db, command_id, actor_id, token, outcome, commit=commit)
    closed: UUID | None = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == command_id,
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase.in_((ApplicationPhase.CLAIMED, ApplicationPhase.RESUMING)),
            ApplicationCommand.claim_token == token,
        )
        .values(phase=outcome.phase, result_encrypted=encrypt_data(outcome.model_dump_json()))
        .returning(ApplicationCommand.id)
    )
    if commit:
        await db.commit()
    return closed is not None


async def _close_waiting_command(
    db: AsyncSession,
    command_id: UUID,
    actor_id: UUID,
    token: UUID,
    outcome: ApplicationExecutionOutcome,
    *,
    commit: bool = True,
) -> bool:
    interaction = outcome.interaction
    if interaction is None:
        return False
    closed: UUID | None = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == command_id,
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase == ApplicationPhase.CLAIMED,
            ApplicationCommand.claim_token == token,
            ApplicationCommand.expires_at >= interaction.expires_at,
        )
        .values(
            phase=ApplicationPhase.WAITING,
            expires_at=interaction.expires_at,
            result_encrypted=encrypt_data(outcome.model_dump_json()),
        )
        .returning(ApplicationCommand.id)
    )
    if commit:
        await db.commit()
    return closed is not None


async def replace_pending_command(
    db: AsyncSession,
    original: ApplicationActionDraftContent,
    revised: ApplicationActionDraftContent,
    *,
    origin: ApplicationOrigin | None = None,
) -> bool:
    if (original.command_id, original.actor_id, original.operation_id) != (
        revised.command_id,
        revised.actor_id,
        revised.operation_id,
    ):
        raise ValueError("An edit cannot change command identity or ownership")
    current = await get_command(db, original.command_id, original.actor_id)
    if current is None:
        return False
    binding_before = current.origin_binding_encrypted
    binding_after: str | None = None
    if binding_before is not None:
        await require_command_origin(current, origin)
        binding_after = await capture_command_origin(
            revised, origin, bind_device=command_has_device_binding(current)
        )
    changed: UUID | None = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == original.command_id,
            ApplicationCommand.actor_id == original.actor_id,
            ApplicationCommand.phase == ApplicationPhase.PENDING,
            ApplicationCommand.expires_at > datetime.now(UTC),
            ApplicationCommand.content_digest == draft_digest(original.model_dump(mode="json")),
            ApplicationCommand.origin_binding_encrypted == binding_before,
        )
        .values(
            content_digest=draft_digest(revised.model_dump(mode="json")),
            content_encrypted=encrypt_data(revised.model_dump_json()),
            expires_at=revised.expires_at,
            origin_binding_encrypted=binding_after,
        )
        .returning(ApplicationCommand.id)
    )
    await db.commit()
    return changed is not None
