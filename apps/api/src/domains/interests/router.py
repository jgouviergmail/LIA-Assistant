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
from src.core.export_utils import create_csv_response
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.interests.helpers import generate_interest_embedding
from src.domains.interests.models import InterestCategory, InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository
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
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/interests", tags=["Interests"])


def _user_to_settings_response(user: User) -> InterestSettingsResponse:
    """
    Convert User model to InterestSettingsResponse.

    Args:
        user: User model instance with interest settings

    Returns:
        InterestSettingsResponse with user's settings
    """
    return InterestSettingsResponse(
        interests_enabled=user.interests_enabled,
        interests_notify_start_hour=user.interests_notify_start_hour,
        interests_notify_end_hour=user.interests_notify_end_hour,
        interests_notify_min_per_day=user.interests_notify_min_per_day,
        interests_notify_max_per_day=user.interests_notify_max_per_day,
    )


def _interest_to_response(
    interest: UserInterest,
    repo: InterestRepository,
) -> InterestResponse:
    """
    Convert UserInterest model to InterestResponse with computed weight.

    Args:
        interest: UserInterest model instance
        repo: InterestRepository for weight calculation

    Returns:
        InterestResponse with computed effective weight
    """
    return InterestResponse(
        id=interest.id,
        topic=interest.topic,
        category=InterestCategory(interest.category),
        weight=repo.calculate_effective_weight(
            interest,
            decay_rate_per_day=settings.interest_decay_rate_per_day,
        ),
        status=InterestStatus(interest.status),
        positive_signals=interest.positive_signals,
        negative_signals=interest.negative_signals,
        last_mentioned_at=interest.last_mentioned_at,
        last_notified_at=interest.last_notified_at,
        created_at=interest.created_at,
    )


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

        logger.info(
            "interests_listed",
            user_id=str(user.id),
            total=len(items),
            active=active_count,
            blocked=blocked_count,
        )

        return InterestListResponse(
            interests=items,
            total=len(items),
            active_count=active_count,
            blocked_count=blocked_count,
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
        topic_embedding = generate_interest_embedding(data.topic)

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
                topic=data.topic[:50],
                fallback="string_matching",
            )

        # Create interest with embedding
        interest = await repo.create(
            user_id=user.id,
            topic=data.topic,
            category=data.category.value,
            embedding=topic_embedding,
        )

        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_created_manual",
            user_id=str(user.id),
            interest_id=str(interest.id),
            topic=data.topic[:50],
            category=data.category.value,
            has_embedding=topic_embedding is not None,
        )

        return _interest_to_response(interest, repo)

    except IntegrityError as e:
        await db.rollback()
        logger.warning(
            "interest_create_duplicate",
            user_id=str(user.id),
            topic=data.topic[:50],
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
        # Update fields that were provided
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            # No changes, return current settings
            return _user_to_settings_response(user)

        # Apply updates
        for field, value in update_data.items():
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "interest_settings_updated",
            user_id=str(user.id),
            updated_fields=list(update_data.keys()),
        )

        return _user_to_settings_response(user)

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
    try:
        repo = InterestRepository(db)

        # Get count for logging
        interests = await repo.get_all_for_user(user.id)
        count = len(interests)

        # Delete all
        await repo.delete_all_for_user(user.id)
        await db.commit()

        logger.info(
            "interests_delete_all",
            user_id=str(user.id),
            deleted_count=count,
        )

    except Exception as e:
        await db.rollback()
        logger.error(
            "interests_delete_all_failed",
            user_id=str(user.id),
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
) -> dict | StreamingResponse:
    """Export all interests for GDPR data portability."""
    try:
        repo = InterestRepository(db)

        # Get all interests
        interests = await repo.get_all_for_user(user.id)

        # Convert to export format
        export_data = [
            {
                "id": str(interest.id),
                "topic": interest.topic,
                "category": interest.category,
                "status": interest.status,
                "positive_signals": interest.positive_signals,
                "negative_signals": interest.negative_signals,
                "weight": round(
                    repo.calculate_effective_weight(
                        interest,
                        decay_rate_per_day=settings.interest_decay_rate_per_day,
                    ),
                    4,
                ),
                "last_mentioned_at": (
                    interest.last_mentioned_at.isoformat() if interest.last_mentioned_at else ""
                ),
                "last_notified_at": (
                    interest.last_notified_at.isoformat() if interest.last_notified_at else ""
                ),
                "created_at": interest.created_at.isoformat() if interest.created_at else "",
            }
            for interest in interests
        ]

        logger.info(
            "interests_exported",
            user_id=str(user.id),
            total=len(export_data),
            export_format=export_format,
        )

        # Return CSV format
        if export_format == "csv":
            return create_csv_response(data=export_data, filename_prefix="interests")

        # Return JSON format
        return {
            "user_id": str(user.id),
            "exported_at": datetime.now(UTC).isoformat(),
            "total_interests": len(export_data),
            "interests": export_data,
        }

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
        repo = InterestRepository(db)

        # Get interest and verify ownership
        interest = await repo.get_by_id(interest_id)

        if not interest or interest.user_id != user.id:
            raise_interest_not_found(interest_id)

        await repo.delete(interest)
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

        # Get interest and verify ownership
        interest = await repo.get_by_id(interest_id)

        if not interest or interest.user_id != user.id:
            raise_interest_not_found(interest_id)

        # Get fields to update
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            # No changes, return current state
            return _interest_to_response(interest, repo)

        # Determine new values
        new_topic = update_data.get("topic", interest.topic)
        new_category_enum = update_data.get("category")
        new_category_value = new_category_enum.value if new_category_enum else interest.category

        topic_changed = "topic" in update_data and update_data["topic"] != interest.topic
        category_changed = "category" in update_data and new_category_value != interest.category

        # Check uniqueness if topic or category changes
        if topic_changed or category_changed:
            existing = await repo.get_by_user_topic_category(
                user_id=user.id,
                topic=new_topic,
                category=new_category_value,
            )
            if existing and existing.id != interest_id:
                raise ResourceConflictError(
                    resource_type="interest",
                    detail=APIMessages.interest_already_exists_in_category(),
                )

        # Regenerate embedding if topic changes
        new_embedding = None
        if topic_changed:
            new_embedding = generate_interest_embedding(new_topic)
            logger.info(
                "interest_embedding_regenerated",
                interest_id=str(interest_id),
                user_id=str(user.id),
                new_topic=new_topic[:50],
                has_embedding=new_embedding is not None,
            )

        # Apply update
        await repo.update(
            interest=interest,
            topic=update_data.get("topic"),
            category=new_category_value if category_changed else None,
            positive_signals=update_data.get("positive_signals"),
            negative_signals=update_data.get("negative_signals"),
            embedding=new_embedding,
        )

        await db.commit()
        await db.refresh(interest)

        logger.info(
            "interest_updated",
            user_id=str(user.id),
            interest_id=str(interest_id),
            updated_fields=list(update_data.keys()),
            topic_changed=topic_changed,
        )

        return _interest_to_response(interest, repo)

    except (ResourceNotFoundError, ResourceConflictError):
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
    from src.domains.conversations.repository import ConversationRepository

    try:
        repo = InterestRepository(db)

        # Get interest and verify ownership
        interest = await repo.get_by_id(interest_id)

        if not interest or interest.user_id != user.id:
            raise_interest_not_found(interest_id)

        # Apply feedback on the interest entity
        await repo.apply_feedback(interest, data.feedback)

        # Persist feedback state on all associated proactive messages so that
        # the frontend feedback buttons stay hidden across reloads and devices.
        conv_repo = ConversationRepository(db)
        messages_updated = await conv_repo.mark_interest_feedback_submitted(
            user_id=user.id,
            interest_id=interest_id,
            feedback_value=data.feedback,
        )

        await db.commit()

        # Prometheus metric for dashboard 13 "User Feedback"
        try:
            from src.infrastructure.observability.metrics_registry import (
                track_proactive_feedback,
            )

            track_proactive_feedback(task_type="interest", feedback_type=data.feedback)
        except Exception:
            pass

        logger.info(
            "interest_feedback_submitted",
            user_id=str(user.id),
            interest_id=str(interest_id),
            feedback=data.feedback,
            new_status=interest.status,
            messages_updated=messages_updated,
        )

        return {"message": APIMessages.feedback_submitted_successfully()}

    except ResourceNotFoundError:
        raise

    except Exception as e:
        await db.rollback()
        logger.error(
            "interest_feedback_failed",
            user_id=str(user.id),
            interest_id=str(interest_id),
            error=str(e),
        )
        raise_interest_store_error(
            operation="feedback",
            detail=APIMessages.failed_to_submit_feedback(),
            interest_id=str(interest_id),
        )
