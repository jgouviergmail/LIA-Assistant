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
from src.core.reasoning_types import ReasoningBudgetRange
from src.core.session_dependencies import get_current_superuser_session
from src.domains.auth.models import User
from src.domains.llm.models import (
    CurrencyExchangeRate,
    LLMModel,
    LLMModelPricing,
)
from src.domains.llm.schemas import (
    CurrencyRateCreate,
    CurrencyRateResponse,
    CurrencyRatesListResponse,
    LLMPricingListResponse,
    ModelPriceCreate,
    ModelPriceResponse,
    ModelPriceUpdate,
    ReasoningTemplatesResponse,
)
from src.domains.llm.service import LLMModelService, UnknownReasoningTemplateError
from src.domains.users.models import AdminAuditLog
from src.infrastructure.cache.pricing_cache import PricingCacheService
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache


def _pricing_to_response(pricing: LLMModelPricing) -> ModelPriceResponse:
    """Build a ModelPriceResponse from a pricing row whose ``model`` is loaded.

    Flattens the llm_models row (provider + 8 capabilities + model_name) and
    the llm_model_pricing row (id + 3 prices + effective_from + is_active)
    into a single payload. Callers must have used
    ``selectinload(LLMModelPricing.model)`` (lazy="raise" enforces this).
    """
    model = pricing.model
    return ModelPriceResponse.model_validate(
        {
            # Pricing
            "id": pricing.id,
            "input_price_per_1m_tokens": pricing.input_price_per_1m_tokens,
            "cached_input_price_per_1m_tokens": pricing.cached_input_price_per_1m_tokens,
            "output_price_per_1m_tokens": pricing.output_price_per_1m_tokens,
            "effective_from": pricing.effective_from,
            "is_active": pricing.is_active,
            # Catalogue
            "provider": model.provider.value,
            "model_name": model.model_name,
            "max_input_tokens": model.max_input_tokens,
            "max_output_tokens": model.max_output_tokens,
            "supports_tools": model.supports_tools,
            "supports_structured_output": model.supports_structured_output,
            "supports_strict_mode": model.supports_strict_mode,
            "supports_streaming": model.supports_streaming,
            "supports_vision": model.supports_vision,
            "is_reasoning_model": model.is_reasoning_model,
            # Kind + reasoning widget + sampling caps
            "kind": model.kind.value,
            "reasoning_widget": model.reasoning_widget.value,
            "reasoning_enum_values": model.reasoning_enum_values,
            "reasoning_budget_range": (
                ReasoningBudgetRange.model_validate(model.reasoning_budget_range)
                if model.reasoning_budget_range is not None
                else None
            ),
            "reasoning_doc_i18n_key": model.reasoning_doc_i18n_key,
            "supports_temperature": model.supports_temperature,
            "supports_top_p": model.supports_top_p,
            "supports_frequency_penalty": model.supports_frequency_penalty,
            "supports_presence_penalty": model.supports_presence_penalty,
        }
    )


async def _invalidate_caches(db: AsyncSession) -> None:
    """Invalidate both pricing and model_capabilities caches cross-worker.

    Called after every llm_models / llm_model_pricing mutation so the new
    state propagates to the runtime hot path (pricing_cache,
    ModelCapabilitiesCache) and to all uvicorn workers via Redis Pub/Sub.
    """
    await ModelCapabilitiesCache.invalidate_and_reload(db)
    redis = await get_redis_cache()
    await PricingCacheService(redis).refresh_from_database()


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


@router.get("/reasoning-templates", response_model=ReasoningTemplatesResponse)
async def list_reasoning_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ReasoningTemplatesResponse:
    """List unique reasoning + sampling behaviors derived from existing models.

    **Requires**: Superuser privileges.

    Drives the admin Pricing form's "Copy behavior from..." selector. Each
    entry exposes one representative model_name plus the 9 reasoning +
    sampling fields that will be copied verbatim onto a newly added model
    when this template is picked. The set self-enriches: a model added in
    Custom mode with a novel fingerprint becomes available as a template
    on subsequent calls.
    """
    service = LLMModelService(db)
    templates = await service.list_templates()
    logger.info(
        "llm_reasoning_templates_listed",
        templates_count=len(templates),
        admin_user_id=str(current_user.id),
    )
    return ReasoningTemplatesResponse(templates=templates)


