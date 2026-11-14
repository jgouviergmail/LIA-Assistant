"""
Scheduled Actions router with FastAPI endpoints.

Provides CRUD operations, toggle enable/disable, and immediate test execution.
A routine started by calls (ADR-386) gets its secret in the answer of the
request that drew it — its creation, its switch to that clock, or a new secret
asked for — and in no other answer: those answers are never cached.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.exceptions import raise_internal_error
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import require_capability
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.scheduled_actions.models import (
    ScheduledAction as ScheduledActionModel,
)
from src.domains.scheduled_actions.models import TriggerKind
from src.domains.scheduled_actions.schemas import (
    RoutineWebhookSecretResponse,
    ScheduledActionFormCreate,
    ScheduledActionFormUpdate,
    ScheduledActionListResponse,
    ScheduledActionResponse,
    ScheduledActionWeekResponse,
)
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.scheduled_actions.webhooks import routine_webhook_url
from src.domains.scheduled_actions.week_projection import project_routine_week
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/scheduled-actions", tags=["Scheduled Actions"])


def _action_to_response(action: ScheduledActionModel) -> ScheduledActionResponse:
    """Convert ScheduledAction model to response schema."""
    return ScheduledActionResponse.model_validate(action)


def _with_new_secret(
    action: ScheduledActionModel, secret: str | None, response: Response
) -> ScheduledActionResponse:
    """The routine's response, carrying a secret this request drew (never cached)."""
    answer = _action_to_response(action)
    if secret is None:
        return answer
    response.headers["Cache-Control"] = "no-store"
    return answer.model_copy(update={"new_webhook_secret": secret})


# =============================================================================
# List
# =============================================================================


