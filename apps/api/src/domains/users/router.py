"""
Users router with FastAPI endpoints for user management.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.security.authorization import (
    check_user_ownership_or_superuser,
    require_superuser,
)
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.core.validators import get_common_timezones
from src.domains.auth.models import User
from src.domains.users.schemas import (
    HomeLocationResponse,
    HomeLocationUpdate,
    UserActivationResponse,
    UserActivationUpdate,
    UserAutocompleteResponse,
    UserListResponse,
    UserListWithStatsResponse,
    UserProfile,
    UserSearchParams,
    UserUpdate,
)
from src.domains.users.service import UserService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/timezones",
    response_model=dict[str, list[str]],
    summary="Get common timezones",
    description="Get list of common IANA timezones grouped by region. No authentication required.",
)
async def list_common_timezones() -> dict[str, list[str]]:
    """
    Get list of common timezones grouped by region.

    Returns grouped timezones for timezone selector UI.
    Public endpoint (no authentication required).
    """
    return get_common_timezones()


@router.get(
    "",
    response_model=UserListResponse,
    summary="Get all users (Admin)",
    description="Get paginated list of all users. **Requires superuser role.**",
)
async def get_users(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Get paginated list of users (admin only)."""
    service = UserService(db)
    return await service.get_all_users(
        page=page,
        page_size=page_size,
        is_active=is_active,
    )


@router.get(
    "/{user_id}",
    response_model=UserProfile,
    summary="Get user by ID",
    description="Get user profile by user ID. Users can only view their own profile unless they are superuser.",
)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Get user by ID. Users can only view their own profile unless they are superuser."""
    check_user_ownership_or_superuser(user_id, current_user, "view this user profile")

    service = UserService(db)
    return await service.get_user_by_id(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserProfile,
    summary="Update user",
    description="Update user profile (partial update). Users can only update their own profile unless they are superuser.",
)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Update user profile."""
    check_user_ownership_or_superuser(user_id, current_user, "update this user")

    service = UserService(db)
    return await service.update_user(user_id, data)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete user account (soft delete). Only superusers can delete users.",
)
async def delete_user(
    user_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete from database"),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete user account."""
    require_superuser(current_user, "delete users")

    service = UserService(db)
    await service.delete_user(user_id, hard_delete=hard_delete)


@router.get(
    "/search/by-email",
    response_model=list[UserProfile],
    summary="Search users by email",
    description="Search users by email pattern. Requires authentication.",
)
async def search_users_by_email(
    pattern: str = Query(..., description="Email pattern to search for"),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[UserProfile]:
    """Search users by email pattern."""
    service = UserService(db)
    return await service.search_users_by_email(f"%{pattern}%")


# ========== HOME LOCATION ENDPOINTS ==========


@router.get(
    "/me/home-location",
    response_model=HomeLocationResponse | None,
    summary="Get current user's home location",
    description="Get the current user's configured home address (decrypted for display).",
)
async def get_home_location(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HomeLocationResponse | None:
    """Get current user's home location."""
    service = UserService(db)
    return await service.get_home_location(current_user.id)


@router.put(
    "/me/home-location",
    response_model=HomeLocationResponse,
    summary="Set current user's home location",
    description=(
        "Set the current user's home address. "
        "**Requires Google Places connector to be active.** "
        "The address is encrypted at rest using Fernet encryption."
    ),
)
async def set_home_location(
    location: HomeLocationUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HomeLocationResponse:
    """Set current user's home location. Requires Google Places connector."""
    service = UserService(db)
    return await service.set_home_location(current_user.id, location)


@router.delete(
    "/me/home-location",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear current user's home location",
    description="Remove the current user's configured home address.",
)
async def clear_home_location(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear current user's home location."""
    service = UserService(db)
    await service.clear_home_location(current_user.id)


# ========== ADMIN ENDPOINTS ==========


@router.get(
    "/admin/search",
    response_model=UserListWithStatsResponse,
    summary="Search and list users with statistics (Admin)",
    description=(
        "Search and list all users with pagination, filters and statistics. "
        "Includes last login, message count, and token usage per user. "
        "**Requires superuser role.**"
    ),
)
async def search_users_admin(
    q: str | None = Query(None, description="Search query (email or name)"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    is_verified: bool | None = Query(None, description="Filter by verified status"),
    is_superuser: bool | None = Query(None, description="Filter by superuser status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (max 100)"),
    sort_by: str = Query(
        "created_at", description="Sort column (email, full_name, created_at, is_active)"
    ),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> UserListWithStatsResponse:
    """
    Search and list all users with pagination, filters and sorting (admin only).

    Query parameters:
    - q: Search query (email or name)
    - is_active: Filter by active status
    - is_verified: Filter by verified status
    - is_superuser: Filter by superuser status
    - page: Page number (default 1)
    - page_size: Items per page (default 10, max 100)
    - sort_by: Sort column (default created_at)
    - sort_order: Sort order asc/desc (default desc)
    """
    params = UserSearchParams(
        q=q,
        is_active=is_active,
        is_verified=is_verified,
        is_superuser=is_superuser,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    service = UserService(db)
    return await service.search_users(params, current_user.id)


@router.patch(
    "/admin/{user_id}/activation",
    response_model=UserActivationResponse,
    summary="Activate or deactivate user (Admin)",
    description=(
        "Activate or deactivate user account. "
        "When deactivating: user cannot login, all sessions are invalidated, reason must be provided. "
        "Sends email notification to user. "
        "Returns email notification status. "
        "**Requires superuser role.**"
    ),
)
async def update_user_activation_admin(
    user_id: UUID,
    update_data: UserActivationUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> UserActivationResponse:
    """
    Activate or deactivate user account (admin only).

    When deactivating:
    - User cannot login
    - All sessions are invalidated
    - Reason must be provided
    - Email notification sent

    Returns:
    - user: Updated user profile
    - email_notification_sent: Whether email was sent successfully
    - email_notification_error: Error message if email failed (None if success)
    """
    service = UserService(db)
    return await service.update_user_activation(user_id, update_data, current_user.id, request)


@router.delete(
    "/admin/{user_id}/gdpr",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user and all data - RGPD (Admin)",
    description=(
        "Delete user and ALL associated data (RGPD compliance). "
        "Cascade deletes: user account, all connectors, all sessions. "
        "**This action is IRREVERSIBLE.** "
        "**Requires superuser role.** "
        "**Cannot delete superuser accounts.**"
    ),
)
async def delete_user_gdpr_admin(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete user and ALL associated data (RGPD compliance).

    Cascade deletes:
    - User account
    - All connectors
    - All sessions
    - Future: conversations, documents, etc.

    **This action is IRREVERSIBLE.**
    **Cannot delete superuser accounts.**
    """
    service = UserService(db)
    await service.delete_user_gdpr(user_id, current_user.id, request)


@router.get(
    "/admin/autocomplete",
    response_model=UserAutocompleteResponse,
    summary="Autocomplete users by email or name (Admin)",
    description=(
        "Search users by email or full name for autocomplete suggestions. "
        "Returns up to 10 matching users (active and inactive). "
        "**Requires superuser role.**"
    ),
)
async def autocomplete_users_admin(
    q: str = Query(..., min_length=2, description="Search query (email or name, min 2 chars)"),
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> UserAutocompleteResponse:
    """
    Autocomplete users by email or full name (admin only).

    Returns simplified user info for autocomplete dropdowns.
    Searches both email and full_name fields (case-insensitive).
    Limited to 10 results for performance.
    """
    service = UserService(db)
    return await service.autocomplete_users(q)
