"""
LLM Configuration Admin API schemas.

Pydantic models for request/response validation in the LLM config admin API.

Created: 2026-03-08
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.llm_agent_config import LLMAgentConfig

# Re-exported so import-time consumers can reference the intent from here.
from src.core.reasoning_intent import ReasoningIntent, intent_from_legacy, is_intent_shape

__all__ = [
    "LLMConfigListResponse",
    "LLMTypeConfig",
    "LLMTypeConfigUpdate",
    "LLMTypeInfo",
    "ModelCapabilities",
    "OllamaModelCapabilities",
    "OllamaModelsResponse",
    "ProviderKeyStatus",
    "ProviderKeyUpdate",
    "ProviderKeysResponse",
    "ProviderModelsMetadata",
    "ReasoningBudgetBounds",
    "ReasoningIntent",
]

# --- Provider Keys ---


class ProviderKeyStatus(BaseModel):
    """Status of a provider's API key configuration."""

    provider: str
    display_name: str
    has_db_key: bool
    masked_key: str | None = None  # "sk-...abc" (last 4 chars)
    updated_at: datetime | None = None


class ProviderKeysResponse(BaseModel):
    """Response for listing all provider key statuses."""

    providers: list[ProviderKeyStatus]


class ProviderKeyUpdate(BaseModel):
    """Request to update a provider's API key."""

    key: str = Field(min_length=1, max_length=500)


# --- LLM Type Config ---


class LLMTypeInfo(BaseModel):
    """Metadata for an LLM type (static, from registry)."""

    llm_type: str
    display_name: str
    category: str
    description_key: str
    required_capabilities: list[str]
    power_tier: str | None = Field(
        None,
        description="Visual power tier indicator: critical, high, medium, low, or null",
    )
    required_kind: Literal["chat", "image", "audio", "realtime", "tts", "embedding"] = Field(
        default="chat",
        description=(
            "The kind of model this LLM type expects. Drives the kinds= filter "
            "applied by the frontend when fetching /llm-config/metadata."
        ),
    )


class LLMTypeConfig(BaseModel):
    """Complete config view for a single LLM type."""

    llm_type: str
    info: LLMTypeInfo
    effective: LLMAgentConfig  # Merged: defaults + overrides
    overrides: dict[str, Any]  # Non-null override fields from DB
    defaults: LLMAgentConfig  # Code constants (LLM_DEFAULTS)
    is_overridden: bool  # True if at least one DB override exists


class LLMTypeConfigUpdate(BaseModel):
    """Request to update an LLM type's config (full replace semantics).

    Each PUT replaces the entire override row. null = use code default.
    The frontend always sends the complete state of overrides.
    """

    provider: (
        Literal[
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
        | None
    ) = None
    model: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    frequency_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0)
    timeout_seconds: int | None = Field(None, gt=0)
    # ``None`` = clear the override. One shape for every provider (ADR-245),
    # with strict validation at the service layer
    # (``domains/llm_config/reasoning_validation.py``). The Literal on
    # ``ReasoningIntent.level`` rejects an unknown level here; the service layer
    # checks membership of the model's ladder, and the translator coerces
    # whatever survives to the nearest depth the model accepts.
    reasoning_effort: ReasoningIntent | None = None

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _accept_legacy_reasoning_shapes(cls, value: Any) -> Any:
        """Accept a payload from a frontend that has not been redeployed yet.

        Same reason as ``LLMAgentConfig``: the admin UI and the API are deployed
        as one image here, but a cached bundle in a browser tab is not, and
        rejecting its payload with a 422 would be a puzzling failure for a
        change that did not need to break anything.
        """
        if value is None or isinstance(value, ReasoningIntent):
            return value
        if not isinstance(value, dict):
            return value
        # Intent-shaped payloads stay raw so the ``Literal`` still 422s a level
        # nobody defined; only the pre-ADR-245 shapes are mapped.
        return value if is_intent_shape(value) else intent_from_legacy(value)

    provider_config: str | None = None


class LLMConfigListResponse(BaseModel):
    """Response for listing all LLM type configs."""

    configs: list[LLMTypeConfig]


# --- Metadata (static) ---


class ReasoningBudgetBounds(BaseModel):
    """The token budget a model accepts — exactly the two numbers it accepts.

    The catalogue's own range type went with its column (ADR-245): it carried
    ``off_sentinel`` / ``dynamic_sentinel``, which became levels. What remains
    is this one -- the bounds the validator enforces, published to the UI that
    must respect them, and nothing else.
    """

    model_config = ConfigDict(extra="forbid")
    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)


class ModelCapabilities(BaseModel):
    """Capabilities metadata for a single model.

    Source of truth: ``llm_models`` DB row, exposed via
    ``GET /llm-config/metadata``.
    """

    model_id: str
    kind: Literal["chat", "image", "audio", "realtime", "tts", "embedding"]
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    is_reasoning_model: bool

    # Sampling parameter acceptance — drives the Configuration LLM admin UI
    # conditional rendering of sampling inputs (philosophy A — raw truth).
    # Source of truth: ``llm_models.supports_*`` columns.
    supports_temperature: bool
    supports_top_p: bool
    supports_frequency_penalty: bool
    supports_presence_penalty: bool

    # Reasoning UI driver (ADR-245): the RESOLVED profile, never the raw
    # catalogue columns. Every field below comes from
    # ``resolve_reasoning_profile`` -- the same function the runtime translator
    # and the write-path validator call -- so what the UI offers, what the API
    # accepts and what the model receives cannot disagree. Publishing the
    # catalogue's own ``reasoning_widget``/``reasoning_enum_values`` instead is
    # how the UI came to offer ``minimal`` on a model whose API refused it.
    reasoning_family: str = Field(
        default="none",
        description="Resolved translator family; 'none' when the model does not reason",
    )
    reasoning_levels: list[str] = Field(
        default_factory=list,
        description="The accepted ladder, ascending. Empty = no reasoning control at all",
    )
    reasoning_can_disable: bool = Field(
        default=True,
        description="Whether reasoning can be turned off ('none' is offerable)",
    )
    reasoning_supports_budget: bool = Field(
        default=False,
        description="Whether an explicit token budget is expressible",
    )
    reasoning_supports_exclude: bool = Field(
        default=False,
        description="Whether exclude_from_output reaches the provider for this family",
    )
    reasoning_budget_range: ReasoningBudgetBounds | None = None
    reasoning_doc_i18n_key: str | None = None

    cost_input: float | None = None
    cost_output: float | None = None


class ProviderModelsMetadata(BaseModel):
    """Available models grouped by provider."""

    providers: dict[str, list[ModelCapabilities]]


# --- Ollama dynamic discovery ---


class OllamaModelCapabilities(ModelCapabilities):
    """Extended capabilities for a dynamically discovered Ollama model."""

    size: str | None = None  # e.g. "8B", "70B"
    family: str | None = None  # e.g. "llama", "qwen2"


class OllamaModelsResponse(BaseModel):
    """Response for dynamically discovered Ollama models.

    ``source`` indicates whether models were fetched live from the Ollama
    server ("live") or fell back to static profiles ("fallback").
    """

    models: list[OllamaModelCapabilities]
    source: Literal["live", "fallback"]
