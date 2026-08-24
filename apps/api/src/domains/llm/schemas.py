"""
Pydantic schemas for LLM pricing API.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.llm.pricing_time_slots import TimeSlotPrice, validate_time_slot_list

# Enum-like literal type for the provider field. Must stay in sync with
# LLMProviderEnum (apps/api/src/domains/llm/models.py) AND LLM_PROVIDERS
# (apps/api/src/domains/llm_config/constants.py).
ProviderLiteral = Literal[
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
    "elevenlabs",
    "edge",
]

# Mirrors LLMModelKindEnum / LLMReasoningWidgetEnum / PricingUnitEnum
# (domains/llm/models.py). Kept as Literal here so the API surface stays
# import-cycle-free.
LLMModelKindLiteral = Literal["chat", "image", "audio", "realtime", "tts", "embedding"]
PricingUnitLiteral = Literal["per_1m_tokens", "per_audio_minute", "per_audio_hour"]


#: Mirrors ``LLMCapabilityProvenanceEnum``. Pinned to it by a test: a payload
#: that could carry a value the column cannot store would be a lie the admin
#: screen renders as a badge.
CapabilityProvenanceLiteral = Literal["declared", "imported", "verified"]


class RetiringModelPayload(BaseModel):
    """One retiring model and the evidence behind it."""

    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    provider: ProviderLiteral
    state: Literal["retired", "disputed", "announced", "flagged"]
    deprecation_date: date | None
    seen_by: list[str]


class CatalogueStatusResponse(BaseModel):
    """What the vendored registries say about this catalogue (ADR-244).

    Read-only, and deliberately so: the correction ships as a migration and the
    continuous sync is a later lot. This endpoint exists because the work the
    registries already did was invisible from the screen that shows the
    catalogue — an operator could not tell a measured context window from the
    column default nobody ever curated.

    Every count is over the ACTIVE rows only: a deactivated model is not part
    of what this deployment offers, and reporting corrections for it would ask
    the reader to arbitrate something that cannot be reached.
    """

    model_config = ConfigDict(protected_namespaces=())

    compared: int = Field(..., ge=0, description="Active catalogue rows examined")
    auto: int = Field(..., ge=0, description="Corrections on rows no human curated")
    review: int = Field(..., ge=0, description="Corrections a human would have to arbitrate")
    retiring: list[RetiringModelPayload] = Field(
        ..., description="Models the registries report as going away, with their evidence"
    )
    provenance: dict[str, int] = Field(..., description="Row count per capability_provenance value")
    snapshot_generated_at: datetime | None = Field(
        None, description="When the vendored registry snapshot was taken"
    )


class ModelPriceResponse(BaseModel):
    """Response model for an LLM model + its active pricing.

    Returns both catalogue fields (provider, capabilities) and pricing in a
    flat structure. Built via :func:`router._pricing_to_response` from a
    pricing row whose ``model`` relationship is selectinload'd.
    """

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    # Pricing row identity + pricing fields
    id: uuid.UUID
    input_unit_price: Decimal
    cached_input_unit_price: Decimal | None
    output_unit_price: Decimal
    pricing_unit: PricingUnitLiteral
    effective_from: datetime
    is_active: bool
    time_slots: list[TimeSlotPrice] | None = Field(
        default=None,
        description="Optional UTC windowed tariff (ADR-223); None = flat pricing",
    )

    # Catalogue fields (from llm_models via JOIN)
    provider: ProviderLiteral
    model_name: str
    max_input_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_strict_mode: bool
    supports_streaming: bool
    supports_vision: bool
    is_reasoning_model: bool

    # Kind + reasoning widget + sampling caps. Returned so the admin form can
    # pre-select the matching template (or "Custom") at edit time.
    kind: LLMModelKindLiteral
    reasoning_enum_values: list[str] | None
    reasoning_doc_i18n_key: str | None
    supports_temperature: bool
    supports_top_p: bool
    supports_frequency_penalty: bool
    supports_presence_penalty: bool

    # Who filled the capability fields (ADR-244). Read-only: the workbook and
    # this API both refuse to take it as input, because a hand-written value
    # would claim a verification nobody performed.
    capability_provenance: CapabilityProvenanceLiteral
    deprecation_date: date | None = None


class ModelPriceCreate(BaseModel):
    """Request model: create a new LLM model + its initial pricing in one transaction.

    The admin form sends this payload. The service layer
    (``LLMModelService.create``) inserts both an ``llm_models`` row and an
    initial active ``llm_model_pricing`` row pointing to it, atomically.

    The reasoning identity is written directly: ``is_reasoning_model``, plus
    the optional ``reasoning_enum_values`` ladder narrowing — the one
    catalogue value the resolution reads (ADR-245). Omitting the ladder means
    "the family's own applies".

    A ``reasoning_template`` mode used to exist beside it, copying the
    identity from another row. It went with the two surfaces that offered it:
    the admin form now renders the model's OWN family ladder as checkboxes,
    and the workbook writes the same two columns. Copying across families
    could only remove depths, silently.

    The following fields are saved explicitly per model:

    - ``kind`` (chat / image / audio / realtime / tts / embedding)
    - the four ``supports_*`` sampling flags
    - ``reasoning_doc_i18n_key`` (UX tooltip key, family-specific)

    Keeping them outside the template lets two models share the same
    reasoning shape while declaring distinct sampling matrices or
    tooltip keys (e.g. OpenAI o-series vs Anthropic 4.5+ both expose an
    enum but accept different sampling subsets).
    """

    model_config = ConfigDict(protected_namespaces=())

    # --- Catalogue ---
    provider: ProviderLiteral = Field(..., description="Provider that hosts this model")
    model_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._\-/:]+$",
        description="Globally unique model identifier",
    )

    # --- Capabilities (always required) ---
    kind: LLMModelKindLiteral = Field(..., description="Model nature")
    max_input_tokens: int = Field(..., gt=0, description="Maximum context window size")
    max_output_tokens: int = Field(..., ge=0, description="Maximum response tokens")
    supports_tools: bool = Field(..., description="Whether the model supports tool calling")
    supports_structured_output: bool = Field(
        ..., description="Whether the model supports structured output"
    )
    supports_strict_mode: bool = Field(
        ..., description="Whether the model supports strict-mode structured output (OpenAI-only)"
    )
    supports_streaming: bool = Field(..., description="Whether the model supports streaming")
    supports_vision: bool = Field(..., description="Whether the model accepts image inputs")
    supports_temperature: bool = Field(
        ..., description="Whether the API accepts a temperature sampling parameter"
    )
    supports_top_p: bool = Field(
        ..., description="Whether the API accepts a top_p sampling parameter"
    )
    supports_frequency_penalty: bool = Field(
        ..., description="Whether the API accepts a frequency_penalty sampling parameter"
    )
    supports_presence_penalty: bool = Field(
        ..., description="Whether the API accepts a presence_penalty sampling parameter"
    )

    # --- Reasoning identity ---
    is_reasoning_model: bool = Field(
        default=False,
        description="Whether this model does any reasoning at all.",
    )
    reasoning_enum_values: list[str] | None = Field(
        default=None,
        description=(
            "The levels this model accepts, ascending, in the ADR-245 ladder "
            "vocabulary. It may only NARROW its family's ladder; omit it to "
            "use the family's own."
        ),
    )

    # --- Saved explicitly per model ---
    reasoning_doc_i18n_key: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Optional i18n key for the reasoning tooltip text. Saved per "
            "model regardless of the template chosen."
        ),
    )

    # --- Pricing ---
    pricing_unit: PricingUnitLiteral = Field(
        default="per_1m_tokens",
        description=(
            "Billing unit semantics. 'per_1m_tokens' for chat/text models. "
            "'per_audio_minute' or 'per_audio_hour' for STT/TTS models "
            "(e.g. ElevenLabs Scribe = per_audio_hour at $0.22/h)."
        ),
    )
    input_unit_price: Decimal = Field(
        ..., ge=0, description="Input unit price in USD (semantic = pricing_unit)"
    )
    cached_input_unit_price: Decimal | None = Field(
        None, ge=0, description="Cached input unit price in USD (optional)"
    )
    output_unit_price: Decimal = Field(
        ..., ge=0, description="Output unit price in USD (0 for STT models)"
    )
    time_slots: list[TimeSlotPrice] | None = Field(
        default=None,
        description=(
            "Optional UTC windowed tariff (ADR-223): non-overlapping "
            "[start,end) windows, each overriding the three unit prices "
            "while active; outside every window the base prices apply. "
            "Only accepted with pricing_unit='per_1m_tokens'. None/[] = "
            "flat pricing."
        ),
    )

    @model_validator(mode="after")
    def _validate_time_slots(self) -> ModelPriceCreate:
        """Reject overlapping windows and windowed tariffs on audio units."""
        if self.time_slots:
            if self.pricing_unit != "per_1m_tokens":
                raise ValueError(
                    "time_slots are only supported with pricing_unit='per_1m_tokens' "
                    f"(got {self.pricing_unit!r})"
                )
            validate_time_slot_list(self.time_slots)
        return self


class ModelPriceUpdate(BaseModel):
    """Request model: partial update of capabilities and/or pricing.

    All fields are optional. ``provider`` is intentionally NOT updatable here
    (it is an intrinsic property of the model). ``model_name`` is updatable —
    it renames the model in place on llm_models.

    Pass ``is_reasoning_model`` and/or ``reasoning_enum_values`` to mutate the
    reasoning identity in place, or ``clear_reasoning_enum_values`` to stop
    narrowing at all. ``kind`` and the four ``supports_*`` sampling flags are
    independent — pass any subset of them.

    The service layer differentiates three cases:
    - capabilities only → mutate llm_models in place
    - pricing only → temporal versioning on llm_model_pricing
    - mixed → both, in a single transaction
    """

    model_config = ConfigDict(protected_namespaces=())

    # --- Catalogue (all optional) ---
    model_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._\-/:]+$",
        description="Rename to this name (kept on llm_models, no new pricing row)",
    )
    kind: LLMModelKindLiteral | None = None
    max_input_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_strict_mode: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None
    supports_temperature: bool | None = None
    supports_top_p: bool | None = None
    supports_frequency_penalty: bool | None = None
    supports_presence_penalty: bool | None = None

    # --- Reasoning identity ---
    is_reasoning_model: bool | None = None
    reasoning_enum_values: list[str] | None = None
    reasoning_doc_i18n_key: str | None = Field(default=None, max_length=100)

    # --- Pricing (all optional) ---
    pricing_unit: PricingUnitLiteral | None = None
    input_unit_price: Decimal | None = Field(default=None, ge=0)
    cached_input_unit_price: Decimal | None = Field(default=None, ge=0)
    output_unit_price: Decimal | None = Field(default=None, ge=0)
    time_slots: list[TimeSlotPrice] | None = Field(
        default=None,
        description=(
            "Optional UTC windowed tariff (ADR-223). Omitted = inherit the "
            "current row's slots onto the new temporal version; [] = clear "
            "them (the explicit-null form is dropped by the service's "
            "exclude_none change-set, so the empty list IS the clearing "
            "sentinel); non-empty = replace. Only valid while the effective "
            "pricing_unit is 'per_1m_tokens'."
        ),
    )

    clear_cached_input_price: bool = Field(
        default=False,
        description=(
            "Explicitly set cached_input_unit_price back to NULL. A plain "
            "None cannot express it: the service builds its change-set with "
            "exclude_none, so the null is dropped and the previous value "
            "survives — an administrator emptying the cell would silently "
            "keep the old price. Same doctrine as the empty list clearing "
            "time_slots (ADR-223): the intent needs a shape of its own."
        ),
    )

    clear_reasoning_enum_values: bool = Field(
        default=False,
        description=(
            "Explicitly set reasoning_enum_values back to NULL, i.e. stop "
            "narrowing the family's ladder. Exactly the same trap as "
            "clear_cached_input_price: the change-set is built with "
            "exclude_none, so re-ticking every depth in the admin form (which "
            "means 'no narrowing') would be dropped and the old restriction "
            "would survive. A ladder that cannot be widened back is a knob "
            "that cannot express its own default value."
        ),
    )

    @model_validator(mode="after")
    def _validate_ladder_clearing(self) -> ModelPriceUpdate:
        """Refuse a payload that both clears and sets the ladder."""
        if self.clear_reasoning_enum_values and self.reasoning_enum_values is not None:
            raise ValueError(
                "clear_reasoning_enum_values and reasoning_enum_values are "
                "mutually exclusive: choose clearing or a ladder, not both"
            )
        return self

    @model_validator(mode="after")
    def _validate_cached_price_clearing(self) -> ModelPriceUpdate:
        """Refuse a payload that both clears and sets the cached price.

        Ranking two contradictory intents silently is how a price ends up
        being whatever the implementation happened to check first.
        """
        if self.clear_cached_input_price and self.cached_input_unit_price is not None:
            raise ValueError(
                "clear_cached_input_price and cached_input_unit_price are "
                "mutually exclusive: choose clearing or a value, not both"
            )
        return self

    @model_validator(mode="after")
    def _validate_time_slots(self) -> ModelPriceUpdate:
        """Reject overlaps, and audio units combined with non-empty slots.

        The unit check here only covers payloads carrying BOTH fields; the
        merged state (inherited slots + switched unit, or inherited unit +
        new slots) is validated by the service, which knows the current row.
        """
        if self.time_slots:
            if self.pricing_unit is not None and self.pricing_unit != "per_1m_tokens":
                raise ValueError(
                    "time_slots are only supported with pricing_unit='per_1m_tokens' "
                    f"(got {self.pricing_unit!r})"
                )
            validate_time_slot_list(self.time_slots)
        return self


class CurrencyRateResponse(BaseModel):
    """Response model for currency exchange rate."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_from: datetime
    is_active: bool


