"""Owner-checked status, reattachment and cancellation over durable SQL occupancy."""

from uuid import UUID

from src.core.conversation_execution import ExecutionPhase, ExecutionSnapshot
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationRef
from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.agents.api.run_schemas import ActiveRunResponse, CancelRunResponse
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.streaming.run_stream_broker import request_cancel


async def read_target(owner_id: UUID, selection: ConversationSelection) -> ConversationRef | None:
    """A control request validates ownership and revision without creating Main."""
    async with get_db_context() as db:
        return await ConversationCatalogueService(db).resolve_target(owner_id, selection)


async def active_status(owner_id: UUID, selection: ConversationSelection) -> ActiveRunResponse:
    """Account occupancy is visible even when another discussion is selected."""
    target = await read_target(owner_id, selection)
    async with get_db_context() as db:
        active = await ConversationExecutionRepository(db).snapshot_for_owner(owner_id)
    if active is None:
        return ActiveRunResponse()
    return ActiveRunResponse.occupied(
        active.busy, active.title, selected=active.busy.target == target
    )


async def cancel_selected(owner_id: UUID, selection: ConversationSelection) -> CancelRunResponse:
    """An old tab can stop only the selected generation, never another discussion's work."""
    target = await read_target(owner_id, selection)
    async with get_db_context() as db:
        active = await ConversationExecutionRepository(db).snapshot_for_owner(owner_id)
    if (
        active is None
        or target != active.busy.target
        or active.busy.phase != ExecutionPhase.RUNNING
        or not active.busy.cancellable
    ):
        return CancelRunResponse(cancelled=False)
    # The exact stream key cannot cancel a replacement that starts after this read.
    await request_cancel(await get_redis_cache(), active.stream_id)
    return CancelRunResponse(cancelled=True, stream_id=active.stream_id)


async def require_subscribable(
    owner_id: UUID,
    selection: ConversationSelection,
    stream_id: str,
) -> ExecutionSnapshot:
    """A subscriber proves owner, target, generation and active reconnectable transport."""
    target = await read_target(owner_id, selection)
    async with get_db_context() as db:
        active = await ConversationExecutionRepository(db).snapshot_for_owner(
            owner_id, stream_id=stream_id
        )
    if (
        active is None
        or target != active.busy.target
        or not active.relayed
        or active.busy.phase != ExecutionPhase.RUNNING
    ):
        raise_not_found_or_unauthorized("run")
    return active
