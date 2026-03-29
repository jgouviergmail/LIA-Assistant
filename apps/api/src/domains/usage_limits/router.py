"""
Usage limits domain router.

REST API endpoints for per-user usage limit management.
User-facing endpoint for checking own limits, admin endpoints for CRUD.

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_user_not_found
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.auth.models import User
from src.domains.usage_limits.schemas import (
    AdminUserUsageLimitListResponse,
    AdminUserUsageLimitResponse,
    UsageBlockUpdate,
    UsageLimitUpdate,
    UserUsageLimitResponse,
)
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.repository import UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/usage-limits", tags=["Usage Limits"])


async def _verify_user_exists(db: AsyncSession, user_id: UUID) -> None:
    """Verify a user exists (including inactive accounts).

    Admins need to configure limits on inactive accounts to prepare
    them before activation. Uses include_inactive=True.

    Args:
        db: Database session.
        user_id: Target user UUID.

    Raises:
        ResourceNotFoundError: If user does not exist.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id, include_inactive=True)
    if not user:
        raise_user_not_found(user_id)


# ============================================================================
# User endpoints
# ============================================================================


@router.get(
    "/me",
    response_model=UserUsageLimitResponse,
    summary="Get my usage limits",
    description="Get the current user's usage limits, current usage, and enforcement status.",
)
async def get_my_usage_limits(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserUsageLimitResponse:
    """Get current user's limits and usage.

    Returns:
        UserUsageLimitResponse with all limit dimensions and cycle info.
    """
    service = UsageLimitService(db)
    return await service.get_user_limits_with_usage(
        user_id=current_user.id,
        user_created_at=current_user.created_at,
    )


# ============================================================================
# Admin endpoints
# ============================================================================


@router.get(
    "/admin/users",
    response_model=AdminUserUsageLimitListResponse,
    summary="List users with usage limits",
    description="Admin: Get paginated list of all users with their limits and usage stats.",
)
async def list_users_usage_limits(
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(20, ge=1, le=100, description="Items per page."),
    search: str | None = Query(None, description="Search by email or name."),
    blocked_only: bool = Query(False, description="Show only manually blocked users."),
    sort_by: str = Query("created_at", description="Sort by: email, is_usage_blocked, created_at."),
    sort_order: str = Query("desc", description="Sort order: asc or desc."),
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUsageLimitListResponse:
    """Admin: List all users with limits and usage.

    Args:
        page: Page number.
        page_size: Items per page.
        search: Optional search query.
        blocked_only: Filter to blocked users only.
        sort_by: Column to sort by (email, is_usage_blocked, created_at).
        sort_order: Sort order (asc or desc).
        current_user: Authenticated admin user.
        db: Database session.

    Returns:
        AdminUserUsageLimitListResponse with paginated results.
    """
    service = UsageLimitService(db)
    return await service.get_admin_list(
        page=page,
        page_size=page_size,
        search=search,
        blocked_only=blocked_only,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.put(
    "/admin/users/{user_id}/limits",
    response_model=AdminUserUsageLimitResponse,
    summary="Update user usage limits",
    description="Admin: Update usage limits for a specific user. Immediate effect.",
)
async def update_user_limits(
    user_id: UUID,
    data: UsageLimitUpdate,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUsageLimitResponse:
    """Admin: Update limits for a user.

    Args:
        user_id: Target user UUID.
        data: New limit values.
        current_user: Authenticated admin user.
        db: Database session.

    Returns:
        Updated AdminUserUsageLimitResponse.

    Raises:
        404: If target user does not exist.
    """
    # Verify target user exists (include inactive — admin can prepare limits before activation)
    await _verify_user_exists(db, user_id)

    service = UsageLimitService(db)
    return await service.update_limits(
        user_id=user_id,
        data=data,
        admin_id=current_user.id,
    )


@router.put(
    "/admin/users/{user_id}/block",
    response_model=AdminUserUsageLimitResponse,
    summary="Toggle user block",
    description="Admin: Block or unblock a user. Immediate effect.",
)
async def toggle_user_block(
    user_id: UUID,
    data: UsageBlockUpdate,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUsageLimitResponse:
    """Admin: Toggle manual block for a user.

    Args:
        user_id: Target user UUID.
        data: Block toggle data.
        current_user: Authenticated admin user.
        db: Database session.

    Returns:
        Updated AdminUserUsageLimitResponse.

    Raises:
        404: If target user does not exist.
    """
    # Verify target user exists (include inactive — admin can manage limits before activation)
    await _verify_user_exists(db, user_id)

    service = UsageLimitService(db)
    return await service.toggle_block(
        user_id=user_id,
        data=data,
        admin_id=current_user.id,
    )