@router.get(
    "",
    response_model=ScheduledActionListResponse,
    summary="List scheduled actions",
    description="Get all scheduled actions for the current user.",
)
async def list_scheduled_actions(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionListResponse:
    """List all scheduled actions for the current user."""
    service = ScheduledActionService(db)
    actions = await service.list_for_user(user.id)

    logger.info(
        "scheduled_actions_listed",
        user_id=str(user.id),
        total=len(actions),
    )

    return ScheduledActionListResponse(
        scheduled_actions=[_action_to_response(a) for a in actions],
        total=len(actions),
    )


# =============================================================================
# The current week (ADR-265)
# =============================================================================


# Declared BEFORE any `/{action_id}` route: a literal segment must be matched
# before a path parameter, or `week` is parsed as a UUID and answers 422.
@router.get(
    "/week",
    response_model=ScheduledActionWeekResponse,
    summary="Current week of the scheduled actions",
    description=(
        "For every routine, the instants it fires at this week and how the run "
        "serving each one ended. Computed from the scheduler's own cron engine."
    ),
)
async def week_scheduled_actions(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionWeekResponse:
    """The current week of every routine of the current user."""
    weeks = await ScheduledActionService(db).week_for_user(user.id)
    return project_routine_week(weeks)


# =============================================================================
# Create
# =============================================================================


@router.post(
    "",
    response_model=ScheduledActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create scheduled action",
    description="Create a new scheduled action for the current user.",
)
async def create_scheduled_action(
    data: ScheduledActionFormCreate,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Create a new scheduled action, with the MCP servers its form pre-approves (D9)."""
    service = ScheduledActionService(db)
    action = await service.create(
        user_id=user.id,
        data=data,
        user_timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
    )
    secret: str | None = None
    if action.trigger_kind == TriggerKind.WEBHOOK.value:
        action, secret = await service.new_webhook_secret(action.id, user.id)
    if data.mcp_preapproved_servers:
        action = await service.set_mcp_preapproval(action, user, data.mcp_preapproved_servers)
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_created",
        user_id=str(user.id),
        action_id=str(action.id),
    )

    return _with_new_secret(action, secret, response)


# =============================================================================
# Update
# =============================================================================


@router.patch(
    "/{action_id}",
    response_model=ScheduledActionResponse,
    summary="Update scheduled action",
    description="Update an existing scheduled action.",
)
async def update_scheduled_action(
    action_id: UUID,
    data: ScheduledActionFormUpdate,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Update an existing scheduled action; an absent pre-approval is left as it is (D9)."""
    service = ScheduledActionService(db)
    stored_kind = (await service.get_with_ownership_check(action_id, user.id)).trigger_kind
    action = await service.update(action_id, user.id, data.routine_changes())
    secret: str | None = None
    if action.trigger_kind == TriggerKind.WEBHOOK.value != stored_kind:
        action, secret = await service.new_webhook_secret(action.id, user.id)
    if "mcp_preapproved_servers" in data.model_fields_set:
        action = await service.set_mcp_preapproval(action, user, data.mcp_preapproved_servers)
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_updated",
        user_id=str(user.id),
        action_id=str(action_id),
    )

    return _with_new_secret(action, secret, response)


# =============================================================================
# A new secret for a routine started by calls (ADR-386)
# =============================================================================


@router.post(
    "/{action_id}/webhook-secret",
    response_model=RoutineWebhookSecretResponse,
    summary="Draw a new secret for a routine started by calls",
    description=(
        "Draws a new HMAC secret for a webhook routine and returns it with the routine's "
        "address. The previous secret stops working at once; this answer is the only one "
        "the new secret is ever in."
    ),
    dependencies=[Depends(require_capability(PlatformCapability.ROUTINE_WEBHOOKS))],
)
async def draw_routine_webhook_secret(
    action_id: UUID,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RoutineWebhookSecretResponse:
    """Draw and show a webhook routine's new secret, once."""
    action, secret = await ScheduledActionService(db).new_webhook_secret(action_id, user.id)
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    if action.webhook_key is None:
        # The table's CHECK gives every webhook routine its address: never reached.
        raise_internal_error("webhook routine without an address")
    return RoutineWebhookSecretResponse(
        webhook_url=routine_webhook_url(action.webhook_key), webhook_secret=secret
    )


# =============================================================================
# Delete
# =============================================================================


@router.delete(
    "/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete scheduled action",
    description="Delete a scheduled action.",
)
async def delete_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a scheduled action."""
    service = ScheduledActionService(db)
    await service.delete(action_id, user.id)
    await db.commit()

    logger.info(
        "scheduled_action_deleted",
        user_id=str(user.id),
        action_id=str(action_id),
    )


# =============================================================================
# Toggle
# =============================================================================


@router.patch(
    "/{action_id}/toggle",
    response_model=ScheduledActionResponse,
    summary="Toggle scheduled action",
    description="Toggle enable/disable for a scheduled action.",
)
async def toggle_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ScheduledActionResponse:
    """Toggle enable/disable for a scheduled action."""
    service = ScheduledActionService(db)
    action = await service.toggle(action_id, user.id)
    await db.commit()
    await db.refresh(action)

    logger.info(
        "scheduled_action_toggled",
        user_id=str(user.id),
        action_id=str(action_id),
        is_enabled=action.is_enabled,
    )

    return _action_to_response(action)


# =============================================================================
# Execute (test now)
# =============================================================================


@router.post(
    "/{action_id}/execute",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute scheduled action now",
    description="Trigger immediate execution of a scheduled action (fire-and-forget).",
)
async def execute_scheduled_action(
    action_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Trigger immediate execution of a scheduled action.

    The execution runs asynchronously (fire-and-forget).
    The result will appear in the user's conversation and as a notification.
    """
    service = ScheduledActionService(db)
    action = await service.reserve_manual_execution(action_id, user.id)
    await db.commit()

    # Fire-and-forget execution via background task
    # Import here to avoid circular imports
    from src.infrastructure.scheduler.scheduled_action_executor import (
        execute_single_action,
    )

    # The run holds the routine by the token it was reserved under: a tick that
    # took it over meanwhile is the only one allowed to settle it.
    safe_fire_and_forget(
        execute_single_action(
            action_id=action.id,
            user_id=user.id,
            execution_token=action.execution_token,
            # The click is the person's act: never given up for a slot's age.
            started_by_person=True,
        ),
        name=f"scheduled_action_execute_{action.id}",
    )

    logger.info(
        "scheduled_action_manual_execute",
        user_id=str(user.id),
        action_id=str(action_id),
    )

    return {"status": "executing"}
