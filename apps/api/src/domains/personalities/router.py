"""
FastAPI router for personality endpoints.

Provides public and admin endpoints for personality management.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.auth.models import User
from src.domains.personalities.schemas import (
    PersonalityCreate,
    PersonalityListResponse,
    PersonalityResponse,
    PersonalityTranslationCreate,
    PersonalityTranslationResponse,
    PersonalityUpdate,
    UserPersonalityResponse,
    UserPersonalityUpdate,
)
from src.domains.personalities.service import PersonalityService
from src.domains.users.service import UserService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/personalities", tags=["Personalities"])


# =============================================================================
# Public Endpoints (Authenticated Users)
# =============================================================================


@router.get("", response_model=PersonalityListResponse)
async def list_personalities(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalityListResponse:
    """
    List all active personalities.

    Returns personalities localized to user's language preference.
    """
    service = PersonalityService(db)
    return await service.list_active(user.language)


@router.get("/current", response_model=UserPersonalityResponse)
async def get_current_personality(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserPersonalityResponse:
    """
    Get user's current personality preference.

    Returns the user's selected personality or the default if none set.
    """
    service = PersonalityService(db)
    personality = await service.get_user_personality(
        user.personality_id if hasattr(user, "personality_id") else None,
        user.language,
    )
    return UserPersonalityResponse(
        personality_id=getattr(user, "personality_id", None),
        personality=personality,
    )


@router.patch("/current", response_model=UserPersonalityResponse)
async def update_current_personality(
    data: UserPersonalityUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserPersonalityResponse:
    """
    Update user's personality preference.

    Set personality_id to null to use the default personality.
    """
    from src.domains.users.schemas import UserUpdate

    # Update user's personality_id
    user_service = UserService(db)
    await user_service.update_user(
        user.id,
        UserUpdate(personality_id=data.personality_id),
    )

    # Return updated personality
    personality_service = PersonalityService(db)
    personality = await personality_service.get_user_personality(
        data.personality_id,
        user.language,
    )

    logger.info(
        "user_personality_updated",
        user_id=str(user.id),
        personality_id=str(data.personality_id) if data.personality_id else None,
    )

    return UserPersonalityResponse(
        personality_id=data.personality_id,
        personality=personality,
    )


# =============================================================================
# Admin Endpoints (Superusers Only)
# =============================================================================


@router.get("/admin", response_model=list[PersonalityResponse])
async def list_all_personalities(
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> list[PersonalityResponse]:
    """
    List all personalities including inactive ones (admin only).

    Returns full personality details with all translations.
    """
    service = PersonalityService(db)
    return await service.list_all()


@router.get("/admin/{personality_id}", response_model=PersonalityResponse)
async def get_personality(
    personality_id: UUID,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalityResponse:
    """
    Get a specific personality by ID (admin only).
    """
    service = PersonalityService(db)
    personality = await service.get_by_id(personality_id)
    return PersonalityResponse.model_validate(personality)


@router.post("/admin", response_model=PersonalityResponse, status_code=201)
async def create_personality(
    data: PersonalityCreate,
    auto_translate: bool = Query(True, description="Auto-translate to other languages"),
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalityResponse:
    """
    Create a new personality (admin only).

    If auto_translate is True, missing language translations will be
    automatically generated using GPT-4.1-nano.
    """
    service = PersonalityService(db)
    personality = await service.create(data, auto_translate=auto_translate)

    logger.info(
        "personality_created_by_admin",
        admin_id=str(user.id),
        personality_code=data.code,
    )

    return PersonalityResponse.model_validate(personality)


@router.patch("/admin/{personality_id}", response_model=PersonalityResponse)
async def update_personality(
    personality_id: UUID,
    data: PersonalityUpdate,
    propagate: bool = Query(
        True,
        description="Auto-propagate translations when title/description change",
    ),
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalityResponse:
    """
    Update an existing personality (admin only).

    Supports updating:
    - code (with uniqueness validation)
    - emoji, is_default, is_active, sort_order
    - prompt_instruction
    - title/description (with optional auto-propagation to all languages)

    Query parameters:
    - propagate: If True (default), changes to title/description
                 trigger automatic translation to all supported languages.
    """
    service = PersonalityService(db)
    personality = await service.update(
        personality_id,
        data,
        propagate_translations=propagate,
    )

    logger.info(
        "personality_updated_by_admin",
        admin_id=str(user.id),
        personality_id=str(personality_id),
        propagate=propagate,
    )

    return PersonalityResponse.model_validate(personality)


@router.delete("/admin/{personality_id}", status_code=204)
async def delete_personality(
    personality_id: UUID,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a personality (admin only).

    Cannot delete the default personality.
    """
    service = PersonalityService(db)
    await service.delete(personality_id)

    logger.info(
        "personality_deleted_by_admin",
        admin_id=str(user.id),
        personality_id=str(personality_id),
    )


@router.post(
    "/admin/{personality_id}/translations",
    response_model=PersonalityTranslationResponse,
)
async def add_translation(
    personality_id: UUID,
    data: PersonalityTranslationCreate,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalityTranslationResponse:
    """
    Add or update a translation for a personality (admin only).
    """
    service = PersonalityService(db)
    translation = await service.add_translation(personality_id, data)

    logger.info(
        "personality_translation_added",
        admin_id=str(user.id),
        personality_id=str(personality_id),
        language=data.language_code,
    )

    return PersonalityTranslationResponse.model_validate(translation)


@router.post("/admin/{personality_id}/auto-translate")
async def trigger_auto_translation(
    personality_id: UUID,
    source_language: str = Query(
        settings.default_language, description="Source language to translate from"
    ),
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger auto-translation for missing languages (admin only).

    Uses GPT-4.1-nano to translate title and description to all
    supported languages that don't have translations yet.
    """
    service = PersonalityService(db)
    count = await service.trigger_auto_translation(personality_id, source_language)

    logger.info(
        "auto_translation_triggered_by_admin",
        admin_id=str(user.id),
        personality_id=str(personality_id),
        translations_created=count,
    )

    return {
        "translations_created": count,
        "source_language": source_language,
    }
