"""
Sub-Agents router with FastAPI endpoints.

Provides CRUD operations, template instantiation, toggle, and execution endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.sub_agents.models import SubAgent as SubAgentModel
from src.domains.sub_agents.schemas import (
    SubAgentCreate,
    SubAgentCreateFromTemplate,
    SubAgentExecutionRequest,
    SubAgentExecutionResponse,
    SubAgentListResponse,
    SubAgentResponse,
    SubAgentTemplateListResponse,
    SubAgentTemplateResponse,
    SubAgentUpdate,
)
from src.domains.sub_agents.service import SubAgentService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sub-agents", tags=["Sub-Agents"])


def _subagent_to_response(subagent: SubAgentModel) -> SubAgentResponse:
    """Convert SubAgent model to response schema."""
    return SubAgentResponse.model_validate(subagent)


# =============================================================================
# List
# =============================================================================


@router.get(
    "",
    response_model=SubAgentListResponse,
    summary="List sub-agents",
    description="Get all sub-agents for the current user.",
)
async def list_sub_agents(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentListResponse:
    """List all sub-agents for the current user."""
    service = SubAgentService(db)
    subagents = await service.list_for_user(user.id, include_disabled=True)

    logger.info(
        "subagents_listed",
        user_id=str(user.id),
        total=len(subagents),
    )

    return SubAgentListResponse(
        items=[_subagent_to_response(s) for s in subagents],
        total=len(subagents),
    )


# =============================================================================
# Templates
# =============================================================================


@router.get(
    "/templates",
    response_model=SubAgentTemplateListResponse,
    summary="List available templates",
    description="Get all pre-defined sub-agent templates.",
)
async def list_templates(
    user: User = Depends(get_current_active_session),
) -> SubAgentTemplateListResponse:
    """List available sub-agent templates."""
    templates = SubAgentService.list_templates()
    return SubAgentTemplateListResponse(
        items=[
            SubAgentTemplateResponse(
                id=t["id"],
                name=t["name_default"],
                description=t["description_default"],
                icon=t.get("icon"),
                suggested_skill_ids=t.get("suggested_skill_ids", []),
                suggested_tools=t.get("suggested_tools", []),
                default_blocked_tools=t.get("default_blocked_tools", []),
            )
            for t in templates
        ]
    )


# =============================================================================
# Create
# =============================================================================


@router.post(
    "",
    response_model=SubAgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sub-agent",
    description="Create a new sub-agent with custom configuration.",
)
async def create_sub_agent(
    data: SubAgentCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentResponse:
    """Create a new sub-agent."""
    service = SubAgentService(db)
    subagent = await service.create(user.id, data)
    await db.commit()
    await db.refresh(subagent)

    return _subagent_to_response(subagent)


# =============================================================================
# Create from template
# =============================================================================


@router.post(
    "/from-template/{template_id}",
    response_model=SubAgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create from template",
    description="Create a sub-agent from a pre-defined template with optional overrides.",
)
async def create_from_template(
    template_id: str,
    overrides: SubAgentCreateFromTemplate | None = None,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentResponse:
    """Create a sub-agent from a template."""
    service = SubAgentService(db)
    subagent = await service.create_from_template(user.id, template_id, overrides)
    await db.commit()
    await db.refresh(subagent)

    return _subagent_to_response(subagent)


# =============================================================================
# Get
# =============================================================================


@router.get(
    "/{subagent_id}",
    response_model=SubAgentResponse,
    summary="Get sub-agent",
    description="Get a sub-agent by ID.",
)
async def get_sub_agent(
    subagent_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentResponse:
    """Get a sub-agent by ID."""
    service = SubAgentService(db)
    subagent = await service.get(subagent_id, user.id)
    return _subagent_to_response(subagent)


# =============================================================================
# Update
# =============================================================================


@router.patch(
    "/{subagent_id}",
    response_model=SubAgentResponse,
    summary="Update sub-agent",
    description="Partially update a sub-agent.",
)
async def update_sub_agent(
    subagent_id: UUID,
    data: SubAgentUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentResponse:
    """Update a sub-agent."""
    service = SubAgentService(db)
    subagent = await service.update(subagent_id, user.id, data)
    await db.commit()
    await db.refresh(subagent)

    return _subagent_to_response(subagent)


# =============================================================================
# Delete
# =============================================================================


@router.delete(
    "/{subagent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete sub-agent",
    description="Delete a sub-agent (hard delete).",
)
async def delete_sub_agent(
    subagent_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a sub-agent."""
    service = SubAgentService(db)
    await service.delete(subagent_id, user.id)
    await db.commit()


