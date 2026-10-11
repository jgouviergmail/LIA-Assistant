"""Mutable command expiry; settled effect receipts remain immutable handoff facts."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase


async def expire_waiting_command(
    db: AsyncSession, command: ApplicationCommand, *, now: datetime | None = None
) -> bool:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Command expiry requires an aware timestamp")
    if command.phase != ApplicationPhase.WAITING or command.expires_at > current:
        return False
    encrypted = command.result_encrypted
    if encrypted is None:
        raise ValueError("A waiting command requires its durable interaction receipt")
    waiting = ApplicationExecutionOutcome.model_validate_json(decrypt_data(encrypted))
    interaction = waiting.interaction
    if interaction is None or interaction.interaction_id != command.id:
        raise ValueError("A waiting receipt must identify its command")
    expired = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.EXPIRED,
        committed=waiting.committed,
        values=waiting.values,
        error_code="INTERACTION_EXPIRED" if interaction.kind == "secure" else "COMPLETION_UNKNOWN",
    )
    changed = await db.scalar(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.id == command.id,
            ApplicationCommand.actor_id == command.actor_id,
            ApplicationCommand.phase == ApplicationPhase.WAITING,
            ApplicationCommand.expires_at <= current,
            ApplicationCommand.result_encrypted == encrypted,
        )
        .values(
            phase=ApplicationPhase.EXPIRED, result_encrypted=encrypt_data(expired.model_dump_json())
        )
        .returning(ApplicationCommand.id)
    )
    await db.commit()
    return changed is not None
