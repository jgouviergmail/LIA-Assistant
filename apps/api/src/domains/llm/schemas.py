"""
Pydantic schemas for LLM pricing API.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.reasoning_types import ReasoningBudgetRange
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
ReasoningWidgetLiteral = Literal["none", "enum", "budget_int", "toggle_budget"]
PricingUnitLiteral = Literal["per_1m_tokens", "per_audio_minute", "per_audio_hour"]


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
    reasoning_widget: ReasoningWidgetLiteral
    reasoning_enum_values: list[str] | None
    reasoning_budget_range: ReasoningBudgetRange | None
    reasoning_doc_i18n_key: str | None
    supports_temperature: bool
    supports_top_p: bool
    supports_frequency_penalty: bool
    supports_presence_penalty: bool


class ModelPriceCreate(BaseModel):
    """Request model: create a new LLM model + its initial pricing in one transaction.

    The admin form sends this payload. The service layer
    (``LLMModelService.create``) inserts both an ``llm_models`` row and an
    initial active ``llm_model_pricing`` row pointing to it, atomically.

    The reasoning *shape* (``is_reasoning_model``, ``reasoning_widget``,
    ``reasoning_enum_values``, ``reasoning_budget_range``) is set in one
    of two mutually-exclusive modes:

    1. **Template mode (default)**: pass ``reasoning_template`` =
       ``model_name`` of an existing row. The service copies the 4
       reasoning shape fields verbatim. Those four explicit fields on
       this payload MUST be left unset.
    2. **Custom mode (disruption / new family)**: leave
       ``reasoning_template`` unset and provide
       ``is_reasoning_model`` + ``reasoning_widget`` (always) plus the
       widget-conditional ``reasoning_enum_values`` (when
       ``reasoning_widget == 'enum'``) or ``reasoning_budget_range``
       (when ``reasoning_widget`` is ``'budget_int'`` or
       ``'toggle_budget'``).

    The following fields are ALWAYS saved explicitly per model and are
    NOT touched by the template mechanism:

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

    # --- Reasoning template OR explicit reasoning fields (XOR, see model_validator) ---
    reasoning_template: str | None = Field(
        default=None,
        description=(
            "Optional model_name of an existing row to copy the 4 reasoning shape "
            "fields from (is_reasoning_model, reasoning_widget, "
            "reasoning_enum_values, reasoning_budget_range). When set, those "
            "four explicit fields below MUST NOT be provided. "
            "``reasoning_doc_i18n_key`` is independent and saved explicitly."
        ),
    )

    is_reasoning_model: bool | None = Field(
        default=None,
        description="Required in Custom mode; ignored in Template mode.",
    )
    reasoning_widget: ReasoningWidgetLiteral | None = Field(
        default=None,
        description="Reasoning widget shape. Required in Custom mode.",
    )
    reasoning_enum_values: list[str] | None = Field(
        default=None,
        description=(
            "Required when reasoning_widget == 'enum' in Custom mode. "
            "Ordered list of accepted reasoning_effort string values."
        ),
    )
    reasoning_budget_range: ReasoningBudgetRange | None = Field(
        default=None,
        description=(
            "Required when reasoning_widget in ('budget_int','toggle_budget') in Custom mode."
        ),
    )

    # --- Independent of the template (always saved explicitly) ---
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
    def _validate_time_slots(self) -> "ModelPriceCreate":
        """Reject overlapping windows and windowed tariffs on audio units."""
        if self.time_slots:
            if self.pricing_unit != "per_1m_tokens":
                raise ValueError(
                    "time_slots are only supported with pricing_unit='per_1m_tokens' "
                    f"(got {self.pricing_unit!r})"
                )
            validate_time_slot_list(self.time_slots)
        return self

    @model_validator(mode="after")
    def _enforce_template_xor_custom(self) -> "ModelPriceCreate":
        """Enforce reasoning template-mode vs custom-mode mutual exclusivity.

        The 4 reasoning shape fields must be wholly absent when
        ``reasoning_template`` is set, and the structural ones
        (``is_reasoning_model``, ``reasoning_widget``) must be wholly
        present otherwise. ``reasoning_enum_values`` /
        ``reasoning_budget_range`` are widget-conditional.
        """
        explicit_required = {
            "is_reasoning_model": self.is_reasoning_model,
            "reasoning_widget": self.reasoning_widget,
        }
        explicit_optional = {
            "reasoning_enum_values": self.reasoning_enum_values,
            "reasoning_budget_range": self.reasoning_budget_range,
        }
        any_explicit = {k for k, v in explicit_required.items() if v is not None} | {
            k for k, v in explicit_optional.items() if v is not None
        }

        if self.reasoning_template is not None:
            if any_explicit:
                raise ValueError(
                    "Template mode is exclusive: must not set explicit reasoning "
                    f"fields when reasoning_template is provided. Conflicting: "
                    f"{sorted(any_explicit)}."
                )
            return self

        # Custom mode: structural fields required.
        missing = sorted(k for k, v in explicit_required.items() if v is None)
        if missing:
            raise ValueError(
                "Custom mode requires is_reasoning_model + reasoning_widget; "
                f"missing: {missing}. Alternatively, pass reasoning_template "
                "to copy from an existing model."
            )

        # Widget-conditional sub-fields.
        if self.reasoning_widget == "enum":
            if not self.reasoning_enum_values:
                raise ValueError(
                    "reasoning_widget='enum' requires non-empty reasoning_enum_values."
                )
        elif self.reasoning_widget in ("budget_int", "toggle_budget"):
            if self.reasoning_budget_range is None:
                raise ValueError(
                    f"reasoning_widget={self.reasoning_widget!r} requires "
                    "reasoning_budget_range."
                )
        else:  # 'none'
            if self.reasoning_enum_values or self.reasoning_budget_range:
                raise ValueError(
                    "reasoning_widget='none' must NOT have reasoning_enum_values "
                    "or reasoning_budget_range set."
                )
        return self


