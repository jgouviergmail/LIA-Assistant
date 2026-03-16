"""
Catalogue manifests for Unified Web Search tools.
Orchestrates triple source search: Perplexity + Brave + Wikipedia.
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
# UNIFIED WEB SEARCH
# ============================================================================

_unified_search_desc = (
    "**Tool: unified_web_search_tool** - Comprehensive web search combining 3 sources.\n"
    "**Executes in parallel**: Perplexity AI (synthesis), Brave Search (URLs), Wikipedia (encyclopedia).\n"
    "**Use for**: Any web search, encyclopedic questions, current events, research.\n"
    "**Fallback chain**: Continues if one source fails, Wikipedia always available.\n"
    "**Output**: Unified results with synthesis, web links, and Wikipedia context."
)

unified_web_search_catalogue_manifest = ToolManifest(
    name="unified_web_search_tool",
    agent="web_search_agent",
    description=_unified_search_desc,
    # Broad keywords in ENGLISH ONLY (semantic pivot translates all queries to English)
    semantic_keywords=[
        # General search intents
        "search",
        "search for",
        "find",
        "look up",
        "look for",
        "search on the internet",
        "search online",
        "web search",
        # Question patterns
        "what is",
        "who is",
        "how to",
        "why",
        "when did",
        "when is",
        "when will",
        "where is",
        "which",
        # Information seeking
        "information about",
        "info about",
        "tell me about",
        "learn about",
        "explain",
        "definition of",
        # News and current events
        "news about",
        "latest news",
        "recent news",
        "current events",
        # Factual questions
        "date of",
        "history of",
        "facts about",
    ],
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="Search query or question",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(
            name="recency",
            type="string",
            required=False,
            description=(
                "Freshness filter. MUST be one of these exact values: "
                "'day' (last 24h), 'week' (last 7 days), 'month' (last 30 days). "
                "Omit or set to null for no time filter."
            ),
            constraints=[
                ParameterConstraint(kind="enum", value=["day", "week", "month"]),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="query", type="string", description="Search query"),
        OutputFieldSchema(
            path="synthesis",
            type="string",
            nullable=True,
            description="Perplexity AI synthesized answer",
            semantic_type="text",
        ),
        OutputFieldSchema(
            path="results",
            type="array",
            description="Brave Search web results",
        ),
        OutputFieldSchema(path="results[].title", type="string", description="Result title"),
        OutputFieldSchema(
            path="results[].url", type="string", description="URL", semantic_type="URL"
        ),
        OutputFieldSchema(path="results[].snippet", type="string", description="Description"),
        OutputFieldSchema(path="results[].source", type="string", description="Source name"),
        OutputFieldSchema(
            path="wikipedia",
            type="object",
            nullable=True,
            description="Wikipedia article info",
        ),
        OutputFieldSchema(path="wikipedia.title", type="string", description="Article title"),
        OutputFieldSchema(
            path="wikipedia.summary",
            type="string",
            description="Article summary",
            semantic_type="text",
        ),
        OutputFieldSchema(
            path="wikipedia.url", type="string", description="Wikipedia URL", semantic_type="URL"
        ),
        OutputFieldSchema(
            path="sources",
            type="array",
            description="All configured sources",
        ),
        OutputFieldSchema(
            path="sources_used",
            type="array",
            description="Sources that returned results",
        ),
        OutputFieldSchema(
            path="related_questions",
            type="array",
            nullable=True,
            description="Related questions from Perplexity",
        ),
        OutputFieldSchema(
            path="citations",
            type="array",
            nullable=True,
            description="Citation URLs from Perplexity",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=200,
        est_tokens_out=2000,
        est_cost_usd=0.005,
        est_latency_ms=1500,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # No OAuth needed - Wikipedia always available
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    context_key="web_searchs",  # Must match CONTEXT_DOMAIN_WEB_SEARCH (domain + "s" pattern)
    reference_examples=["synthesis", "results[0].title", "wikipedia.summary"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🔍",
        i18n_key="unified_web_search",
        visible=True,
        category="tool",
    ),
)

__all__ = [
    "unified_web_search_catalogue_manifest",
]
