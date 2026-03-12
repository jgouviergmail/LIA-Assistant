"""
Catalogue manifests for Perplexity tools (Web Search AI).
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
# 1. PERPLEXITY SEARCH
# ============================================================================
_search_desc = (
    "**Tool: perplexity_search_tool** - Real-time web search with AI synthesis.\n"
    "**Use for**: Web search, current events, prices, factual lookups, recent news, knowledge after 2024.\n"
    "**Features**: Aggregates multiple sources, returns citations.\n"
    "**Output**: Synthesized answer + source URLs + follow-up queries."
)
perplexity_search_catalogue_manifest = ToolManifest(
    name="perplexity_search_tool",
    agent="perplexity_agent",
    description=_search_desc,
    semantic_keywords=[
        "search web",
        "web search",
        "search online",
        "search internet",
        "look up online",
        "find online",
        "current news",
        "latest news",
        "what is happening",
        "recent events",
        "google search",
        "internet search",
        "perplexity search",
        "search for",
        "information about",
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
            name="recency",
            type="string",
            required=False,
            description="'day', 'week', 'month', 'year' (def: none)",
        ),
        ParameterSchema(
            name="include_citations",
            type="boolean",
            required=False,
            description="Include URLs (def: True)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="answer", type="string", description="Synthesized answer", semantic_type="text"
        ),
        OutputFieldSchema(path="citations", type="array", description="Sources"),
        OutputFieldSchema(
            path="citations[].url",
            type="string",
            description="URL",
            semantic_type="citation_url",
        ),
        OutputFieldSchema(path="citations[].title", type="string", description="Title"),
        OutputFieldSchema(path="related_queries", type="array", description="Follow-up queries"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=800, est_cost_usd=0.01, est_latency_ms=3000),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="perplexitys",  # Must match CONTEXT_DOMAIN_PERPLEXITY (domain + "s" pattern)
    reference_examples=["answer", "citations[0].url", "related_queries"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🌐", i18n_key="perplexity_search", visible=True, category="tool"
    ),
)

# ============================================================================
# 2. PERPLEXITY ASK
# ============================================================================
_ask_desc = (
    "**Tool: perplexity_ask_tool** - Deep explanation using web context.\n"
    "**Use for**: Complex 'Why'/'How' questions requiring synthesis.\n"
    "**Difference**: Use perplexity_search_tool for facts, perplexity_ask_tool for understanding."
)
perplexity_ask_catalogue_manifest = ToolManifest(
    name="perplexity_ask_tool",
    agent="perplexity_agent",
    description=_ask_desc,
    semantic_keywords=[
        "explain",
        "how does",
        "why does",
        "what causes",
        "understand",
        "explain to me",
        "help me understand",
        "deep explanation",
        "complex question",
    ],
    parameters=[
        ParameterSchema(
            name="question",
            type="string",
            required=True,
            description="Complex question",
            constraints=[ParameterConstraint(kind="min_length", value=5)],
        ),
        ParameterSchema(
            name="context",
            type="string",
            required=False,
            description="Focus domain (e.g. 'medical', 'finance')",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="answer", type="string", description="Detailed answer", semantic_type="text"
        ),
        OutputFieldSchema(path="citations", type="array", description="Sources"),
        OutputFieldSchema(
            path="citations[].url",
            type="string",
            description="URL",
            semantic_type="citation_url",
        ),
        OutputFieldSchema(
            path="confidence",
            type="number",
            nullable=True,
            description="Confidence (0-1)",
            semantic_type="confidence_score",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=200, est_tokens_out=1000, est_cost_usd=0.015, est_latency_ms=5000
    ),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="perplexitys",  # Must match CONTEXT_DOMAIN_PERPLEXITY (domain + "s" pattern)
    reference_examples=["answer", "confidence"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="❓", i18n_key="perplexity_ask", visible=True, category="tool"),
)

__all__ = [
    "perplexity_search_catalogue_manifest",
    "perplexity_ask_catalogue_manifest",
]