# =============================================================================
# Toggle
# =============================================================================


@router.patch(
    "/{subagent_id}/toggle",
    response_model=SubAgentResponse,
    summary="Toggle sub-agent",
    description="Toggle is_enabled for a sub-agent.",
)
async def toggle_sub_agent(
    subagent_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentResponse:
    """Toggle a sub-agent's enabled state."""
    service = SubAgentService(db)
    subagent = await service.toggle(subagent_id, user.id)
    await db.commit()
    await db.refresh(subagent)

    return _subagent_to_response(subagent)


# =============================================================================
# Execute
# =============================================================================


@router.post(
    "/{subagent_id}/execute",
    response_model=SubAgentExecutionResponse,
    summary="Execute sub-agent",
    description="Execute a sub-agent synchronously or in background.",
)
async def execute_sub_agent(
    subagent_id: UUID,
    data: SubAgentExecutionRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SubAgentExecutionResponse:
    """Execute a sub-agent with the given instruction."""
    from src.domains.sub_agents.executor import SubAgentExecutor

    service = SubAgentService(db)
    subagent = await service.get(subagent_id, user.id)

    executor = SubAgentExecutor()
    user_timezone = (
        getattr(user, "timezone", DEFAULT_USER_DISPLAY_TIMEZONE) or DEFAULT_USER_DISPLAY_TIMEZONE
    )
    user_language = (
        getattr(user, "language", settings.default_language) or settings.default_language
    )

    if data.run_in_background:
        # Background: executor manages its own DB session and status
        task_id = await executor.execute_background(
            subagent=subagent,
            instruction=data.instruction,
            user_id=user.id,
            user_timezone=user_timezone,
            user_language=user_language,
        )
        return SubAgentExecutionResponse(success=True, task_id=task_id)

    # Sync: executor manages status via the current DB session
    result = await executor.execute(
        subagent=subagent,
        instruction=data.instruction,
        user_id=user.id,
        user_timezone=user_timezone,
        user_language=user_language,
        db=db,
    )

    # Record execution
    summary = (
        result.result[:200] + "..."
        if result.result and len(result.result) > 200
        else result.result or ""
    )
    await service.record_execution(
        subagent_id=subagent.id,
        success=result.success,
        summary=summary if result.success else None,
        error=result.error,
    )
    await db.commit()

    return SubAgentExecutionResponse(
        success=result.success,
        result=result.result,
        tokens_used=result.tokens_used,
        duration_seconds=result.duration_seconds,
    )


# =============================================================================
# Kill execution
# =============================================================================


@router.delete(
    "/{subagent_id}/execution",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kill sub-agent execution",
    description="Cancel an in-progress sub-agent execution.",
)
async def kill_sub_agent_execution(
    subagent_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel a running sub-agent execution."""
    from src.domains.sub_agents.executor import SubAgentExecutor
    from src.domains.sub_agents.models import SubAgentStatus as SAS

    service = SubAgentService(db)
    subagent = await service.get(subagent_id, user.id)

    if subagent.status != SAS.EXECUTING.value:
        raise HTTPException(
            status_code=404,
            detail=f"Sub-agent '{subagent.name}' is not currently executing",
        )

    cancelled = SubAgentExecutor.cancel_execution(subagent_id)
    if not cancelled:
        # No running task found — reset status (stale state)
        subagent.status = SAS.ERROR.value
        subagent.last_error = "Manually stopped by user (no running task found)"
        await db.commit()

    logger.info(
        "subagent_execution_killed",
        subagent_id=str(subagent_id),
        user_id=str(user.id),
        subagent_name=subagent.name,
        cancel_signal_sent=cancelled,
    )
