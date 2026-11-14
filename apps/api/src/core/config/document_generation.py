"""Document generation configuration module.

Contains settings for the AI document generation feature (ADR-226):
- Feature toggle (document_generation_enabled)
- Rate limiting and the dedicated tool-timeout family (ADR-160)
- Source-data size cap forwarded to the internal document LLM

Note: the model is managed via the admin LLM Config system (LLM type
``document_generation`` in LLM_TYPES_REGISTRY / LLMConfigOverrideCache).

There is **no per-user opt-in**: an instance that offers document generation
offers it to every account, and the only bounds are this deployment flag and
the administrator's capability switch. The person's own choices (illustrations,
animations — ``core/document_preferences.py``) shape a document, never whether
one is made; this module only bounds how many pictures one document may carry. (This docstring claimed such a column
existed on the User model until 2026-08-18; it never did, and the capability
map was about to report a dormant state nobody could ever turn on.)
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    DOCUMENT_GENERATION_ENABLED_DEFAULT,
    DOCUMENT_GENERATION_MAX_SOURCE_CHARS_DEFAULT,
    DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_CALLS_DEFAULT,
    DOCUMENT_GENERATION_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS_DEFAULT,
    DOCUMENT_GENERATION_SLIDE_MAX_BULLETS_DEFAULT,
    DOCUMENT_GENERATION_TOC_MIN_HEADINGS_DEFAULT,
    DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
    DOCUMENT_ILLUSTRATIONS_MAX_DEFAULT,
    INTERACTIVE_PAGE_ENABLED_DEFAULT,
    INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT,
    INTERACTIVE_PAGE_MAX_BYTES_DEFAULT,
    INTERACTIVE_PAGE_SOURCE_LOOKBACK_MESSAGES_DEFAULT,
    MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT,
)
from src.core.map_tile_providers import parse_map_provider_keys


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
            "documents and exceeds the generic tool default. It yields to the "
            "document_generation slot's timeout (ADR-221)."
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

    # ========================================================================
    # Interactive pages (ADR-370)
    # ========================================================================

    interactive_page_enabled: bool = Field(
        default=INTERACTIVE_PAGE_ENABLED_DEFAULT,
        description=(
            "Global feature flag for interactive pages. When false, the "
            "generate_interactive_page tool is not registered and the "
            "interactive_page domain is absent from the planner catalogue."
        ),
    )

    interactive_page_max_bytes: int = Field(
        default=INTERACTIVE_PAGE_MAX_BYTES_DEFAULT,
        ge=10240,
        le=524288,
        description=(
            "Largest page, in UTF-8 bytes, published to the writer and enforced "
            "on its result. Stays under widget_persist_max_bytes: a page travels "
            "with its message, and its JSON encoding is larger than the page."
        ),
    )

    interactive_page_source_lookback_messages: int = Field(
        default=INTERACTIVE_PAGE_SOURCE_LOOKBACK_MESSAGES_DEFAULT,
        ge=2,
        le=200,
        description=(
            "How many recent messages of the conversation are read to find the "
            "page or HTML code a revision, a display or a source request works from."
        ),
    )

    interactive_page_map_providers: str | list[str] = Field(
        default=",".join(INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT),
        validate_default=True,
        description=(
            "Map tile sources a page may load, by key of core/map_tile_providers.py "
            "(comma-separated; empty for none). The page's content policy names "
            "their origins for images only, and the writer is told the same list."
        ),
    )

    @field_validator("interactive_page_map_providers", mode="after")
    @classmethod
    def declared_map_providers(cls, value: str | list[str]) -> list[str]:
        """Read the map sources, in the table's order, refusing an undeclared one.

        A host never reaches a content policy from the environment: the setting
        names keys, and the table owns what each key means.

        Args:
            value: The configured list, or its comma-separated spelling.

        Returns:
            The declared keys, in the table's order, without duplicates.

        Raises:
            ValueError: An entry names no declared source.
        """
        return parse_map_provider_keys(value)

    # ========================================================================
    # Rendering craft (ADR-274)
    # ========================================================================
    # What the renderer ENFORCES, the prompt PUBLISHES (ADR-184): the three
    # bounds below travel to the writer as placeholders, with the consequence
    # of each overrun stated.

    document_generation_page_size: Literal["a4", "letter"] = Field(
        default=DOCUMENT_GENERATION_PAGE_SIZE_DEFAULT,
        description="Page size of docx/pdf documents: a4 or letter (slides are 16:9 landscape).",
    )

    document_generation_toc_min_headings: int = Field(
        default=DOCUMENT_GENERATION_TOC_MIN_HEADINGS_DEFAULT,
        ge=2,
        le=50,
        description=(
            "Headings from which a document gets a table of contents, numbered "
            "headings and a page break before each part — one predicate for the "
            "three, so a note never grows an apparatus it does not need."
        ),
    )

    document_generation_slide_max_bullets: int = Field(
        default=DOCUMENT_GENERATION_SLIDE_MAX_BULLETS_DEFAULT,
        ge=2,
        le=12,
        description=(
            "Bullets per slide published to the writer; beyond it the renderer "
            "splits the slide rather than overflowing it."
        ),
    )

    document_generation_slide_max_bullet_chars: int = Field(
        default=DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS_DEFAULT,
        ge=40,
        le=400,
        description=(
            "Characters per bullet published to the writer; beyond it the "
            "renderer shrinks the text, then splits the slide."
        ),
    )

    document_illustrations_max: int = Field(
        default=DOCUMENT_ILLUSTRATIONS_MAX_DEFAULT,
        ge=0,
        le=12,
        description=(
            "Pictures one generated document may carry, published to the writer "
            "and enforced; each is an image generation billed to the turn. 0 "
            "switches illustrations off for the instance."
        ),
    )