class ModelPriceUpdate(BaseModel):
    """Request model: partial update of capabilities and/or pricing.

    All fields are optional. ``provider`` is intentionally NOT updatable here
    (it is an intrinsic property of the model). ``model_name`` is updatable —
    it renames the model in place on llm_models.

    Reasoning behavior supports the same Template / Custom modes as
    :class:`ModelPriceCreate`, but in update they are optional:

    - Pass ``reasoning_template`` to re-copy the 4 reasoning shape fields
      from an existing model (resets them in one move). Explicit
      reasoning shape fields must NOT be passed alongside.
    - Pass any subset of explicit reasoning shape fields to mutate in
      place (cross-field cohesion is validated against the model's
      current ``reasoning_widget`` once known by the service layer).

    ``kind`` and the four ``supports_*`` sampling flags are independent
    of the template — pass any subset of them to update directly.

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

    # --- Reasoning template OR explicit reasoning fields ---
    reasoning_template: str | None = Field(
        default=None,
        description=(
            "Optional model_name of an existing row to copy the 4 reasoning shape "
            "fields from (is_reasoning_model, reasoning_widget, "
            "reasoning_enum_values, reasoning_budget_range). Mutually exclusive "
            "with those four explicit fields below; ``kind``, the four "
            "``supports_*`` flags and ``reasoning_doc_i18n_key`` may be passed "
            "alongside."
        ),
    )

    is_reasoning_model: bool | None = None
    reasoning_widget: ReasoningWidgetLiteral | None = None
    reasoning_enum_values: list[str] | None = None
    reasoning_budget_range: ReasoningBudgetRange | None = None
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

    @model_validator(mode="after")
    def _validate_time_slots(self) -> "ModelPriceUpdate":
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

    @model_validator(mode="after")
    def _reject_template_with_explicit_reasoning(self) -> "ModelPriceUpdate":
        """Reject mixing template-mode with explicit reasoning fields.

        Per-widget cohesion (enum requires enum_values, budget_int requires
        budget_range, etc.) is enforced at the service layer, where the
        target widget is known after merging incoming changes with the
        current row.
        """
        if self.reasoning_template is None:
            return self
        explicit = {
            "is_reasoning_model": self.is_reasoning_model,
            "reasoning_widget": self.reasoning_widget,
            "reasoning_enum_values": self.reasoning_enum_values,
            "reasoning_budget_range": self.reasoning_budget_range,
        }
        conflicts = sorted(k for k, v in explicit.items() if v is not None)
        if conflicts:
            raise ValueError(
                "reasoning_template is mutually exclusive with explicit "
                f"reasoning shape fields. Conflicting: {conflicts}. "
                "(reasoning_doc_i18n_key is independent and may be passed "
                "alongside.)"
            )
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


class ReasoningTemplate(BaseModel):
    """A representative ``llm_models`` row for one unique reasoning shape
    present in the catalogue.

    The admin Pricing form lets the operator pick one of these templates to
    copy its 4-field reasoning shape onto a newly added model. The
    following fields are intentionally excluded — saved explicitly per
    model:

    - ``kind`` (chat / image / audio / ...)
    - the four ``supports_*`` sampling flags
    - ``reasoning_doc_i18n_key`` (UX tooltip key, family-specific)

    Templates are derived dynamically by grouping ``llm_models`` rows by
    their reasoning fingerprint (4 fields) and returning one representative
    per group. The set self-enriches: a model created in Custom mode with a
    novel reasoning shape becomes available as a template for future
    entries.
    """

    template_model_name: str = Field(
        ..., description="model_name of the representative row for this reasoning group"
    )
    representative_provider: ProviderLiteral
    description: str = Field(
        ...,
        description=("Human-readable summary of the reasoning shape rendered in the admin Select."),
    )
    matching_count: int = Field(
        ..., ge=1, description="Number of llm_models rows sharing this reasoning shape."
    )

    # The 4 reasoning shape fields that get copied to the new model when
    # this template is picked. Returned inline so the frontend can show a
    # readonly preview without a second round-trip.
    is_reasoning_model: bool
    reasoning_widget: ReasoningWidgetLiteral
    reasoning_enum_values: list[str] | None
    reasoning_budget_range: ReasoningBudgetRange | None


class ReasoningTemplatesResponse(BaseModel):
    """Response model for ``GET /admin/llm/reasoning-templates``."""

    templates: list[ReasoningTemplate]
