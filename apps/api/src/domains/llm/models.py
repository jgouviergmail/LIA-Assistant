"""
Database models for LLM pricing and configuration.
"""

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DECIMAL,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import TimestampMixin, UUIDMixin
from src.infrastructure.database.session import Base


class LLMProviderEnum(str, enum.Enum):
    """Supported LLM providers.

    Must stay in sync with ``LLM_PROVIDERS`` in
    :mod:`src.domains.llm_config.constants`.
    """

    openai = "openai"
    anthropic = "anthropic"
    deepseek = "deepseek"
    perplexity = "perplexity"
    ollama = "ollama"
    gemini = "gemini"
    qwen = "qwen"
    elevenlabs = "elevenlabs"
    edge = "edge"


class PricingUnitEnum(str, enum.Enum):
    """Billing unit for an LLMModelPricing row.

    Disambiguates the semantics of the unit-price columns:
    - ``per_1m_tokens``: price per 1 million tokens (default; LLM chat/text).
    - ``per_audio_minute``: price per minute of audio transcribed/synthesised.
    - ``per_audio_hour``: price per hour of audio (e.g. ElevenLabs Scribe at
      $0.22/hour). Stored verbatim for auditable refacturing.
    """

    per_1m_tokens = "per_1m_tokens"
    per_audio_minute = "per_audio_minute"
    per_audio_hour = "per_audio_hour"


class LLMModelKindEnum(str, enum.Enum):
    """Classifies a model's nature for UI filtering and capability surface.

    A given LLM type ('router', 'image_generation', ...) requires a specific
    kind via LLMTypeMetadata.required_kind. The Configuration LLM admin UI
    filters its model dropdown via the GET /llm-config/metadata?kinds= query
    parameter so the admin only sees models compatible with the LLM type
    being edited.
    """

    chat = "chat"
    image = "image"
    audio = "audio"
    realtime = "realtime"
    tts = "tts"
    embedding = "embedding"


class LLMReasoningWidgetEnum(str, enum.Enum):
    """Drives the frontend rendering of the reasoning_effort selector.

    Single source of truth: each row of llm_models declares which widget the
    Configuration LLM dialog must render for this model. The frontend has no
    regex / hardcoded list — it dispatches purely on this value.
    """

    none = "none"  # model does not accept reasoning_effort
    enum = "enum"  # API accepts a string enum (use reasoning_enum_values)
    budget_int = "budget_int"  # API accepts only a numeric budget (use reasoning_budget_range)
    toggle_budget = "toggle_budget"  # API accepts boolean toggle + numeric budget (Qwen3 hybrid)


