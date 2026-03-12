"""
Test helpers for LLM domain.

Functions moved here from pricing_service.py (were dead code in production).
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domains.llm.models import LLMModelPricing

logger = structlog.get_logger(__name__)


def create_llm_pricing_entry(
    db: Session,
    model_name: str,
    input_price: Decimal,
    cached_input_price: Decimal | None,
    output_price: Decimal,
) -> LLMModelPricing:
    """
    Create a new LLM pricing entry in the database (TEST HELPER).

    Args:
        db: Database session
        model_name: LLM model identifier
        input_price: Price per 1M input tokens (USD)
        cached_input_price: Price per 1M cached input tokens (USD), None if not supported
        output_price: Price per 1M output tokens (USD)

    Returns:
        Created LLMModelPricing instance
    """
    pricing = LLMModelPricing(
        model_name=model_name,
        input_price_per_1m_tokens=input_price,
        cached_input_price_per_1m_tokens=cached_input_price,
        output_price_per_1m_tokens=output_price,
        effective_from=datetime.now(UTC),
        is_active=True,
    )

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
    stmt = select(LLMModelPricing).where(LLMModelPricing.id == pricing_id)
    pricing = db.scalars(stmt).first()

    if not pricing:
        raise ValueError(f"Pricing entry not found: {pricing_id}")

    pricing.is_active = False
    db.commit()

    logger.debug(
        "test_llm_pricing_deactivated",
        model_name=pricing.model_name,
        pricing_id=str(pricing_id),
    )
