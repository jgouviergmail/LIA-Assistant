"""
Database models for LLM pricing and configuration.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import TimestampMixin
from src.infrastructure.database.session import Base


class LLMModelPricing(Base, TimestampMixin):
    """
    LLM model pricing configuration with temporal versioning.

    Stores pricing per million tokens for input, cached input, and output.
    Supports versioning through effective_from and is_active flags.

    Example:
        gpt-5:
            input_price_per_1m_tokens = 1.25 ($/1M tokens)
            cached_input_price_per_1m_tokens = 0.125 ($/1M tokens)
            output_price_per_1m_tokens = 10.00 ($/1M tokens)
    """

    __tablename__ = "llm_model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="LLM model identifier (e.g., 'gpt-5', 'o1-mini')",
    )

    input_price_per_1m_tokens: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 6),
        nullable=False,
        comment="Price in USD per 1 million input tokens",
    )

    cached_input_price_per_1m_tokens: Mapped[Decimal | None] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="Price in USD per 1M cached input tokens (NULL if not supported)",
    )

    output_price_per_1m_tokens: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 6),
        nullable=False,
        comment="Price in USD per 1 million output tokens",
    )

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Date from which this pricing is effective",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this pricing entry is currently active",
    )

    __table_args__ = (
        UniqueConstraint(
            "model_name",
            "effective_from",
            name="uq_model_effective_from",
        ),
        Index(
            "ix_llm_model_pricing_active_lookup",
            "model_name",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMModelPricing(model={self.model_name}, "
            f"input=${self.input_price_per_1m_tokens}/1M, "
            f"output=${self.output_price_per_1m_tokens}/1M, "
            f"active={self.is_active})>"
        )


class CurrencyExchangeRate(Base, TimestampMixin):
    """
    Currency exchange rates for cost conversion.

    Supports temporal versioning through effective_from and is_active.

    Example:
        USD -> EUR: rate = 0.95 (1 USD = 0.95 EUR)
    """

    __tablename__ = "currency_exchange_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    from_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
        comment="Source currency code (ISO 4217, e.g., 'USD')",
    )

    to_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
        comment="Target currency code (ISO 4217, e.g., 'EUR')",
    )

    rate: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 6),
        nullable=False,
        comment="Exchange rate (1 from_currency = rate to_currency)",
    )

    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Date from which this rate is effective",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this rate entry is currently active",
    )

    __table_args__ = (
        UniqueConstraint(
            "from_currency",
            "to_currency",
            "effective_from",
            name="uq_currency_pair_effective_from",
        ),
        Index(
            "ix_currency_exchange_rates_active_lookup",
            "from_currency",
            "to_currency",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CurrencyExchangeRate({self.from_currency}/{self.to_currency}={self.rate}, "
            f"active={self.is_active})>"
        )
