"""Exact source commitment actions execute once, behind fresh capability and ownership fences."""

from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.open_loop_action_schemas import (
    OpenLoopClosePatch,
    OpenLoopCloseRequest,
    OpenLoopCloseValues,
    OpenLoopUpdatePatch,
    OpenLoopUpdateRequest,
    OpenLoopUpdateValues,
    canonical_open_loop,
    open_loop_command,
)
from src.domains.agents.application.open_loop_spec import (
    OPEN_LOOP_CLOSE_OPERATION,
    OPEN_LOOP_UPDATE_OPERATION,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.open_loops.management_commands import (
    apply_open_loop_change,
    changed_open_loop,
    managed_open_loop,
    require_open_loop,
)
from src.domains.open_loops.schemas import CloseLoopRequest, UpdateLoopRequest
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def open_loop_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent | None = None
) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.OPEN_LOOPS)
    await load_actor(db, actor_id)
    if draft is not None and datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def prepare_open_loop_action(
    db: AsyncSession,
    actor_id: UUID,
    request: OpenLoopUpdateRequest | OpenLoopCloseRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = type(request).model_validate(request.model_dump(mode="json", exclude_unset=True))
    await open_loop_fence(db, actor_id)
    expected = await managed_open_loop(db, actor_id, request.loop_id)
    require_open_loop(expected)
    change: UpdateLoopRequest | CloseLoopRequest
    intent: OpenLoopUpdatePatch | OpenLoopClosePatch
    if isinstance(request, OpenLoopUpdateRequest):
        change = request.changes
        intent = OpenLoopUpdatePatch(
            open_loop=OpenLoopUpdateValues(expected=expected, changes=change)
        )
        spec = OPEN_LOOP_UPDATE_OPERATION
    else:
        change = CloseLoopRequest(action=request.action)
        intent = OpenLoopClosePatch(open_loop=OpenLoopCloseValues(expected=expected, action=change))
        spec = OPEN_LOOP_CLOSE_OPERATION
    await open_loop_fence(db, actor_id)
    return build_action_content(
        actor_id,
        spec,
        intent,
        {"open_loop": expected.model_dump(mode="json")},
        {"open_loop": changed_open_loop(expected, change).model_dump(mode="json")},
        command_id=command_id,
    )


async def execute_open_loop_action(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if not canonical_open_loop(draft):
        raise ValueError("The commitment result must match the exact confirmed source transition")
    expected, change = open_loop_command(draft)
    await open_loop_fence(db, actor_id, draft)
    authorize_actor(
        await UserRepository(db).get_by_id_for_preference_update(actor_id), owner_id=actor_id
    )
    await open_loop_fence(db, actor_id, draft)
    try:
        actual = await managed_open_loop(db, actor_id, expected.id, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("open_loop", detail={"error_code": "STALE_STATE"}) from exc
    require_open_loop(actual)
    if actual != expected:
        raise ResourceConflictError("open_loop", detail={"error_code": "STALE_STATE"})
    if changed_open_loop(actual, change) == actual:
        await open_loop_fence(db, actor_id, draft)
        receipt.committed, receipt.no_op = True, True
        return
    await apply_open_loop_change(db, actor_id, expected.id, change)
    await open_loop_fence(db, actor_id, draft)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    if isinstance(change, CloseLoopRequest):
        with suppress(Exception):
            from src.infrastructure.observability.metrics_registry import track_open_loop_closure

            track_open_loop_closure("api" if change.action == "done" else "dismissed")
