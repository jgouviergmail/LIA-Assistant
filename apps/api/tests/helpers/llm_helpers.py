"""
Test helpers for LLM domain.

Functions moved here from pricing_service.py (were dead code in production).
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from src.domains.llm.models import LLMModel, LLMModelPricing, LLMProviderEnum, PricingUnitEnum

logger = structlog.get_logger(__name__)


def _ensure_llm_model_sync(
    db: Session,
    model_name: str,
    provider: LLMProviderEnum = LLMProviderEnum.openai,
) -> LLMModel:
    """Look up an LLMModel by name; create it with safe defaults if missing."""
    existing = db.scalar(select(LLMModel).where(LLMModel.model_name == model_name))
    if existing is not None:
        return existing
    model = LLMModel(model_name=model_name, provider=provider)
    db.add(model)
    db.flush()
    return model


async def ensure_llm_model_async(
    db: AsyncSession,
    model_name: str,
    provider: LLMProviderEnum = LLMProviderEnum.openai,
) -> LLMModel:
    """Async variant: look up an LLMModel by name; create it with safe defaults if missing.

    Tests that build a ``LLMModelPricing`` directly should call this first
    to obtain a valid ``model_id`` (``LLMModelPricing.model_id`` is NOT NULL).
    """
    existing = await db.scalar(select(LLMModel).where(LLMModel.model_name == model_name))
    if existing is not None:
        return existing
    model = LLMModel(model_name=model_name, provider=provider)
    db.add(model)
    await db.flush()
    return model


async def create_llm_pricing_async(
    db: AsyncSession,
    model_name: str,
    input_price: Decimal,
    output_price: Decimal,
    cached_input_price: Decimal | None = None,
    is_active: bool = True,
    provider: LLMProviderEnum = LLMProviderEnum.openai,
) -> LLMModelPricing:
    """Async TEST HELPER: create both an LLMModel (if missing) and a pricing row.

    Returns the pricing row with ``model`` relationship populated so
    ``pricing.model.model_name`` is safe to read without lazy-loading
    (LLMModelPricing.model uses lazy="raise").
    """
    model = await ensure_llm_model_async(db, model_name, provider)
    pricing = LLMModelPricing(
        model_id=model.id,
        input_unit_price=input_price,
        cached_input_unit_price=cached_input_price,
        output_unit_price=output_price,
        pricing_unit=PricingUnitEnum.per_1m_tokens,
        effective_from=datetime.now(UTC),
        is_active=is_active,
    )
    pricing.model = model
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)
    return pricing


def create_llm_pricing_entry(
    db: Session,
    model_name: str,
    input_price: Decimal,
    cached_input_price: Decimal | None,
    output_price: Decimal,
    provider: LLMProviderEnum = LLMProviderEnum.openai,
) -> LLMModelPricing:
    """
    Create a new LLM pricing entry in the database (TEST HELPER).

    Also ensures an ``LLMModel`` row exists for ``model_name`` (creates one
    with conservative defaults if missing) so the FK is satisfied.

    Args:
        db: Database session
        model_name: LLM model identifier (resolved to llm_models.id via FK)
        input_price: Price per 1M input tokens (USD)
        cached_input_price: Price per 1M cached input tokens (USD), None if not supported
        output_price: Price per 1M output tokens (USD)
        provider: Provider enum value (used only when creating the LLMModel row)

    Returns:
        Created LLMModelPricing instance with ``model`` relationship loaded.
    """
    model = _ensure_llm_model_sync(db, model_name, provider)

    pricing = LLMModelPricing(
        model_id=model.id,
        input_unit_price=input_price,
        cached_input_unit_price=cached_input_price,
        output_unit_price=output_price,
        pricing_unit=PricingUnitEnum.per_1m_tokens,
        effective_from=datetime.now(UTC),
        is_active=True,
    )
    pricing.model = model  # avoid lazy-load when the caller accesses pricing.model

    db.add(pricing)
    db.commit()
    db.refresh(pricing)

    logger.debug(
        "test_llm_pricing_created",
        model_name=model_name,
        input_price=float(input_price),
        output_price=float(output_price),
    )

    return pricing


def deactivate_llm_pricing(db: Session, pricing_id: str) -> None:
    """
    Deactivate an existing LLM pricing entry (soft delete) (TEST HELPER).

    Args:
        db: Database session
        pricing_id: UUID of the pricing entry to deactivate

    Raises:
        ValueError: If pricing entry not found
    """
    stmt = (
        select(LLMModelPricing)
        .options(selectinload(LLMModelPricing.model))
        .where(LLMModelPricing.id == pricing_id)
    )
    pricing = db.scalars(stmt).first()

    if not pricing:
        raise ValueError(f"Pricing entry not found: {pricing_id}")

    pricing.is_active = False
    db.commit()

    logger.debug(
        "test_llm_pricing_deactivated",
        model_name=pricing.model.model_name,
        pricing_id=str(pricing_id),
    )