class CurrencyRateCreate(BaseModel):
    """Request model for creating new currency exchange rate."""

    from_currency: str = Field(
        ..., min_length=3, max_length=3, description="Source currency code (ISO 4217)"
    )
    to_currency: str = Field(
        ..., min_length=3, max_length=3, description="Target currency code (ISO 4217)"
    )
    rate: Decimal = Field(
        ..., gt=0, description="Exchange rate (1 from_currency = rate to_currency)"
    )


class LLMPricingListResponse(BaseModel):
    """Response model for listing all active LLM pricing with pagination."""

    total: int
    page: int
    page_size: int
    total_pages: int
    models: list[ModelPriceResponse]


class CurrencyRatesListResponse(BaseModel):
    """Response model for listing all active currency rates."""

    total: int
    rates: list[CurrencyRateResponse]


class ReasoningBudgetBoundsPayload(BaseModel):
    """The token budget bounds, published to the Pricing form.

    A deliberate twin of ``llm_config.schemas.ReasoningBudgetBounds``: the two
    JSON shapes are identical on purpose, so both admin screens name one
    resolved value the same way, but IMPORTING that one would close a cycle --
    ``llm_config.constants`` already imports ``llm.models.LLMModelKindEnum``,
    and the domain-cycle ratchet caught the second edge the moment it appeared.
    Six duplicated lines buy a graph that stays acyclic; a shared type would
    have to move to a neutral module, which is a refactor of ``llm_config``,
    not of this endpoint.
    """

    model_config = ConfigDict(extra="forbid")
    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)


