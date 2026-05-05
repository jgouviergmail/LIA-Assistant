"""
API routes for LLM pricing management (Admin only).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.dependencies import get_db
from src.core.exceptions import (
    raise_invalid_input,
    raise_pricing_already_exists,
    raise_pricing_not_found,
)
from src.core.field_names import FIELD_MODEL_NAME
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.llm.models import (
    CurrencyExchangeRate,
    LLMModel,
    LLMModelPricing,
    LLMProviderEnum,
)
from src.domains.llm.schemas import (
    CurrencyRateCreate,
    CurrencyRateResponse,
    CurrencyRatesListResponse,
    LLMPricingListResponse,
    ModelPriceCreate,
    ModelPriceResponse,
    ModelPriceUpdate,
)
from src.domains.users.models import AdminAuditLog


def _pricing_to_response(pricing: LLMModelPricing) -> ModelPriceResponse:
    """Build a ModelPriceResponse from a pricing row whose ``model`` is loaded.

    The legacy ``LLMModelPricing.model_name`` column was dropped; the model
    name now lives on the related ``LLMModel`` row. Callers must have used
    ``selectinload(LLMModelPricing.model)`` (lazy="raise" enforces this).
    """
    return ModelPriceResponse.model_validate(
        {
            "id": pricing.id,
            "model_name": pricing.model.model_name,
            "input_price_per_1m_tokens": pricing.input_price_per_1m_tokens,
            "cached_input_price_per_1m_tokens": pricing.cached_input_price_per_1m_tokens,
            "output_price_per_1m_tokens": pricing.output_price_per_1m_tokens,
            "effective_from": pricing.effective_from,
            "is_active": pricing.is_active,
        }
    )


async def _ensure_llm_model(
    db: AsyncSession, model_name: str, provider: LLMProviderEnum = LLMProviderEnum.openai
) -> LLMModel:
    """Look up a model by name, creating a conservative-defaults row if missing.

    Used by the legacy admin POST endpoint which only carries ``model_name``.
    Task 10 refactors the endpoint to take all 14 catalogue fields explicitly;
    until then, new models are created with safe default capabilities and the
    admin can refine them via Task 13's enriched form.
    """
    existing = await db.scalar(select(LLMModel).where(LLMModel.model_name == model_name))
    if existing is not None:
        return existing
    model = LLMModel(model_name=model_name, provider=provider)
    db.add(model)
    await db.flush()
    return model


logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/llm",
    tags=["admin", "llm"],
    dependencies=[Depends(get_current_superuser_session)],
)


@router.get("/pricing", response_model=LLMPricingListResponse)
async def list_active_pricing(
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = "model_name",
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> LLMPricingListResponse:
    """
    List all active LLM model pricing with pagination, search and sorting.

    **Requires**: Superuser privileges

    **Query Parameters**:
    - `search`: Filter by model name (case-insensitive partial match)
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 10, max: 100)
    - `sort_by`: Column to sort by (model_name, input_price_per_1m_tokens, output_price_per_1m_tokens)
    - `sort_order`: Sort order (asc or desc, default: asc)

    Returns paginated list of active pricing entries.
    """
    # Validate pagination parameters and calculate offset
    from src.core.pagination_helpers import calculate_skip, validate_pagination

    page, page_size = validate_pagination(page, page_size)
    offset = calculate_skip(page, page_size)

    # ========================================================================
    # OPTIMIZED PAGINATION WITH WINDOW FUNCTION (Single Query)
    # ========================================================================
    # Uses SQLAlchemy window function to get total count in same query
    # Performance improvement: ~30-50% vs. separate COUNT query
    # Guarantees consistency (count and data at same instant)
    # ========================================================================
    from sqlalchemy import func

    # Build query with window function for total count.
    # The OVER() clause computes total across all rows (before LIMIT).
    # JOIN llm_models so we can search/sort by model_name (now stored there)
    # and selectinload eagerly fetches the relationship for response building.
    stmt = (
        select(
            LLMModelPricing,
            func.count().over().label("total_count"),
        )
        .join(LLMModelPricing.model)
        .options(selectinload(LLMModelPricing.model))
        .where(LLMModelPricing.is_active)
    )

    # Apply search filter (model_name lives on llm_models)
    if search:
        stmt = stmt.where(LLMModel.model_name.ilike(f"%{search}%"))

    # Apply sorting (whitelist for security - prevent column injection)
    ALLOWED_SORT_COLUMNS = {
        "model_name",
        "input_price_per_1m_tokens",
        "output_price_per_1m_tokens",
        "created_at",
        "updated_at",
    }

    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise_invalid_input(
            APIMessages.invalid_sort_parameter(list(ALLOWED_SORT_COLUMNS)),
            sort_by=sort_by,
            allowed=list(ALLOWED_SORT_COLUMNS),
        )

    # model_name is on LLMModel; the rest are still on LLMModelPricing.
    if sort_by == "model_name":
        sort_column = LLMModel.model_name
    else:
        sort_column = getattr(LLMModelPricing, sort_by)
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(sort_column.desc())
    else:
        stmt = stmt.order_by(sort_column.asc())

    # Apply pagination
    stmt = stmt.limit(page_size).offset(offset)

    # Execute single query (count + data)
    result = await db.execute(stmt)
    rows = result.all()

    # Extract total and models from window function result
    # Window function returns tuples: (LLMModelPricing, total_count)
    if rows:
        total = rows[0][1]  # total_count from first row (same for all rows)
        pricing_list = [row[0] for row in rows]  # Extract model objects
    else:
        total = 0
        pricing_list = []

    # Calculate total pages
    from src.core.pagination_helpers import calculate_total_pages

    total_pages = calculate_total_pages(total, page_size)

    logger.info(
        "llm_pricing_list_retrieved",
        total_models=total,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        admin_user_id=str(current_user.id),
    )

    return LLMPricingListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        models=[_pricing_to_response(p) for p in pricing_list],
    )


@router.post("/pricing", response_model=ModelPriceResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing(
    data: ModelPriceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ModelPriceResponse:
    """
    Create new LLM model pricing entry.

    **Requires**: Superuser privileges

    Creates a new active pricing entry. If model already has active pricing,
    this endpoint will fail. Use PUT /{id} to update existing pricing.
    """
    # Resolve (or create) the LLMModel for this name. The legacy POST contract
    # only carries model_name; Task 10 will introduce a richer schema with all
    # 14 catalogue fields. For now, _ensure_llm_model creates a row with safe
    # defaults if needed.
    model = await _ensure_llm_model(db, data.model_name)

    # Reject if an active pricing row already exists for this model.
    existing = await db.scalar(
        select(LLMModelPricing).where(
            LLMModelPricing.model_id == model.id,
            LLMModelPricing.is_active,
        )
    )
    if existing is not None:
        raise_pricing_already_exists(data.model_name)

    # Create new pricing entry
    pricing = LLMModelPricing(
        model_id=model.id,
        input_price_per_1m_tokens=data.input_price_per_1m_tokens,
        cached_input_price_per_1m_tokens=data.cached_input_price_per_1m_tokens,
        output_price_per_1m_tokens=data.output_price_per_1m_tokens,
        is_active=True,
    )
    pricing.model = model  # avoid lazy-load when reading model.model_name later

    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_pricing_created",
        resource_type="llm_model_pricing",
        resource_id=pricing.id,
        details={
            FIELD_MODEL_NAME: model.model_name,
            "input_price_per_1m_tokens": float(pricing.input_price_per_1m_tokens),
            "cached_input_price_per_1m_tokens": (
                float(pricing.cached_input_price_per_1m_tokens)
                if pricing.cached_input_price_per_1m_tokens
                else None
            ),
            "output_price_per_1m_tokens": float(pricing.output_price_per_1m_tokens),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "llm_pricing_created",
        model_name=data.model_name,
        admin_user_id=str(current_user.id),
        pricing_id=str(pricing.id),
    )

    return _pricing_to_response(pricing)


@router.put("/pricing/{model_name}", response_model=ModelPriceResponse)
async def update_pricing(
    model_name: str,
    data: ModelPriceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ModelPriceResponse:
    """
    Update LLM model pricing (creates new version, deactivates old).

    **Requires**: Superuser privileges

    **Path Parameters**:
    - `model_name`: Current model identifier

    **Body Parameters** (optional for renaming):
    - `model_name`: New model identifier (if renaming)

    Deactivates the current active pricing and creates a new active entry
    with updated prices. This maintains pricing history.
    If model_name is provided in body, validates uniqueness before renaming.
    """
    # Find the current active pricing via JOIN on llm_models (model_name lives there).
    stmt = (
        select(LLMModelPricing)
        .join(LLMModelPricing.model)
        .options(selectinload(LLMModelPricing.model))
        .where(
            LLMModel.model_name == model_name,
            LLMModelPricing.is_active,
        )
    )
    current_pricing = await db.scalar(stmt)

    if current_pricing is None:
        raise_pricing_not_found(model_name)

    model = current_pricing.model

    # Determine new model_name (use provided or keep original).
    new_model_name = data.model_name if data.model_name is not None else model_name

    # If renaming, check uniqueness against the llm_models catalogue.
    is_renaming = new_model_name != model_name
    if is_renaming:
        conflict = await db.scalar(select(LLMModel).where(LLMModel.model_name == new_model_name))
        if conflict is not None:
            raise_pricing_already_exists(new_model_name)
        # Rename in place on llm_models — the FK on the new pricing row stays valid.
        model.model_name = new_model_name

    # Deactivate current pricing (temporal versioning).
    current_pricing.is_active = False

    # Create new pricing entry pointing to the same model.
    new_pricing = LLMModelPricing(
        model_id=model.id,
        input_price_per_1m_tokens=data.input_price_per_1m_tokens,
        cached_input_price_per_1m_tokens=data.cached_input_price_per_1m_tokens,
        output_price_per_1m_tokens=data.output_price_per_1m_tokens,
        is_active=True,
    )
    new_pricing.model = model  # avoid lazy-load when reading model.model_name later

    db.add(new_pricing)
    await db.commit()
    await db.refresh(new_pricing)

    # Create audit log entry
    audit_details = {
        "old_model_name": model_name,
        "new_model_name": new_model_name,
        "old_pricing_id": str(current_pricing.id),
        "new_pricing_id": str(new_pricing.id),
        "old_input_price": float(current_pricing.input_price_per_1m_tokens),
        "new_input_price": float(new_pricing.input_price_per_1m_tokens),
        "old_output_price": float(current_pricing.output_price_per_1m_tokens),
        "new_output_price": float(new_pricing.output_price_per_1m_tokens),
    }
    if is_renaming:
        audit_details["renamed"] = True

    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_pricing_updated",
        resource_type="llm_model_pricing",
        resource_id=new_pricing.id,
        details=audit_details,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "llm_pricing_updated",
        old_model_name=model_name,
        new_model_name=new_model_name,
        renamed=is_renaming,
        old_pricing_id=str(current_pricing.id),
        new_pricing_id=str(new_pricing.id),
        admin_user_id=str(current_user.id),
    )

    return _pricing_to_response(new_pricing)


@router.delete("/pricing/{pricing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_pricing(
    pricing_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> None:
    """
    Deactivate LLM model pricing (soft delete).

    **Requires**: Superuser privileges

    Sets is_active=False. Does not delete from database to maintain history.
    """
    # Eager-load the catalogue row so we can read model.model_name for the audit log.
    stmt = (
        select(LLMModelPricing)
        .options(selectinload(LLMModelPricing.model))
        .where(LLMModelPricing.id == pricing_id)
    )
    pricing = await db.scalar(stmt)

    if pricing is None:
        raise_pricing_not_found(str(pricing_id))

    pricing.is_active = False
    await db.commit()

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_pricing_deactivated",
        resource_type="llm_model_pricing",
        resource_id=pricing.id,
        details={
            FIELD_MODEL_NAME: pricing.model.model_name,
            "pricing_id": str(pricing_id),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "llm_pricing_deactivated",
        pricing_id=str(pricing_id),
        model_name=pricing.model.model_name,
        admin_user_id=str(current_user.id),
    )


@router.post("/pricing/reload-cache", status_code=status.HTTP_200_OK)
async def reload_pricing_cache(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> dict:
    """
    Reload the LLM pricing cache.

    **Requires**: Superuser privileges

    Reloads the in-memory and Redis pricing cache from the database.
    Use after creating/updating pricing to apply changes immediately
    without waiting for TTL expiration.
    """
    from src.infrastructure.cache.pricing_cache import (
        PricingCacheService,
        get_cache_stats,
    )
    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    service = PricingCacheService(redis)

    # Invalidate existing cache and refresh from database
    await service.invalidate()
    success = await service.refresh_from_database()

    if not success:
        raise_invalid_input("Failed to refresh pricing cache from database")

    stats = get_cache_stats()

    # Create audit log entry
    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_pricing_cache_reloaded",
        resource_type="llm_model_pricing",
        resource_id=None,
        details={"cache_stats": stats},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    logger.info(
        "llm_pricing_cache_reloaded",
        models_count=stats.get("models_count", 0),
        admin_user_id=str(current_user.id),
    )

    return {
        "status": "success",
        "message": "Pricing cache reloaded",
        "cache_stats": stats,
    }


@router.get("/currencies", response_model=CurrencyRatesListResponse)
async def list_active_currency_rates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> CurrencyRatesListResponse:
    """
    List all active currency exchange rates.

    **Requires**: Superuser privileges
    """
    stmt = (
        select(CurrencyExchangeRate)
        .where(CurrencyExchangeRate.is_active)
        .order_by(CurrencyExchangeRate.from_currency, CurrencyExchangeRate.to_currency)
    )

    result = await db.execute(stmt)
    rates_list = result.scalars().all()

    logger.info(
        "currency_rates_list_retrieved",
        total_rates=len(rates_list),
        admin_user_id=str(current_user.id),
    )

    return CurrencyRatesListResponse(
        total=len(rates_list),
        rates=[CurrencyRateResponse.model_validate(r) for r in rates_list],
    )


@router.post(
    "/currencies", response_model=CurrencyRateResponse, status_code=status.HTTP_201_CREATED
)
async def create_currency_rate(
    data: CurrencyRateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> CurrencyRateResponse:
    """
    Create new currency exchange rate.

    **Requires**: Superuser privileges

    Creates a new active exchange rate. If rate already exists for this pair,
    the old one will be deactivated and replaced.
    """
    # Check if active rate already exists for this currency pair
    stmt = select(CurrencyExchangeRate).where(
        CurrencyExchangeRate.from_currency == data.from_currency,
        CurrencyExchangeRate.to_currency == data.to_currency,
        CurrencyExchangeRate.is_active,
    )
    result = await db.execute(stmt)
    existing_rate = result.scalars().first()

    if existing_rate:
        # Deactivate existing rate
        existing_rate.is_active = False
        logger.info(
            "currency_rate_replaced",
            from_currency=data.from_currency,
            to_currency=data.to_currency,
            old_rate=float(existing_rate.rate),
            new_rate=float(data.rate),
        )

    # Create new rate
    new_rate = CurrencyExchangeRate(
        from_currency=data.from_currency.upper(),
        to_currency=data.to_currency.upper(),
        rate=data.rate,
        is_active=True,
    )

    db.add(new_rate)
    await db.commit()
    await db.refresh(new_rate)

    logger.info(
        "currency_rate_created",
        from_currency=data.from_currency,
        to_currency=data.to_currency,
        rate=float(data.rate),
        admin_user_id=str(current_user.id),
    )

    return CurrencyRateResponse.model_validate(new_rate)
