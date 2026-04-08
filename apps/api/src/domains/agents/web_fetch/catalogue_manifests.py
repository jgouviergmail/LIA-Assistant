"""
Catalogue manifests for Web Fetch tool (evolution F1).
Optimized for orchestration efficiency.
"""

from src.core.constants import WEB_FETCH_MAX_OUTPUT_LENGTH, WEB_FETCH_MIN_OUTPUT_LENGTH
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# WEB FETCH TOOL — Page content extraction from URL
# ============================================================================

_fetch_desc = (
    "**Tool: fetch_web_page_tool** - Fetch and read a web page content.\n"
    "**Use for**: Reading full content of a URL, extracting article text, page content.\n"
    "**NOT for**: Searching the web (use web_search or brave_search instead).\n"
    "**Output**: Page title, markdown content, word count, language."
)

fetch_web_page_catalogue_manifest = ToolManifest(
    name="fetch_web_page_tool",
    agent="web_fetch_agent",
    description=_fetch_desc,
    semantic_keywords=[
        "fetch web page content from URL",
        "read article at this link",
        "open and extract web page text",
        "get content from this website URL",
        "download and read this page",
        "what does this link say",
    ],
    parameters=[
        ParameterSchema(
            name="url",
            type="string",
            required=True,
            description="Complete URL to fetch (e.g., 'https://example.com/article')",
            semantic_type="URL",
            constraints=[ParameterConstraint(kind="min_length", value=8)],
        ),
        ParameterSchema(
            name="extract_mode",
            type="string",
            required=False,
            description=("'article' (main content, default) or 'full' (entire page)"),
            constraints=[
                ParameterConstraint(kind="enum", value=["article", "full"]),
            ],
        ),
        ParameterSchema(
            name="max_length",
            type="integer",
            required=False,
            description=f"Max output chars (default: {WEB_FETCH_MAX_OUTPUT_LENGTH}, max: {WEB_FETCH_MAX_OUTPUT_LENGTH})",
            constraints=[
                ParameterConstraint(kind="minimum", value=WEB_FETCH_MIN_OUTPUT_LENGTH),
                ParameterConstraint(kind="maximum", value=WEB_FETCH_MAX_OUTPUT_LENGTH),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="title",
            type="string",
            description="Page title",
        ),
        OutputFieldSchema(
            path="content",
            type="string",
            description="Extracted page content as Markdown",
        ),
        OutputFieldSchema(
            path="url",
            type="string",
            description="Fetched URL (after HTTPS upgrade if applicable)",
            semantic_type="URL",
        ),
        OutputFieldSchema(
            path="word_count",
            type="integer",
            description="Word count of extracted content",
        ),
        OutputFieldSchema(
            path="language",
            type="string",
            description="Detected language (from HTML lang attribute)",
            nullable=True,
        ),
        OutputFieldSchema(
            path="web_fetchs",
            type="array",
            description="List of fetched page metadata for $steps references",
        ),
        OutputFieldSchema(
            path="web_fetchs[].title",
            type="string",
            description="Page title",
        ),
        OutputFieldSchema(
            path="web_fetchs[].url",
            type="string",
            description="Fetched URL",
            semantic_type="URL",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=2000,
        est_cost_usd=0.002,
        est_latency_ms=3000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="web_fetchs",  # Must match CONTEXT_DOMAIN_WEB_FETCH
    reference_examples=["web_fetchs[0].title", "web_fetchs[0].url"],
    version="1.0.0",
    maintainer="Team AI",
    display=DisplayMetadata(
        emoji="🌐",
        i18n_key="fetch_web_page",
        visible=True,
        category="tool",
    ),
    initiative_eligible=False,  # Web fetch tool, no personal data for cross-domain enrichment
)

__all__ = [
    "fetch_web_page_catalogue_manifest",
]