class LLMModel(Base, UUIDMixin, TimestampMixin):
    """LLM model catalogue with capability metadata.

    Mutated in place (no temporal versioning at this layer). Pricing lives in
    :class:`LLMModelPricing` (FK below) and remains temporally versioned.

    Example:
        gpt-4.1-mini, openai, max_output=16384, supports_tools=True, ...
    """

    __tablename__ = "llm_models"

    provider: Mapped[LLMProviderEnum] = mapped_column(
        SQLEnum(
            LLMProviderEnum,
            name="llm_provider_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        index=True,
        comment="Provider that hosts this model",
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,  # creates a unique index, no separate index= needed
        comment="Globally unique model identifier (e.g., 'gpt-4.1-mini')",
    )

    max_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_strict_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_reasoning_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Per-model sampling parameter acceptance (added 2026-05-06).
    # Drives the Configuration LLM admin UI conditional rendering of sampling
    # inputs (philosophy A — "raw truth": the UI shows only what the API
    # accepts). Defaults are permissive (True) so unknown models stay editable
    # and the explicit per-model matrix downgrades when needed.
    supports_temperature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_top_p: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_frequency_penalty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_presence_penalty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # NEW (2026-05-06): model classification + reasoning UI driver.
    # See docs/superpowers/specs/2026-05-06-llm-reasoning-effort-overhaul-design.md
    kind: Mapped[LLMModelKindEnum] = mapped_column(
        SQLEnum(
            LLMModelKindEnum,
            name="llm_model_kind_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMModelKindEnum.chat,
        comment="Model nature (chat / image / audio / realtime / tts / embedding)",
    )

    reasoning_widget: Mapped[LLMReasoningWidgetEnum] = mapped_column(
        SQLEnum(
            LLMReasoningWidgetEnum,
            name="llm_reasoning_widget_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMReasoningWidgetEnum.none,
        comment="UI widget shape for reasoning_effort selection",
    )

    reasoning_enum_values: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered list of accepted reasoning_effort string values (when reasoning_widget='enum')",
    )

    reasoning_budget_range: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            '{"min":int,"max":int,"off_sentinel":int|null,"dynamic_sentinel":int|null} '
            'when reasoning_widget in ("budget_int","toggle_budget")'
        ),
    )

    reasoning_doc_i18n_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Frontend lookup key in REASONING_DOC_TEXT constant table (English-only)",
    )

    effort_values: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Allowed values for a separate global 'effort' control (Anthropic "
            "output_config.effort), distinct from reasoning_effort. NULL = the "
            "model has no separate effort field. Currently only claude-opus-4-5."
        ),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this model is currently selectable (no index: low cardinality)",
    )

    # cascade kept narrow on purpose: the FK uses ON DELETE RESTRICT, so we
    # never want the ORM to attempt cascading deletes (would race with the DB
    # constraint and emit IntegrityError). Use lazy="raise" to make any N+1
    # access fail loud — callers must use selectinload(LLMModel.pricings).
    pricings: Mapped[list["LLMModelPricing"]] = relationship(
        "LLMModelPricing",
        back_populates="model",
        cascade="save-update, merge",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<LLMModel(name={self.model_name}, "
            f"provider={self.provider.value}, active={self.is_active})>"
        )


class LLMModelPricing(Base, TimestampMixin):
    """
    LLM model pricing configuration with temporal versioning.

    Stores unit prices for input, cached input, and output. The semantic of
    the unit is given by ``pricing_unit``:
      - ``per_1m_tokens``: price per 1 million tokens (LLM chat/text).
      - ``per_audio_minute``: price per minute of audio.
      - ``per_audio_hour``: price per hour of audio.
    Supports versioning through effective_from and is_active flags.

    Examples:
        gpt-5 (text)::
            pricing_unit             = per_1m_tokens
            input_unit_price         = 1.25  ($/1M input tokens)
            cached_input_unit_price  = 0.125 ($/1M cached input tokens)
            output_unit_price        = 10.00 ($/1M output tokens)

        ElevenLabs Scribe v2 (STT)::
            pricing_unit             = per_audio_hour
            input_unit_price         = 0.22  ($/hour of audio)
            cached_input_unit_price  = NULL
            output_unit_price        = 0     (no token output billed)
    """

    __tablename__ = "llm_model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # FK to the model catalogue. Use `pricing.model.model_name` to recover
    # the model identifier (callers must add selectinload(LLMModelPricing.model)
    # to their queries — lazy="raise" enforces this at runtime).
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="FK to llm_models.id",
    )

    model: Mapped["LLMModel"] = relationship(
        "LLMModel",
        back_populates="pricings",
        lazy="raise",
    )

    input_unit_price: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 6),
        nullable=False,
        comment="Input unit price in USD (semantic = pricing_unit)",
    )

    cached_input_unit_price: Mapped[Decimal | None] = mapped_column(
        DECIMAL(10, 6),
        nullable=True,
        comment="Cached input unit price in USD (NULL if not supported; semantic = pricing_unit)",
    )

    output_unit_price: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 6),
        nullable=False,
        comment="Output unit price in USD (semantic = pricing_unit; 0 for STT models)",
    )

    pricing_unit: Mapped[PricingUnitEnum] = mapped_column(
        SQLEnum(
            PricingUnitEnum,
            name="pricing_unit_enum",
            create_constraint=True,
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=PricingUnitEnum.per_1m_tokens,
        server_default=PricingUnitEnum.per_1m_tokens.value,
        comment="Billing unit semantics for the unit-price columns",
    )

    time_slots: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Optional UTC time-based tariff (ADR-223): list of "
            '{"start_utc":"HH:MM","end_utc":"HH:MM","input_unit_price":float,'
            '"cached_input_unit_price":float|null,"output_unit_price":float}. '
            "[start,end) at minute granularity, end < start wraps midnight, "
            "windows must not overlap. NULL/[] = flat pricing (base columns "
            "apply 24/7); a slot overrides all three unit prices while "
            "active. Only meaningful for pricing_unit='per_1m_tokens'."
        ),
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
            "model_id",
            "effective_from",
            name="uq_pricing_model_effective",
        ),
        Index(
            "ix_llm_model_pricing_active_lookup",
            "model_id",
            "is_active",
        ),
    )

    def __repr__(self) -> str:
        # Avoid touching self.model (lazy="raise" would crash without selectinload).
        return (
            f"<LLMModelPricing(model_id={self.model_id}, "
            f"unit={self.pricing_unit.value}, "
            f"input=${self.input_unit_price}, "
            f"output=${self.output_unit_price}, "
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
