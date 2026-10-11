"""A deferred manual run checks current authority and its own reservation."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from redis.asyncio import Redis
from sqlalchemy import Result, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.routine_operations import routine_snapshot
from src.domains.agents.application.routine_schemas import RoutineSnapshot
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.streaming.run_stream_broker import active_run_key

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RoutineExecutionReservation:
    actor_id: UUID
    expected: RoutineSnapshot
    token: UUID
    expires_at: datetime


async def wait_for_routine_turn(redis: Redis, conversation_id: str, expires_at: datetime) -> bool:
    """Wait only within the approval deadline, without holding a SQL transaction."""
    while datetime.now(UTC) < expires_at:
        if not await redis.exists(active_run_key(conversation_id)):
            return True
        remaining = (expires_at - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(settings.background_runs_cancel_poll_seconds, remaining))
    return False


async def cancel_routine_reservation(reservation: RoutineExecutionReservation) -> None:
    async with get_db_context() as db:
        await ScheduledActionRepository(db).release_manual_execution(
            reservation.expected.id, reservation.actor_id, reservation.token
        )


async def authorize_reserved_routine(
    reservation: RoutineExecutionReservation, db: AsyncSession, action: ScheduledAction
) -> bool:
    """Recheck after source reads and before inference; never substitute fresh settings."""
    try:
        await require_application_tools(db)
        await load_actor(db, reservation.actor_id)
        result: Result[tuple[ScheduledAction]] = await db.execute(
            select(ScheduledAction)
            .where(
                ScheduledAction.id == reservation.expected.id,
                ScheduledAction.user_id == reservation.actor_id,
            )
            .execution_options(populate_existing=True)
        )
        current = result.scalar_one_or_none()
        valid = (
            current is not None
            and action.id == reservation.expected.id
            and current.execution_token == reservation.token
            and current.status == "executing"
            and routine_snapshot(current) == reservation.expected
            and datetime.now(UTC) < reservation.expires_at
        )
        await load_actor(db, reservation.actor_id)
        await require_application_tools(db)
        if valid and datetime.now(UTC) < reservation.expires_at:
            return True
    except AuthorizationError, SQLAlchemyError, ValueError:
        await db.rollback()
    try:
        await ScheduledActionRepository(db).release_manual_execution(
            reservation.expected.id, reservation.actor_id, reservation.token
        )
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning(
            "routine_reservation_release_unavailable", action_id=str(reservation.expected.id)
        )
    return False