@router.post("/pricing", response_model=ModelPriceResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing(
    data: ModelPriceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> ModelPriceResponse:
    """Create a new LLM model + initial pricing in a single transaction.

    **Requires**: Superuser privileges.

    The payload carries the full 14-field catalogue:
    - provider (Literal[7])
    - model_name (globally unique)
    - 8 capability fields (max_input_tokens, max_output_tokens,
      supports_tools, supports_structured_output, supports_strict_mode,
      supports_streaming, supports_vision, is_reasoning_model)
    - 3 pricing fields (input/cached_input/output per 1M tokens)

    Inserts both an ``llm_models`` row and an active ``llm_model_pricing``
    row pointing to it. Rejects if the ``model_name`` already exists.
    """
    service = LLMModelService(db)
    try:
        model, pricing = await service.create(data)
    except UnknownReasoningTemplateError as exc:
        # Unknown reasoning_template — surface a 400 with the original
        # message so the admin sees which template name was wrong.
        raise_invalid_input(str(exc))
    except ValueError:
        raise_pricing_already_exists(data.model_name)

    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_model_created",
        resource_type="llm_models",
        resource_id=model.id,
        details={
            FIELD_MODEL_NAME: model.model_name,
            "provider": model.provider.value,
            "kind": model.kind.value,
            # Trace which reasoning template (if any) the new row inherits
            # from. Snapshot semantics: the value is captured at creation
            # time and persisted on the row even if the template later
            # changes — but the source choice is preserved here.
            "reasoning_template": data.reasoning_template,
            "reasoning_widget": model.reasoning_widget.value,
            "input_price_per_1m_tokens": float(pricing.input_price_per_1m_tokens),
            "output_price_per_1m_tokens": float(pricing.output_price_per_1m_tokens),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()
    # Do NOT call db.refresh(pricing) here: refresh re-reads ALL attributes
    # from the DB and clears the manually-set pricing.model relationship,
    # which would crash _pricing_to_response() against lazy="raise".

    # Cross-worker invalidation so Configuration LLM + runtime see the new model.
    await _invalidate_caches(db)

    logger.info(
        "llm_model_created",
        model_name=model.model_name,
        provider=model.provider.value,
        kind=model.kind.value,
        reasoning_template=data.reasoning_template,
        reasoning_widget=model.reasoning_widget.value,
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
    """Partial update of capabilities and/or pricing for an LLM model.

    **Requires**: Superuser privileges.

    The service layer differentiates three cases:
    - capabilities only → mutate ``llm_models`` in place
    - pricing only → temporal versioning on ``llm_model_pricing``
      (deactivate old active row, insert new active row)
    - mixed → both, in one transaction

    The optional ``model_name`` body field renames the model (in place on
    ``llm_models``). Conflicts return 409.
    """
    service = LLMModelService(db)
    try:
        model, new_pricing = await service.update(model_name, data)
    except UnknownReasoningTemplateError as exc:
        # Unknown reasoning_template — 400 with the original message so the
        # admin sees which template name was wrong. Caught BEFORE plain
        # LookupError because UnknownReasoningTemplateError subclasses it.
        raise_invalid_input(str(exc))
    except LookupError:
        raise_pricing_not_found(model_name)
    except ValueError:
        # Rename target conflicts with an existing model.
        target = data.model_name or model_name
        raise_pricing_already_exists(target)

    # Resolve the active pricing for the response (may be the existing row
    # if the update only touched capabilities or only renamed the model).
    response_pricing = new_pricing or await service.get_active_pricing_for(model.id)
    if response_pricing is None:
        # Defensive: a model with no active pricing should not happen post-update,
        # but signal it explicitly rather than 500'ing on _pricing_to_response.
        raise_pricing_not_found(model.model_name)

    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_model_updated",
        resource_type="llm_models",
        resource_id=model.id,
        details={
            "model_name": model.model_name,
            "renamed_from": model_name if model.model_name != model_name else None,
            "changed_fields": sorted(data.model_dump(exclude_unset=True, exclude_none=True).keys()),
            # Trace which reasoning template (if any) was applied in this
            # update — the field value comes from the request payload, not
            # from the persisted row (the row only stores the resolved
            # shape, not the template name).
            "reasoning_template": data.reasoning_template,
            # Post-update reasoning shape + kind for forensic search.
            "kind": model.kind.value,
            "reasoning_widget": model.reasoning_widget.value,
            "new_pricing_id": str(new_pricing.id) if new_pricing else None,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    await _invalidate_caches(db)

    logger.info(
        "llm_model_updated",
        old_model_name=model_name,
        new_model_name=model.model_name,
        kind=model.kind.value,
        reasoning_template=data.reasoning_template,
        reasoning_widget=model.reasoning_widget.value,
        new_pricing_id=str(new_pricing.id) if new_pricing else None,
        admin_user_id=str(current_user.id),
    )
    return _pricing_to_response(response_pricing)


@router.delete("/pricing/{pricing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_pricing(
    pricing_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> None:
    """Soft-delete a model and its active pricing row (atomically).

    **Requires**: Superuser privileges.

    The path parameter is a ``pricing_id`` for backward compatibility with the
    existing frontend; the service layer resolves it to the parent model and
    deactivates BOTH (model + active pricing). Past conversations keep their
    cost history because the deactivated pricing row is preserved.
    """
    # Resolve pricing → model_name so we can call service.deactivate(name).
    stmt = (
        select(LLMModelPricing)
        .options(selectinload(LLMModelPricing.model))
        .where(LLMModelPricing.id == pricing_id)
    )
    pricing = await db.scalar(stmt)
    if pricing is None or pricing.model is None:
        raise_pricing_not_found(str(pricing_id))

    model_name = pricing.model.model_name
    model_id = pricing.model.id

    service = LLMModelService(db)
    try:
        await service.deactivate(model_name)
    except LookupError:
        raise_pricing_not_found(model_name)

    audit_entry = AdminAuditLog(
        admin_user_id=str(current_user.id),
        action="llm_model_deactivated",
        resource_type="llm_models",
        resource_id=model_id,
        details={
            FIELD_MODEL_NAME: model_name,
            "pricing_id": str(pricing_id),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_entry)
    await db.commit()

    await _invalidate_caches(db)

    logger.info(
        "llm_model_deactivated",
        pricing_id=str(pricing_id),
        model_name=model_name,
        admin_user_id=str(current_user.id),
    )


@router.post("/pricing/reload-cache", status_code=status.HTTP_200_OK)
async def reload_pricing_cache(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> dict:
    """Reload BOTH the LLM pricing cache and the model capabilities cache.

    **Requires**: Superuser privileges.

    Reloads the in-memory + Redis pricing cache and the in-memory model
    capabilities cache from the database, then publishes a cross-worker
    invalidation so all uvicorn workers refresh.

    Use after manual DB edits, or to recover from a stale cache without
    waiting for TTL expiration.
    """
    from src.infrastructure.cache.pricing_cache import (
        PricingCacheService,
        get_cache_stats,
    )
    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    pricing_service = PricingCacheService(redis)

    # Invalidate + refresh the pricing cache (Redis-backed)
    await pricing_service.invalidate()
    success = await pricing_service.refresh_from_database()
    if not success:
        raise_invalid_input("Failed to refresh pricing cache from database")

    # Invalidate + refresh the model_capabilities cache (in-memory + Pub/Sub)
    await ModelCapabilitiesCache.invalidate_and_reload(db)

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
