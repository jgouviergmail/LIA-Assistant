"""Document generation configuration module.

Contains settings for the AI document generation feature (ADR-226):
- Feature toggle (document_generation_enabled)
- Rate limiting and the dedicated tool-timeout family (ADR-160)
- Source-data size cap forwarded to the internal document LLM

Note: the model is managed via the admin LLM Config system (LLM type
``document_generation`` in LLM_TYPES_REGISTRY / LLMConfigOverrideCache); the
per-user opt-in lives on the User model (``document_generation_enabled``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DOCUMENT_GENERATION_ENABLED_DEFAULT,
    DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
)


class DocumentGenerationSettings(BaseSettings):
    """Settings for the AI document generation feature."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    document_generation_enabled: bool = Field(
        default=DOCUMENT_GENERATION_ENABLED_DEFAULT,
        description=(
            "Global feature flag for AI document generation. When false, the "
            "generate_document tool is not registered and the "
            "document_generation domain is absent from the planner catalogue."
        ),
    )

    # ========================================================================
    # Rate Limiting
    # ========================================================================

    document_generation_rate_limit_calls: int = Field(
        default=DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=100,
        description=(
            "Max generate_document calls per user per window. Technical "
            "anti-runaway ceiling for the dedicated LLM slot; complements the "
            "usage_limits cost caps which are per billing cycle."
        ),
    )

    document_generation_rate_limit_window: int = Field(
        default=DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate limit window (seconds) for the generate_document tool.",
    )

    # ========================================================================
    # Tool Execution Timeout (dedicated family, ADR-160)
    # ========================================================================

    document_generation_tool_timeout_seconds: float = Field(
        default=DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=600.0,
        description=(
            "Wall-clock FLOOR (seconds) applied by the parallel executor to a "
            "generate_document step — the internal LLM call writes whole "
            "documents and exceeds the generic tool default."
        ),
    )

    max_document_generation_tool_timeout_seconds: float = Field(
        default=MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=10.0,
        le=900.0,
        description=(
            "Wall-clock CEILING (seconds) for a generate_document step. "
            "Dedicated to the document family (ADR-160): caps whatever "
            "timeout the planner requests without undercutting the real "
            "latency of a large document."
        ),
    )

    # ========================================================================
    # Content Bounds
    # ========================================================================

    document_generation_max_source_chars: int = Field(
        default=DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
        ge=1000,
        le=500000,
        description=(
            "Maximum characters of source_data forwarded to the document LLM; "
            "the excess is truncated and the truncation is reported to the "
            "caller (never silent)."
        ),
    )
