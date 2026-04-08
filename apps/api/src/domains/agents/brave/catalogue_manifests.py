"""
Catalogue manifests for Brave Search tools.
Optimized for orchestration efficiency.
"""

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
# 1. BRAVE WEB SEARCH
# ============================================================================
_search_desc = (
    "**Tool: brave_search_tool** - Lightweight web search via Brave Search API (single API call).\n"
    "**Use for**: Additional/complementary web searches when unified_web_search_tool was already used, "
    "or when multiple distinct search queries are needed in one plan.\n"
    "**Output**: List of results with title, URL, description."
)

brave_search_catalogue_manifest = ToolManifest(
    name="brave_search_tool",
    agent="brave_agent",
    description=_search_desc,
    # Keywords for direct Brave Search usage (rare - most go via unified_web_search)
    semantic_keywords=[
        "internet search",
        "net search",
        "web search",
        "brave search",
        "online search",
    ],
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="Search query",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(
            name="count",
            type="integer",
            required=False,
            description="Number of results (default: 5, max: 20)",
            constraints=[ParameterConstraint(kind="maximum", value=20)],
        ),
        ParameterSchema(
            name="freshness",
            type="string",
            required=False,
            description="Freshness: 'pd' (24h), 'pw' (7d), 'pm' (31d), 'py' (1y)",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="braves", type="array", description="Search results"),
        OutputFieldSchema(path="braves[].title", type="string", description="Result title"),
        OutputFieldSchema(
            path="braves[].url",
            type="string",
            description="Result URL",
            semantic_type="URL",
        ),
        OutputFieldSchema(
            path="braves[].description",
            type="string",
            description="Result snippet",
            semantic_type="text",
        ),
        OutputFieldSchema(path="total", type="integer", description="Total count"),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=500,
        est_cost_usd=0.001,
        est_latency_ms=2000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="braves",  # Must match CONTEXT_DOMAIN_BRAVE
    reference_examples=["braves[0].url", "braves[0].title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🔍",
        i18n_key="brave_search",
        visible=True,
        category="tool",
    ),
    initiative_eligible=False,  # Web search tool, no personal data for cross-domain enrichment
)

# ============================================================================
# 2. BRAVE NEWS SEARCH
# ============================================================================
_news_desc = (
    "**Tool: brave_news_tool** - News search via Brave Search API.\n"
    "**Use for**: Recent news, current events, articles.\n"
    "**Output**: List of news articles with title, URL, description, date."
)

brave_news_catalogue_manifest = ToolManifest(
    name="brave_news_tool",
    agent="brave_agent",
    description=_news_desc,
    # Keywords for direct Brave News usage (rare - most go via unified_web_search)
    semantic_keywords=[
        "brave news",
        "search news",
        "web news",
        "online news",
    ],
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="News search query",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(
            name="count",
            type="integer",
            required=False,
            description="Number of results (default: 5, max: 50)",
            constraints=[ParameterConstraint(kind="maximum", value=50)],
        ),
        ParameterSchema(
            name="freshness",
            type="string",
            required=False,
            description="Freshness: 'pd' (24h), 'pw' (7d), 'pm' (31d)",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="braves", type="array", description="News articles"),
        OutputFieldSchema(path="braves[].title", type="string", description="Article title"),
        OutputFieldSchema(
            path="braves[].url",
            type="string",
            description="Article URL",
            semantic_type="URL",
        ),
        OutputFieldSchema(
            path="braves[].description",
            type="string",
            description="Article snippet",
        ),
        OutputFieldSchema(
            path="braves[].age",
            type="string",
            description="Article age (e.g., '2 hours ago')",
        ),
        OutputFieldSchema(path="total", type="integer", description="Total count"),
    ],
    cost=CostProfile(
        est_tokens_in=100,
        est_tokens_out=600,
        est_cost_usd=0.001,
        est_latency_ms=2000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="braves",
    reference_examples=["braves[0].url", "braves[0].title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📰",
        i18n_key="brave_news",
        visible=True,
        category="tool",
    ),
    initiative_eligible=False,  # Web search tool, no personal data for cross-domain enrichment
)

__all__ = [
    "brave_search_catalogue_manifest",
    "brave_news_catalogue_manifest",
]
