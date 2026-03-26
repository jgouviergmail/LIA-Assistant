"""API routes for image generation pricing management (Admin only).

Provides CRUD endpoints for managing per-image pricing by (model, quality, size).
Follows the same pattern as src/domains/llm/router.py.

Phase: evolution — AI Image Generation
Created: 2026-03-26
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input, raise_pricing_not_found
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.image_generation.models import ImageGenerationPricing
from src.domains.image_generation.schemas import (
    ImagePricingCreate,
    ImagePricingListResponse,
    ImagePricingResponse,
    ImagePricingUpdate,
)
from src.domains.users.models import AdminAuditLog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/image-pricing",
    tags=["admin", "image-pricing"],
    dependencies=[Depends(get_current_superuser_session)],
)


@router.get("/pricing", response_model=ImagePricingListResponse)
async def list_active_pricing(
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "model",
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ImagePricingListResponse:
    """List all active image pricing with pagination, search and sorting.

    Args:
        search: Filter by model name (case-insensitive partial match).
        page: Page number (default: 1).
        page_size: Items per page (default: 10, max: 100).
        sort_by: Column to sort by.
        sort_order: Sort order (asc or desc).
        db: Database session.
        current_user: Authenticated superuser.

    Returns:
        Paginated list of active image pricing entries.
    """
    from src.core.pagination_helpers import (
        calculate_skip,
        calculate_total_pages,
        validate_pagination,
    )

    page, page_size = validate_pagination(page, page_size)
    offset = calculate_skip(page, page_size)

    # Window function pagination (single query for count + data)
    stmt = select(
        ImageGenerationPricing,
        func.count().over().label("total_count"),
    ).where(ImageGenerationPricing.is_active)

    if search:
        stmt = stmt.where(ImageGenerationPricing.model.ilike(f"%{search}%"))

    # Whitelist sort columns (security)
    allowed_sort_columns = {
        "model",
        "quality",
        "size",
        "cost_per_image_usd",
    }
    if sort_by not in allowed_sort_columns:
        raise_invalid_input(
            APIMessages.invalid_sort_parameter(list(allowed_sort_columns)),
            sort_by=sort_by,
            allowed=list(allowed_sort_columns),
        )

    sort_column = getattr(ImageGenerationPricing, sort_by)
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(sort_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc())

    stmt = stmt.limit(page_size).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    if rows:
        total = rows[0][1]
        pricing_list = [row[0] for row in rows]
    else:
        total = 0
        pricing_list = []

    total_pages = calculate_total_pages(total, page_size)

    logger.info(
        "image_pricing_list_retrieved",
        total_entries=total,
        page=page,
        search=search,
        admin_user_id=str(current_user.id),
    )

    return ImagePricingListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        entries=[ImagePricingResponse.model_validate(p) for p in pricing_list],
    )


@router.post("/pricing", response_model=ImagePricingResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing(
    data: ImagePricingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ImagePricingResponse:
    """Create a new image pricing entry.

    Args:
        data: Pricing data (model, quality, size, cost).
        request: HTTP request (for audit IP).
        db: Database session.
        current_user: Authenticated superuser.

    Returns:
        Created pricing entry.

    Raises:
        HTTPException: 409 if active pricing already exists for this combination.
    """
    # Check uniqueness among active entries
    stmt = select(ImageGenerationPricing).where(
        and_(
            ImageGenerationPricing.model == data.model,
            ImageGenerationPricing.quality == data.quality,
            ImageGenerationPricing.size == data.size,
            ImageGenerationPricing.is_active,
        )
    )
    existing = await db.execute(stmt)
    if existing.scalars().first():
        raise_invalid_input(
            f"Active pricing already exists for {data.model}/{data.quality}/{data.size}. "
            "Use PUT to update.",
        )

    pricing = ImageGenerationPricing(
        model=data.model,
        quality=data.quality,
        size=data.size,
        cost_per_image_usd=data.cost_per_image_usd,
        is_active=True,
    )
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    # Audit log
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="image_pricing_created",
        resource_type="image_generation_pricing",
        resource_id=pricing.id,
        details={
            "model": pricing.model,
            "quality": pricing.quality,
            "size": pricing.size,
            "cost_per_image_usd": float(pricing.cost_per_image_usd),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "image_pricing_created",
        model=data.model,
        quality=data.quality,
        size=data.size,
        cost_usd=float(data.cost_per_image_usd),
        admin_user_id=str(current_user.id),
    )

    return ImagePricingResponse.model_validate(pricing)


@router.put("/pricing/{pricing_id}", response_model=ImagePricingResponse)
async def update_pricing(
    pricing_id: uuid.UUID,
    data: ImagePricingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ImagePricingResponse:
    """Update image pricing (deactivates old, creates new version).

    Args:
        pricing_id: UUID of the pricing entry to update.
        data: New pricing data.
        request: HTTP request (for audit IP).
        db: Database session.
        current_user: Authenticated superuser.

    Returns:
        New pricing entry.
    """
    # Find current active pricing
    stmt = select(ImageGenerationPricing).where(
        ImageGenerationPricing.id == pricing_id,
        ImageGenerationPricing.is_active,
    )
    result = await db.execute(stmt)
    current_pricing = result.scalars().first()

    if not current_pricing:
        raise_pricing_not_found(str(pricing_id))

    # Determine new values (use provided or keep original)
    new_model = data.model if data.model is not None else current_pricing.model
    new_quality = data.quality if data.quality is not None else current_pricing.quality
    new_size = data.size if data.size is not None else current_pricing.size

    # If key changed, check uniqueness
    key_changed = (
        new_model != current_pricing.model
        or new_quality != current_pricing.quality
        or new_size != current_pricing.size
    )
    if key_changed:
        conflict_stmt = select(ImageGenerationPricing).where(
            and_(
                ImageGenerationPricing.model == new_model,
                ImageGenerationPricing.quality == new_quality,
                ImageGenerationPricing.size == new_size,
                ImageGenerationPricing.is_active,
            )
        )
        conflict_result = await db.execute(conflict_stmt)
        if conflict_result.scalars().first():
            raise_invalid_input(
                f"Active pricing already exists for {new_model}/{new_quality}/{new_size}.",
            )

    # Deactivate old
    current_pricing.is_active = False

    # Create new version
    new_pricing = ImageGenerationPricing(
        model=new_model,
        quality=new_quality,
        size=new_size,
        cost_per_image_usd=data.cost_per_image_usd,
        is_active=True,
    )
    db.add(new_pricing)
    await db.commit()
    await db.refresh(new_pricing)

    # Audit log
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="image_pricing_updated",
        resource_type="image_generation_pricing",
        resource_id=new_pricing.id,
        details={
            "old_id": str(pricing_id),
            "model": new_pricing.model,
            "quality": new_pricing.quality,
            "size": new_pricing.size,
            "old_cost": float(current_pricing.cost_per_image_usd),
            "new_cost": float(new_pricing.cost_per_image_usd),
            "key_changed": key_changed,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "image_pricing_updated",
        old_id=str(pricing_id),
        new_id=str(new_pricing.id),
        model=new_model,
        quality=new_quality,
        size=new_size,
        admin_user_id=str(current_user.id),
    )

    return ImagePricingResponse.model_validate(new_pricing)


@router.delete("/pricing/{pricing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_pricing(
    pricing_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> None:
    """Deactivate image pricing (soft delete).

    Args:
        pricing_id: UUID of the pricing entry to deactivate.
        request: HTTP request (for audit IP).
        db: Database session.
        current_user: Authenticated superuser.
    """
    stmt = select(ImageGenerationPricing).where(ImageGenerationPricing.id == pricing_id)
    result = await db.execute(stmt)
    pricing = result.scalars().first()

    if not pricing:
        raise_pricing_not_found(str(pricing_id))

    pricing.is_active = False
    await db.commit()

    # Audit log
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="image_pricing_deactivated",
        resource_type="image_generation_pricing",
        resource_id=pricing.id,
        details={
            "model": pricing.model,
            "quality": pricing.quality,
            "size": pricing.size,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "image_pricing_deactivated",
        pricing_id=str(pricing_id),
        model=pricing.model,
        admin_user_id=str(current_user.id),
    )


@router.post("/pricing/reload-cache", status_code=status.HTTP_200_OK)
async def reload_pricing_cache(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> dict:
    """Reload the image generation pricing in-memory cache.

    Args:
        request: HTTP request (for audit IP).
        db: Database session.
        current_user: Authenticated superuser.

    Returns:
        Dict with cache statistics.
    """
    from src.domains.image_generation.pricing_service import ImageGenerationPricingService

    await ImageGenerationPricingService.invalidate_and_reload(db)

    cache_size = len(ImageGenerationPricingService._pricing_cache)

    # Audit log
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="image_pricing_cache_reloaded",
        resource_type="image_generation_pricing",
        resource_id=None,
        details={"cache_size": cache_size},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "image_pricing_cache_reloaded",
        cache_size=cache_size,
        admin_user_id=str(current_user.id),
    )

    return {"status": "ok", "cache_size": cache_size}
