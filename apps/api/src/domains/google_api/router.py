"""
API routes for Google API pricing management (Admin only).

Provides CRUD operations for managing Google API endpoint pricing.
Follows the same pattern as LLM pricing admin routes.

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_invalid_input,
    raise_pricing_already_exists,
    raise_pricing_not_found,
)
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.google_api.models import GoogleApiPricing
from src.domains.google_api.schemas import (
    GoogleApiPricingCreate,
    GoogleApiPricingListResponse,
    GoogleApiPricingResponse,
    GoogleApiPricingUpdate,
)
from src.domains.users.models import AdminAuditLog

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/google-api",
    tags=["admin", "google-api"],
    dependencies=[Depends(get_current_superuser_session)],
)


@router.get("/pricing", response_model=GoogleApiPricingListResponse)
async def list_active_pricing(
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "api_name",
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> GoogleApiPricingListResponse:
    """
    List all active Google API pricing with pagination, search and sorting.

    **Requires**: Superuser privileges

    **Query Parameters**:
    - `search`: Filter by api_name or endpoint (case-insensitive partial match)
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)
    - `sort_by`: Column to sort by (api_name, endpoint, sku_name, cost_per_1000_usd)
    - `sort_order`: Sort order (asc or desc, default: asc)

    Returns paginated list of active pricing entries.
    """
    from src.core.pagination_helpers import (
        calculate_skip,
        calculate_total_pages,
        validate_pagination,
    )

    page, page_size = validate_pagination(page, page_size)
    offset = calculate_skip(page, page_size)

    # Build query with window function for total count
    stmt = select(
        GoogleApiPricing,
        func.count().over().label("total_count"),
    ).where(GoogleApiPricing.is_active.is_(True))

    # Apply search filter (search in api_name, endpoint, or sku_name)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (GoogleApiPricing.api_name.ilike(search_pattern))
            | (GoogleApiPricing.endpoint.ilike(search_pattern))
            | (GoogleApiPricing.sku_name.ilike(search_pattern))
        )

    # Apply sorting (whitelist for security - prevent column injection)
    ALLOWED_SORT_COLUMNS = {
        "api_name",
        "endpoint",
        "sku_name",
        "cost_per_1000_usd",
        "effective_from",
        "created_at",
    }

    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise_invalid_input(
            APIMessages.invalid_sort_parameter(list(ALLOWED_SORT_COLUMNS)),
            sort_by=sort_by,
            allowed=list(ALLOWED_SORT_COLUMNS),
        )

    sort_column = getattr(GoogleApiPricing, sort_by)
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(sort_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc())

    # Apply pagination
    stmt = stmt.limit(page_size).offset(offset)

    # Execute single query (count + data)
    result = await db.execute(stmt)
    rows = result.all()

    # Extract total and entries from window function result
    if rows:
        total = rows[0][1]
        pricing_list = [row[0] for row in rows]
    else:
        total = 0
        pricing_list = []

    total_pages = calculate_total_pages(total, page_size)

    logger.info(
        "google_api_pricing_list_retrieved",
        total_entries=total,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        admin_user_id=str(current_user.id),
    )

    return GoogleApiPricingListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        entries=[GoogleApiPricingResponse.model_validate(p) for p in pricing_list],
    )


@router.post(
    "/pricing", response_model=GoogleApiPricingResponse, status_code=status.HTTP_201_CREATED
)
async def create_pricing(
    data: GoogleApiPricingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> GoogleApiPricingResponse:
    """
    Create new Google API pricing entry.

    **Requires**: Superuser privileges

    Creates a new active pricing entry for an API endpoint.
    If pricing already exists for this api_name+endpoint, this will fail.
    Use PUT to update existing pricing.
    """
    # Check if active pricing already exists for this api_name + endpoint
    stmt = select(GoogleApiPricing).where(
        and_(
            GoogleApiPricing.api_name == data.api_name,
            GoogleApiPricing.endpoint == data.endpoint,
            GoogleApiPricing.is_active == True,  # noqa: E712
        )
    )
    existing = await db.execute(stmt)
    if existing.scalars().first():
        raise_pricing_already_exists(f"{data.api_name}:{data.endpoint}")

    # Create new pricing entry
    pricing = GoogleApiPricing(
        api_name=data.api_name,
        endpoint=data.endpoint,
        sku_name=data.sku_name,
        cost_per_1000_usd=data.cost_per_1000_usd,
        is_active=True,
    )

    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="google_api_pricing_created",
        resource_type="google_api_pricing",
        resource_id=pricing.id,
        details={
            "api_name": pricing.api_name,
            "endpoint": pricing.endpoint,
            "sku_name": pricing.sku_name,
            "cost_per_1000_usd": float(pricing.cost_per_1000_usd),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "google_api_pricing_created",
        api_name=data.api_name,
        endpoint=data.endpoint,
        sku_name=data.sku_name,
        cost_per_1000_usd=float(data.cost_per_1000_usd),
        admin_user_id=str(current_user.id),
        pricing_id=str(pricing.id),
    )

    return GoogleApiPricingResponse.model_validate(pricing)


@router.put("/pricing/{api_name}/{endpoint:path}", response_model=GoogleApiPricingResponse)
async def update_pricing(
    api_name: str,
    endpoint: str,
    data: GoogleApiPricingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> GoogleApiPricingResponse:
    """
    Update Google API pricing (creates new version, deactivates old).

    **Requires**: Superuser privileges

    **Path Parameters**:
    - `api_name`: Current API identifier (places, routes, geocoding, static_maps)
    - `endpoint`: Current endpoint path (URL-encoded if contains special chars)

    **Body Parameters** (optional for renaming):
    - `api_name`: New API identifier (if renaming)
    - `endpoint`: New endpoint path (if renaming)

    Deactivates the current active pricing and creates a new active entry.
    This maintains pricing history for audit purposes.
    If api_name/endpoint are provided in body, validates uniqueness before renaming.
    """
    # Find current active pricing
    stmt = select(GoogleApiPricing).where(
        and_(
            GoogleApiPricing.api_name == api_name,
            GoogleApiPricing.endpoint == endpoint,
            GoogleApiPricing.is_active == True,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    current_pricing = result.scalars().first()

    if not current_pricing:
        raise_pricing_not_found(f"{api_name}:{endpoint}")

    # Determine new api_name and endpoint (use provided or keep original)
    new_api_name = data.api_name if data.api_name is not None else api_name
    new_endpoint = data.endpoint if data.endpoint is not None else endpoint

    # If renaming, check uniqueness of new combination
    is_renaming = (new_api_name != api_name) or (new_endpoint != endpoint)
    if is_renaming:
        conflict_stmt = select(GoogleApiPricing).where(
            and_(
                GoogleApiPricing.api_name == new_api_name,
                GoogleApiPricing.endpoint == new_endpoint,
                GoogleApiPricing.is_active == True,  # noqa: E712
            )
        )
        conflict_result = await db.execute(conflict_stmt)
        if conflict_result.scalars().first():
            raise_pricing_already_exists(f"{new_api_name}:{new_endpoint}")

    # Deactivate current pricing
    current_pricing.is_active = False

    # Create new pricing entry
    new_pricing = GoogleApiPricing(
        api_name=new_api_name,
        endpoint=new_endpoint,
        sku_name=data.sku_name,
        cost_per_1000_usd=data.cost_per_1000_usd,
        is_active=True,
    )

    db.add(new_pricing)
    await db.commit()
    await db.refresh(new_pricing)

    # Create audit log entry
    audit_details = {
        "old_api_name": api_name,
        "old_endpoint": endpoint,
        "new_api_name": new_api_name,
        "new_endpoint": new_endpoint,
        "old_pricing_id": str(current_pricing.id),
        "new_pricing_id": str(new_pricing.id),
        "old_sku_name": current_pricing.sku_name,
        "new_sku_name": new_pricing.sku_name,
        "old_cost_per_1000_usd": float(current_pricing.cost_per_1000_usd),
        "new_cost_per_1000_usd": float(new_pricing.cost_per_1000_usd),
    }
    if is_renaming:
        audit_details["renamed"] = True

    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="google_api_pricing_updated",
        resource_type="google_api_pricing",
        resource_id=new_pricing.id,
        details=audit_details,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "google_api_pricing_updated",
        old_api_name=api_name,
        old_endpoint=endpoint,
        new_api_name=new_api_name,
        new_endpoint=new_endpoint,
        renamed=is_renaming,
        old_pricing_id=str(current_pricing.id),
        new_pricing_id=str(new_pricing.id),
        old_cost=float(current_pricing.cost_per_1000_usd),
        new_cost=float(new_pricing.cost_per_1000_usd),
        admin_user_id=str(current_user.id),
    )

    return GoogleApiPricingResponse.model_validate(new_pricing)


@router.delete("/pricing/{pricing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_pricing(
    pricing_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> None:
    """
    Deactivate Google API pricing (soft delete).

    **Requires**: Superuser privileges

    Sets is_active=False. Does not delete from database to maintain history.
    """
    stmt = select(GoogleApiPricing).where(GoogleApiPricing.id == pricing_id)
    result = await db.execute(stmt)
    pricing = result.scalars().first()

    if not pricing:
        raise_pricing_not_found(str(pricing_id))

    pricing.is_active = False
    await db.commit()

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="google_api_pricing_deactivated",
        resource_type="google_api_pricing",
        resource_id=pricing.id,
        details={
            "api_name": pricing.api_name,
            "endpoint": pricing.endpoint,
            "sku_name": pricing.sku_name,
            "pricing_id": str(pricing_id),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "google_api_pricing_deactivated",
        pricing_id=str(pricing_id),
        api_name=pricing.api_name,
        endpoint=pricing.endpoint,
        admin_user_id=str(current_user.id),
    )


@router.post("/pricing/reload-cache", status_code=status.HTTP_200_OK)
async def reload_pricing_cache(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> dict:
    """
    Reload the Google API pricing cache.

    **Requires**: Superuser privileges

    Reloads the in-memory pricing cache from the database.
    Use after creating/updating pricing to apply changes immediately.
    """
    from src.domains.google_api.pricing_service import GoogleApiPricingService

    await GoogleApiPricingService.load_pricing_cache(db)

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="google_api_pricing_cache_reloaded",
        resource_type="google_api_pricing",
        resource_id=None,
        details={"cache_entries": len(GoogleApiPricingService._pricing_cache)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "google_api_pricing_cache_reloaded",
        cache_entries=len(GoogleApiPricingService._pricing_cache),
        admin_user_id=str(current_user.id),
    )

    return {
        "status": "success",
        "message": "Pricing cache reloaded",
        "cache_entries": len(GoogleApiPricingService._pricing_cache),
    }


# ============================================================================
# CONSUMPTION EXPORT ENDPOINTS
# ============================================================================


@router.get("/export/token-usage")
async def export_token_usage(
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> StreamingResponse:
    """
    Export LLM token usage logs as CSV.

    **Requires**: Superuser privileges

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)
    - `user_id`: Filter by specific user (optional)

    Returns CSV file with token usage data.
    """
    from src.domains.google_api.export_service import export_token_usage_csv

    response, rows_count = await export_token_usage_csv(db, start_date, end_date, user_id)

    logger.info(
        "token_usage_exported",
        rows_count=rows_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(user_id) if user_id else None,
        admin_user_id=str(current_user.id),
    )

    return response


@router.get("/export/google-api-usage")
async def export_google_api_usage(
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> StreamingResponse:
    """
    Export Google API usage logs as CSV.

    **Requires**: Superuser privileges

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)
    - `user_id`: Filter by specific user (optional)

    Returns CSV file with Google API usage data.
    """
    from src.domains.google_api.export_service import export_google_api_usage_csv

    response, rows_count = await export_google_api_usage_csv(db, start_date, end_date, user_id)

    logger.info(
        "google_api_usage_exported",
        rows_count=rows_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(user_id) if user_id else None,
        admin_user_id=str(current_user.id),
    )

    return response


@router.get("/export/consumption-summary")
async def export_consumption_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> StreamingResponse:
    """
    Export aggregated consumption summary by user as CSV.

    **Requires**: Superuser privileges

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)
    - `user_id`: Filter by specific user (optional)

    Returns CSV file with per-user consumption totals.
    """
    from src.domains.google_api.export_service import export_consumption_summary_csv

    response, users_count = await export_consumption_summary_csv(db, start_date, end_date, user_id)

    logger.info(
        "consumption_summary_exported",
        users_count=users_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(user_id) if user_id else None,
        admin_user_id=str(current_user.id),
    )

    return response
