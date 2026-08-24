"""
Database models for LLM pricing and configuration.
"""

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
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


class LLMCapabilityProvenanceEnum(str, enum.Enum):
    """Which authority filled a model row's capability fields.

    Measured 2026-08-23: 89 of 114 active rows carried the column defaults
    (``max_input_tokens=8192 / max_output_tokens=4096``), so
    ``get_effective_context_window`` returned 8 192 for ``gpt-5.2`` against a
    real 272 000. Provenance is what lets the runtime tell a measurement from a
    default, instead of trusting both equally.

    **SCOPE -- read this before arbitrating a new column on it.** The value is
    row-level; the evidence behind it is field-level.

    - ``imported`` vouches for the columns the vendored registries publish, and
      those only: exactly ``sync_diff.CORRECTABLE_FIELDS``
      (``max_input_tokens``, ``max_output_tokens``, ``supports_tools``,
      ``supports_structured_output``, ``supports_vision``). Every other column
      keeps whatever it had, and ``imported`` says nothing about it.
    - ``verified`` vouches for the whole row: a human edited it through
      ``LLMModelService.update``.

    Measured 2026-08-24, the trap this warning exists for: 41 active OpenAI rows
    are ``imported`` while still carrying an unfilled
    ``supports_strict_mode=false`` -- a column no registry publishes. A reader
    that treated ``imported`` as evidence about it would have switched
    ``gpt-4.1``, ``gpt-5.2`` and 39 others off the strict path in one commit.
    A reader of a column outside ``CORRECTABLE_FIELDS`` must therefore require
    ``verified``.
    """

    declared = "declared"  # column defaults — never curated, do not trust
    imported = "imported"  # from the vendored registry snapshot or the pricing sheet
    verified = "verified"  # a human confirmed it; the sync never overwrites this


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

    reasoning_enum_values: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "The levels this model accepts, ascending, in the ADR-245 ladder "
            "vocabulary. It may only NARROW its family's ladder "
            "(resolve_reasoning_profile); NULL = the family's own applies. The "
            "one catalogue value the reasoning resolution reads."
        ),
    )

    reasoning_doc_i18n_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Frontend lookup key in REASONING_DOC_TEXT constant table (English-only)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this model is currently selectable (no index: low cardinality)",
    )

    capability_provenance: Mapped[LLMCapabilityProvenanceEnum] = mapped_column(
        SQLEnum(
            LLMCapabilityProvenanceEnum,
            name="llm_capability_provenance_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMCapabilityProvenanceEnum.declared,
        server_default=LLMCapabilityProvenanceEnum.declared.value,
        comment="Authority that filled the capability fields (declared/imported/verified)",
    )

    deprecation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Provider retirement date from the vendored registry snapshot",
    )

    # cascade kept narrow on purpose: the FK uses ON DELETE RESTRICT, so we
    # never want the ORM to attempt cascading deletes (would race with the DB
    # constraint and emit IntegrityError). Use lazy="raise" to make any N+1
    # access fail loud — callers must use selectinload(LLMModel.pricings).
    pricings: Mapped[list[LLMModelPricing]] = relationship(
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

    model: Mapped[LLMModel] = relationship(
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
        # ADR-228: "the" active tariff of a model is an invariant, not a
        # convention. Without it, four read paths selected among two or three
        # active rows without a deterministic order — two of them could return
        # different prices for the same model at the same instant.
        Index(
            "uq_llm_model_pricing_active",
            "model_id",
            unique=True,
            postgresql_where=text("is_active"),
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
        # ADR-228: one active rate per pair. The duplicates came from a
        # scheduler that inserted without deactivating; both writers now go
        # through domains/llm/currency_rates.py::replace_active_rate.
        Index(
            "uq_currency_rate_active",
            "from_currency",
            "to_currency",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CurrencyExchangeRate({self.from_currency}/{self.to_currency}={self.rate}, "
            f"active={self.is_active})>"
        )
