"""
Authorization utilities following principle of least privilege.

Best Practices:
- Explicit permission checks
- Fail-secure by default
- Audit logging for denied access
- Separation of authentication (who you are) and authorization (what you can do)

HTTP Status Code Strategy (OWASP-aligned):
- 403 Forbidden: For PUBLIC resources (user profiles, public documents)
  → Clear UX, reveals existence but denies access
- 404 Not Found: For PRIVATE resources (connectors, credentials, private documents)
  → Security-first, prevents enumeration attacks, hides existence
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.exceptions import (
    raise_admin_required,
    raise_not_found_or_unauthorized,
    raise_permission_denied,
    raise_user_inactive,
)

logger = structlog.get_logger(__name__)


def check_resource_ownership(
    resource: Any,
    current_user: Any,
    resource_name: str,
    allow_superuser: bool = True,
    hide_existence: bool = False,
) -> None:
    """
    Check that the current user owns the resource.

    Best Practices:
    - Fail-secure: Raises exception if resource is None
    - Audit logging: Logs all unauthorized access attempts
    - Flexible: Supports superuser bypass
    - OWASP-compliant: Supports both 403 and 404 strategies

    Args:
        resource: Resource to check (must have user_id attribute)
        current_user: Authenticated user (must have id and is_superuser)
        resource_name: Name for logging/errors (e.g., "connector", "user")
        allow_superuser: If True, superusers bypass the check
        hide_existence: If True, uses 404 instead of 403 (private resources)

    Raises:
        HTTPException 404: If resource does not exist OR (hide_existence=True) not authorized
        HTTPException 403: If (hide_existence=False) user is not the owner

    HTTP Status Strategy:
        - hide_existence=False (default): PUBLIC resources (user profiles)
          → Returns 404 if not found, 403 if not authorized
        - hide_existence=True: PRIVATE resources (connectors, credentials)
          → Returns 404 for both "not found" and "not authorized" (OWASP enumeration prevention)

    Examples:
        >>> # Public resource (user profile)
        >>> user = await repo.get_by_id(user_id)
        >>> check_resource_ownership(user, current_user, "user", hide_existence=False)

        >>> # Private resource (connector)
        >>> connector = await repo.get_by_id(connector_id)
        >>> check_resource_ownership(connector, current_user, "connector", hide_existence=True)
    """
    if not resource:
        raise_not_found_or_unauthorized(
            resource_type=resource_name,
        )

    # Superuser bypass
    if allow_superuser and current_user.is_superuser:
        logger.debug(
            "resource_access_granted_superuser",
            resource_type=resource_name,
            resource_id=str(getattr(resource, "id", "unknown")),
            user_id=str(current_user.id),
        )
        return

    # Check ownership
    if resource.user_id != current_user.id:
        # Security strategy: use unified exception that supports both strategies
        resource_id = getattr(resource, "id", None)
        if hide_existence:
            # Return 404 to prevent enumeration attacks (OWASP)
            raise_not_found_or_unauthorized(
                resource_type=resource_name,
                resource_id=resource_id,
            )
        else:
            # Return 403 for public resources (better UX)
            raise_permission_denied(
                action="access",
                resource_type=resource_name,
                user_id=current_user.id,
                resource_id=resource_id,
            )

    logger.debug(
        "resource_access_granted_owner",
        resource_type=resource_name,
        resource_id=str(getattr(resource, "id", "unknown")),
        user_id=str(current_user.id),
    )


def require_superuser(current_user: Any, action: str = "perform this action") -> None:
    """
    Check that the user is a superuser.

    Best Practices:
    - Explicit permission check
    - Audit logging
    - Clear error message

    Args:
        current_user: Authenticated user (must have is_superuser)
        action: Action description for the error message

    Raises:
        HTTPException 403: If the user is not a superuser

    Example:
        >>> require_superuser(current_user, "access admin dashboard")
    """
    if not current_user.is_superuser:
        raise_admin_required(current_user.id)

    logger.debug(
        "superuser_access_granted",
        action=action,
        user_id=str(current_user.id),
    )


def check_user_active(user: Any) -> None:
    """
    Check that the user account is active.

    Best Practices:
    - Soft-delete awareness
    - Security: Prevents access to deactivated accounts
    - Audit logging

    Args:
        user: User to check (must have is_active)

    Raises:
        HTTPException 403: If the account is inactive

    Example:
        >>> user = await repo.get_by_id(user_id)
        >>> check_user_active(user)
    """
    if not user.is_active:
        raise_user_inactive(user.id)


def check_user_ownership_or_superuser(
    target_user_id: UUID,
    current_user: Any,
    action: str = "perform this action",
) -> None:
    """
    Check that the user accesses their own data OR is a superuser.

    Best Practices:
    - Common pattern extraction
    - Audit logging
    - Clear intent

    Args:
        target_user_id: UUID of the target user
        current_user: Authenticated user
        action: Action description for logging

    Raises:
        HTTPException 403: If neither owner nor superuser

    Example:
        >>> check_user_ownership_or_superuser(
        ...     user_id,
        ...     current_user,
        ...     "view profile"
        ... )
    """
    if target_user_id != current_user.id and not current_user.is_superuser:
        raise_permission_denied(
            action=action,
            resource_type="user",
            user_id=current_user.id,
            resource_id=target_user_id,
        )


def check_resource_ownership_by_user_id(
    resource: Any,
    user_id: UUID,
    resource_name: str,
    hide_existence: bool = True,
) -> None:
    """
    Check that the resource belongs to the user specified by user_id.

    Simplified variant of check_resource_ownership() for services that receive
    user_id (UUID) instead of current_user (User object). This function does not
    support superuser bypass since we don't have access to current_user.

    Best Practices:
    - Fail-secure: Raises exception if resource is None
    - Audit logging: Logs all unauthorized access attempts
    - OWASP-compliant: Uses 404 by default for private resources

    Args:
        resource: Resource to check (must have user_id attribute)
        user_id: UUID of the user requesting access
        resource_name: Name for logging/errors (e.g., "connector", "user")
        hide_existence: If True (default), uses 404 (private resources)

    Raises:
        HTTPException 404: If resource does not exist OR not authorized

    HTTP Status Strategy:
        - hide_existence=True (default): PRIVATE resources (connectors, credentials)
          → Returns 404 for both "not found" and "not authorized" (OWASP enumeration prevention)
        - hide_existence=False: PUBLIC resources (use check_resource_ownership instead)

    Example:
        >>> # In service layer with user_id parameter
        >>> connector = await repo.get_by_id(connector_id)
        >>> check_resource_ownership_by_user_id(connector, user_id, "connector")
    """
    if not resource:
        raise_not_found_or_unauthorized(
            resource_type=resource_name,
        )

    # Check ownership
    if resource.user_id != user_id:
        resource_id = getattr(resource, "id", None)
        # Security strategy: hide existence for private resources (OWASP enumeration prevention)
        if hide_existence:
            # Return 404 to prevent enumeration attacks
            raise_not_found_or_unauthorized(
                resource_type=resource_name,
                resource_id=resource_id,
            )
        else:
            # Return 403 for public resources (better UX)
            raise_permission_denied(
                action="access",
                resource_type=resource_name,
                user_id=user_id,
                resource_id=resource_id,
            )

    logger.debug(
        "resource_access_granted_owner_by_user_id",
        resource_type=resource_name,
        resource_id=str(getattr(resource, "id", "unknown")),
        user_id=str(user_id),
    )
