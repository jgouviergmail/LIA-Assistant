"""
Interests router with FastAPI endpoints for user interest management.

Provides CRUD operations and settings management for:
- Interest listing with computed weights
- Manual interest creation
- Interest deletion
- Feedback submission (thumbs_up, thumbs_down, block)
- Notification settings configuration

References:
    - Pattern: domains/memories/router.py
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    raise_interest_not_found,
    raise_interest_store_error,
)
from src.core.i18n_api_messages import APIMessages
from src.core.management_export_file import prepare_management_export_file
from src.core.management_export_response import ManagementExportResponse
from src.core.session_dependencies import get_current_active_session
from src.domains.interests.helpers import generate_interest_embedding
from src.domains.interests.management_commands import (
    create_managed_interest,
    delete_all_managed_interests,
    delete_managed_interest,
    get_managed_interest,
    lock_interest_actor,
    preview_interest_update,
    require_available_interest_configuration,
    update_managed_interest,
)
from src.domains.interests.management_export import InterestExportRecord, interest_export_rows
from src.domains.interests.management_feedback import (
    apply_interest_feedback_effects,
    record_interest_feedback_metric,
)
from src.domains.interests.management_reactivation import reactivate_managed_interest
from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.interests.preference_commands import update_interest_settings
from src.domains.interests.read_models import interest_to_response as _interest_to_response
from src.domains.interests.read_models import (
    user_to_settings_response as _user_to_settings_response,
)
from src.domains.interests.repository import (
    InterestRepository,
)
from src.domains.interests.schemas import (
    InterestCategoriesResponse,
    InterestCategoryResponse,
    InterestCreate,
    InterestFeedbackRequest,
    InterestListResponse,
    InterestResponse,
    InterestSettingsResponse,
    InterestSettingsUpdate,
    InterestUpdate,
)
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/interests", tags=["Interests"])


# =============================================================================
# Categories
# =============================================================================


@router.get(
    "/categories",
    response_model=InterestCategoriesResponse,
    summary="Get interest categories",
    description="Get list of available interest categories with descriptions.",
)
async def list_categories() -> InterestCategoriesResponse:
    """Get available interest categories."""
    # Category descriptions (i18n could be added later)
    category_info = {
        InterestCategory.TECHNOLOGY: "Technology, software, hardware, AI",
        InterestCategory.SCIENCE: "Science, research, discoveries",
        InterestCategory.CULTURE: "Arts, music, literature, history",
        InterestCategory.SPORTS: "Sports, fitness, outdoor activities",
        InterestCategory.FINANCE: "Finance, economy, investments",
        InterestCategory.TRAVEL: "Travel, geography, tourism",
        InterestCategory.NATURE: "Nature, environment, animals",
        InterestCategory.HEALTH: "Health, medicine, wellness",
        InterestCategory.ENTERTAINMENT: "Movies, TV, games, celebrities",
        InterestCategory.OTHER: "Other topics",
    }

    categories = [
        InterestCategoryResponse(
            value=cat.value,
            label=cat.value.capitalize(),
            description=category_info.get(cat, ""),
        )
        for cat in InterestCategory
    ]

    return InterestCategoriesResponse(categories=categories)


# =============================================================================
# Interest CRUD
# =============================================================================


@router.get(
    "",
    response_model=InterestListResponse,
    summary="List user interests",
    description="Get all interests for the current user with computed weights.",
)
async def list_interests(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestListResponse:
    """List all interests for the current user."""
    try:
        repo = InterestRepository(db)

        # Get all interests for user
        interests = await repo.get_all_for_user(user.id)

        # Convert to responses with computed weights
        items = [_interest_to_response(interest, repo) for interest in interests]

        # Count by status
        active_count = sum(1 for i in items if i.status == InterestStatus.ACTIVE)
        blocked_count = sum(1 for i in items if i.status == InterestStatus.BLOCKED)
        dormant_count = sum(1 for i in items if i.status == InterestStatus.DORMANT)

        logger.info(
            "interests_listed",
            user_id=str(user.id),
            total=len(items),
            active=active_count,
            blocked=blocked_count,
            dormant=dormant_count,
        )

        return InterestListResponse(
            interests=items,
            total=len(items),
            active_count=active_count,
            blocked_count=blocked_count,
            dormant_count=dormant_count,
        )

    except Exception as e:
        logger.error(
            "interests_list_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="list",
            detail=APIMessages.failed_to_retrieve_interests(),
        )


@router.post(
    "",
    response_model=InterestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create interest",
    description="Create a new interest manually for the current user.",
)
async def create_interest(
    data: InterestCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestResponse:
    """Create a new interest manually."""
    try:
        repo = InterestRepository(db)

        # Generate embedding for semantic deduplication (same as auto-extraction)
        topic_embedding = await generate_interest_embedding(data.topic)

        if topic_embedding:
            logger.debug(
                "interest_manual_embedding_generated",
                user_id=str(user.id),
                topic=data.topic[:50],
            )
        else:
            logger.info(
                "interest_manual_no_embedding",
                user_id=str(user.id),
                topic_length=len(data.topic),
                fallback="string_matching",
            )

        # Create interest with embedding
        interest = await create_managed_interest(db, user.id, data, embedding=topic_embedding)

        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_created_manual",
            user_id=str(user.id),
            interest_id=str(interest.id),
            category=data.category.value,
            has_embedding=topic_embedding is not None,
        )

        return _interest_to_response(interest, repo)

    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            "interest_create_duplicate",
            user_id=str(user.id),
            topic_length=len(data.topic),
        )
        raise ResourceConflictError(
            resource_type="interest",
            detail=APIMessages.interest_already_exists(),
        ) from e

    except ResourceConflictError:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_create_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="create",
            detail=APIMessages.failed_to_create_interest(),
        )


# =============================================================================
# Settings (MUST be before /{interest_id} routes to avoid path collision)
# =============================================================================


@router.get(
    "/settings",
    response_model=InterestSettingsResponse,
    summary="Get interest settings",
    description="Get current user's interest notification settings.",
)
async def get_settings(
    user: User = Depends(get_current_active_session),
) -> InterestSettingsResponse:
    """Get user's interest notification settings."""
    return _user_to_settings_response(user)


