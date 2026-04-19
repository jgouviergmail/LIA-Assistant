"""Skills domain exceptions — centralized raisers for the skills router.

Thin wrappers around ``src.core.exceptions`` that add skill-specific log
context so HTTP responses and structured logs stay consistent across the
skills API (import, delete, toggle, description update, etc.).

Pattern mirrors ``src.domains.attachments.service`` module-local raisers,
and complies with CLAUDE.md §18 (never raise raw HTTPException in routers).
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import status

from src.core.exceptions import (
    AuthorizationError,
    BaseAPIException,
    ResourceNotFoundError,
    ValidationError,
)


def raise_skill_not_found(skill_name: str, *, scope: str | None = None) -> NoReturn:
    """Raise 404 for a missing skill.

    Args:
        skill_name: Skill identifier used in URL path.
        scope: Optional ``"admin"`` or ``"user"`` for more specific logging.

    Raises:
        ResourceNotFoundError: 404 Not Found.
    """
    resource_type = f"{scope}_skill" if scope else "skill"
    raise ResourceNotFoundError(
        resource_type=resource_type,
        resource_id=skill_name,
        detail=f"Skill '{skill_name}' not found",
    )


def raise_admin_skill_delete_forbidden() -> NoReturn:
    """Raise 403 when a non-superuser attempts to delete an admin skill.

    Raises:
        AuthorizationError: 403 Forbidden.
    """
    raise AuthorizationError(
        detail="Cannot delete admin skills",
        action="delete",
        resource_type="admin_skill",
    )


def raise_admin_skill_only(endpoint: str) -> NoReturn:
    """Raise 403 when an admin-only operation is attempted on a non-admin skill.

    Args:
        endpoint: Human-readable endpoint name (for logging).

    Raises:
        AuthorizationError: 403 Forbidden.
    """
    raise AuthorizationError(
        detail=f"Only admin (system) skills can be {endpoint}",
        action=endpoint,
        resource_type="user_skill",
    )


def raise_skill_invalid_format(detail: str) -> NoReturn:
    """Raise 400 for an invalid SKILL.md or zip payload.

    Args:
        detail: Specific validation error message.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(detail=detail, resource_type="skill")


def raise_skill_file_too_large(file_size: int, max_size_kb: int) -> NoReturn:
    """Raise 413 when an imported skill archive exceeds the size limit.

    Args:
        file_size: Actual size in bytes.
        max_size_kb: Configured ceiling in KB.

    Raises:
        BaseAPIException: 413 Request Entity Too Large.
    """
    raise BaseAPIException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"File exceeds {max_size_kb}KB limit",
        log_event="skill_file_too_large",
        file_size=file_size,
        max_size_kb=max_size_kb,
    )


def raise_skill_quota_exceeded(user_id: str, max_per_user: int) -> NoReturn:
    """Raise 429 when a user has reached the maximum number of imported skills.

    Args:
        user_id: User UUID (for audit logging).
        max_per_user: Configured per-user cap.

    Raises:
        BaseAPIException: 429 Too Many Requests.
    """
    raise BaseAPIException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Maximum {max_per_user} skills per user",
        log_event="skill_quota_exceeded",
        user_id=user_id,
        max_per_user=max_per_user,
    )


def raise_skill_translation_invalid(skill_name: str) -> NoReturn:
    """Raise 422 when the LLM-generated translation payload is malformed.

    Args:
        skill_name: Skill being translated.

    Raises:
        BaseAPIException: 422 Unprocessable Entity.
    """
    raise BaseAPIException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="LLM returned invalid JSON for translations",
        log_event="skill_translation_invalid",
        skill_name=skill_name,
    )


def raise_skill_translation_failed(skill_name: str) -> NoReturn:
    """Raise 500 when the LLM-backed translation call fails unexpectedly.

    Args:
        skill_name: Skill being translated.

    Raises:
        BaseAPIException: 500 Internal Server Error.
    """
    raise BaseAPIException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Translation failed",
        log_event="skill_translation_failed",
        skill_name=skill_name,
    )


def raise_skill_write_failed(skill_name: str, target: str) -> NoReturn:
    """Raise 500 when writing a skill file fails at OS level.

    Args:
        skill_name: Skill identifier.
        target: Short name of the file that failed (e.g., ``"SKILL.md"``).

    Raises:
        BaseAPIException: 500 Internal Server Error.
    """
    raise BaseAPIException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to write {target}",
        log_event="skill_write_failed",
        skill_name=skill_name,
        target=target,
    )