class ReasoningFamilyResponse(BaseModel):
    """What the RUNTIME will accept for one ``(provider, model)`` pair.

    The Pricing form needs this to stop asking the operator to *declare* what a
    model supports: ``reasoning_enum_values`` can only NARROW the ladder
    derived from that pair, never widen it and never create a family. Rendering
    the field as a free-text list invited the two mistakes the catalogue
    actually made -- writing a level the ladder does not have (``off``, which
    the narrowing intersection dropped in silence) and copying a ladder that
    belongs to another family, which removes depths without saying so.

    Resolved WITHOUT the catalogue narrowing, on purpose: the narrowing is what
    the operator is about to choose, and offering the already-narrowed ladder
    would make a saved restriction impossible to widen again.

    Field names mirror ``LLMModelMetadata`` so both admin screens name the same
    resolved profile the same way.
    """

    model_config = ConfigDict(extra="forbid")

    reasoning_family: str = Field(
        ..., description="Resolved translator family; 'none' when no rule matches the model"
    )
    reasoning_levels: list[str] = Field(
        ..., description="The family's ladder, ascending. Empty = no reasoning control at all"
    )
    reasoning_can_disable: bool = Field(
        ..., description="Whether reasoning can be switched off — never narrowable by a row"
    )
    reasoning_supports_budget: bool = Field(
        ..., description="Whether an explicit token budget is expressible"
    )
    reasoning_budget_range: ReasoningBudgetBoundsPayload | None = Field(
        None, description="The bounds the validator enforces, when a budget is expressible"
    )
    source: str = Field(
        ...,
        description="'family' when a rule matched, 'unknown' when none did — the form says which",
    )
