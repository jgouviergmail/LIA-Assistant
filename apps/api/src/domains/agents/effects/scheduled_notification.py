"""Strict, transaction-owned claims for immediate ingestion notifications."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.digest import args_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest


@dataclass(frozen=True, slots=True)
class NotificationEffect:
    id: UUID
    token: UUID


async def claim_notification(
    db: AsyncSession,
    *,
    owner: UUID,
    occurrence: UUID,
    delivery: UUID,
    attempt: int,
    retry_of: UUID | None,
) -> NotificationEffect | None:
    result = await EffectLedgerRepository(db).claim(
        ClaimRequest(
            user_id=owner,
            thread_id=str(owner),
            run_id=str(occurrence),
            source="scheduled",
            execution_mode="direct",
            tool_name="sms_notification",
            mutation_policy="reversible",
            idempotency_key=f"sms:{delivery}:{attempt}",
            args_digest=args_digest(
                "sms_notification", {"occurrence": str(occurrence), "delivery": str(delivery)}
            ),
            retry_of=retry_of,
            label={"i18n_key": "effects.labels.sms_notification", "values": {}},
        )
    )
    if not result.claimed or result.claim_token is None:
        return None
    return NotificationEffect(result.effect.id, result.claim_token)


async def close_notification(
    db: AsyncSession,
    ticket: NotificationEffect,
    *,
    outcome: Literal["accepted", "retryable", "permanent", "unknown", "cancelled"],
    error_code: str | None,
) -> None:
    repo = EffectLedgerRepository(db)
    if outcome == "accepted":
        await repo.close_success(ticket.id, ticket.token)
    elif outcome in {"unknown", "cancelled"}:
        await repo.close_abandoned(
            ticket.id, ticket.token, error_code=error_code or "DELIVERY_ACK_UNKNOWN"
        )
    else:
        await repo.close_failure(
            ticket.id, ticket.token, error_code=error_code or "DELIVERY_REFUSED"
        )


async def abandon_notification(db: AsyncSession, owner: UUID, effect_id: UUID | None) -> None:
    if effect_id is None:
        return
    row = await db.scalar(
        select(AgentEffect).where(
            AgentEffect.id == effect_id,
            AgentEffect.user_id == owner,
            AgentEffect.status == EffectStatus.CLAIMED,
        )
    )
    if row is not None and row.claim_token is not None:
        await EffectLedgerRepository(db).close_abandoned(
            row.id, row.claim_token, error_code="DELIVERY_ACK_UNKNOWN"
        )