@router.patch(
    "/settings",
    response_model=InterestSettingsResponse,
    summary="Update interest settings",
    description="Update user's interest notification settings.",
)
async def update_settings(
    data: InterestSettingsUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestSettingsResponse:
    """Update user's interest notification settings."""
    try:
        saved = await update_interest_settings(db, user.id, data)

        logger.info(
            "interest_settings_updated",
            user_id=str(user.id),
            updated_fields=list(data.model_fields_set),
        )

        return _user_to_settings_response(saved)

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_settings_update_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="update_settings",
            detail=APIMessages.failed_to_update_settings(),
        )


# =============================================================================
# Delete All and Export (MUST be before /{interest_id} routes)
# =============================================================================


@router.delete(
    "/all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all interests (GDPR)",
    description="Delete all interests for the current user. GDPR erasure.",
)
async def delete_all_interests(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete all interests for the current user (GDPR erasure)."""
    owner = user.id
    try:
        count = await delete_all_managed_interests(db, owner)
        await db.commit()

        logger.info(
            "interests_delete_all",
            user_id=str(owner),
            deleted_count=count,
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "interests_delete_all_failed",
            user_id=str(owner),
            error=str(e),
        )
        raise_interest_store_error(
            operation="delete_all",
            detail=APIMessages.failed_to_delete_all_interests(),
        )


@router.get(
    "/export",
    response_model=None,
    summary="Export all interests (GDPR)",
    description="Export all interests for the current user. Supports JSON and CSV formats. GDPR data portability.",
)
async def export_interests(
    export_format: Literal["json", "csv"] = Query(
        default="csv",
        alias="format",
        description="Export format (json or csv)",
    ),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all interests for GDPR data portability."""
    try:
        now = datetime.now(UTC)
        reader = await prepare_management_export_file(
            interest_export_rows(db, user.id, now),
            format=export_format,
            fieldnames=tuple(InterestExportRecord.model_fields),
            collection="interests",
            metadata={"user_id": str(user.id), "exported_at": now.isoformat()},
            count_key="total_interests",
            max_bytes=settings.account_export_max_bytes,
        )
        logger.info(
            "interests_exported",
            user_id=str(user.id),
            file_size_bytes=reader.file_size_bytes,
            export_format=export_format,
        )

        return ManagementExportResponse(reader, collection="interests", format=export_format)

    except Exception as e:
        logger.error(
            "interests_export_failed",
            user_id=str(user.id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="export",
            detail=APIMessages.failed_to_export_interests(),
        )


# =============================================================================
# Interest Operations by ID
# =============================================================================


@router.delete(
    "/{interest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete interest",
    description="Delete a specific interest.",
)
async def delete_interest(
    interest_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific interest."""
    try:
        await delete_managed_interest(db, user.id, interest_id)
        await db.commit()

        logger.info(
            "interest_deleted",
            user_id=str(user.id),
            interest_id=str(interest_id),
        )

    except ResourceNotFoundError:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_delete_failed",
            user_id=str(user.id),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="delete",
            detail=APIMessages.failed_to_delete_interest(),
            interest_id=str(interest_id),
        )


@router.patch(
    "/{interest_id}",
    response_model=InterestResponse,
    summary="Update interest",
    description="Update an existing interest (topic, category, signals).",
)
async def update_interest(
    interest_id: UUID,
    data: InterestUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestResponse:
    """
    Update an existing interest.

    - Topic change triggers embedding regeneration
    - Uniqueness is per (user_id, topic, category)
    """
    try:
        repo = InterestRepository(db)

        interest = await get_managed_interest(db, user.id, interest_id)
        expected = preview_interest_update(interest, InterestUpdate())
        expected_status, expected_subject = interest.status, interest.subject
        configuration = preview_interest_update(interest, data)
        await require_available_interest_configuration(db, interest, configuration)
        topic_changed = configuration.topic != expected.topic
        assert configuration.topic is not None
        new_embedding = (
            await generate_interest_embedding(configuration.topic) if topic_changed else None
        )
        interest, _ = await update_managed_interest(
            db,
            user.id,
            interest,
            data,
            embedding=new_embedding,
            expected=expected,
            expected_status=expected_status,
            expected_subject=expected_subject,
        )

        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_updated",
            user_id=str(user.id),
            interest_id=str(interest_id),
            updated_fields=list(data.model_fields_set),
            topic_changed=topic_changed,
        )

        return _interest_to_response(interest, repo)

    except ResourceNotFoundError, ResourceConflictError:
        raise

    except IntegrityError as e:
        await db.rollback()
        raise ResourceConflictError(
            resource_type="interest",
            detail=APIMessages.interest_already_exists_in_category(),
        ) from e

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_update_failed",
            user_id=str(user.id),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="update",
            detail=APIMessages.failed_to_update_interest(),
            interest_id=str(interest_id),
        )


# =============================================================================
# Feedback
# =============================================================================


@router.post(
    "/{interest_id}/feedback",
    status_code=status.HTTP_200_OK,
    summary="Submit feedback",
    description="Submit feedback on an interest (thumbs_up, thumbs_down, block).",
)
async def submit_feedback(
    interest_id: UUID,
    data: InterestFeedbackRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Submit feedback on an interest."""
    owner = user.id

    try:
        actor = await lock_interest_actor(db, owner)
        repo = InterestRepository(db)

        # Get interest and verify ownership
        interest = await repo.get_by_id(interest_id, lock=True)

        if not interest or interest.user_id != owner:
            raise_interest_not_found(interest_id)

        effects = await apply_interest_feedback_effects(
            db,
            actor,
            interest,
            data.feedback,
            run_id=data.run_id,
        )

        await db.commit()

        record_interest_feedback_metric(data.feedback)

        logger.info(
            "interest_feedback_submitted",
            user_id=str(owner),
            interest_id=str(interest_id),
            feedback=data.feedback,
            new_status=interest.status,
            messages_updated=effects.messages_updated,
            audit_updated=effects.audit_updated,
        )

        return {"message": APIMessages.feedback_submitted_successfully()}

    except ResourceNotFoundError:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_feedback_failed",
            user_id=str(owner),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="feedback",
            detail=APIMessages.failed_to_submit_feedback(),
            interest_id=str(interest_id),
        )


# =============================================================================
# Reactivation
# =============================================================================


@router.post(
    "/{interest_id}/reactivate",
    response_model=InterestResponse,
    status_code=status.HTTP_200_OK,
    summary="Reactivate a dormant interest",
    description="Reactivate a dormant interest, resetting its signals to a fresh state.",
)
async def reactivate_interest(
    interest_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestResponse:
    """Reactivate a dormant interest (reset counters to a fresh state).

    Args:
        interest_id: UUID of the interest to reactivate.
        user: Authenticated owner (injected).
        db: Database session (injected).

    Returns:
        The reactivated interest as an ``InterestResponse``.

    Raises:
        ResourceNotFoundError: If the interest is missing or not owned by the user.
        ResourceConflictError: If the interest is not in the ``dormant`` status.
    """
    owner = user.id
    try:
        repo = InterestRepository(db)
        interest = await reactivate_managed_interest(db, owner, interest_id)
        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_reactivated",
            user_id=str(owner),
            interest_id=str(interest_id),
        )

        return _interest_to_response(interest, repo)

    except ResourceNotFoundError, ResourceConflictError:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_reactivate_failed",
            user_id=str(owner),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="reactivate",
            detail=APIMessages.failed_to_reactivate_interest(),
            interest_id=str(interest_id),
        )
