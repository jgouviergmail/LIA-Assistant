"""UI and native reset share the same owner-first source transaction and scope comparison."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.psyche.management_projection import project_psyche_state
from src.domains.psyche.models import PsycheHistory, PsycheState
from src.domains.psyche.reset_snapshot import PsycheResetSnapshot, psyche_reset_snapshot
from src.domains.psyche.schemas import PsycheResetRequest, PsycheResetResponse
from src.domains.psyche.service import PsycheService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class PsycheResetCompletionUnknown(RuntimeError):
    """The SQL acknowledgement cannot establish reset completion."""


async def observed_psyche_reset(
    db: AsyncSession, actor_id: UUID, result: PsycheResetResponse, expected: PsycheResetSnapshot
) -> dict[str, JsonValue]:
    stored = await db.scalar(
        select(PsycheState)
        .where(PsycheState.user_id == actor_id)
        .execution_options(populate_existing=True)
    )
    history = await db.scalar(
        select(func.count()).select_from(PsycheHistory).where(PsycheHistory.user_id == actor_id)
    )
    projection, _ = project_psyche_state(stored) if stored else (None, None)
    observed = projection.model_dump(mode="json") if projection else {}
    if stored is not None and any(
        observed[name] != value for name, value in expected.after.items()
    ):
        raise ResourceConflictError("psyche", detail={"error_code": "STALE_STATE"})
    return {
        **result.model_dump(mode="json"),
        "state_present": stored is not None,
        "history_count": history or 0,
        "values": {name: observed[name] for name in expected.after},
    }


async def reset_managed_psyche(
    db: AsyncSession,
    actor_id: UUID,
    request: PsycheResetRequest,
    *,
    expected: PsycheResetSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> PsycheResetResponse:
    selected = PsycheResetRequest.model_validate(request.model_dump())
    owner = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if owner is None:
        raise AuthorizationError()
    if check is not None:
        await check()
    actual = await psyche_reset_snapshot(db, actor_id, selected, locked=True)
    if check is not None:
        await check()
    if expected is not None and actual != expected:
        raise ResourceConflictError("psyche", detail={"error_code": "STALE_STATE"})
    result = PsycheResetResponse(status="reset", level=selected.level)
    if (selected.level != "purge" and actual.states == 0) or (
        selected.level == "purge" and actual.states == actual.history == 0
    ):
        if receipt is not None:
            receipt.committed, receipt.no_op, receipt.values = (
                True,
                True,
                result.model_dump(mode="json"),
            )
        return result
    await PsycheService(db).reset_state(actor_id, selected.level)
    await db.flush()
    observed = await observed_psyche_reset(db, actor_id, result, actual)
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise PsycheResetCompletionUnknown from exc
    if receipt is not None:
        receipt.committed, receipt.values = True, observed
    return result
