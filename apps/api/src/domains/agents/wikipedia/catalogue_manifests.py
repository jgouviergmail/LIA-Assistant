"""
Catalogue manifests for Wikipedia tools.
Optimized for orchestration efficiency.
"""

from src.core.constants import (
    WIKIPEDIA_TOOL_DEFAULT_LIMIT,
    WIKIPEDIA_TOOL_DEFAULT_MAX_RESULTS,
)
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
# Shared Parameters
# ============================================================================
_LANG_PARAM = ParameterSchema(
    name="language",
    type="string",
    required=False,
    description="Lang code (e.g. 'fr', 'en'). Def: 'fr'.",
    semantic_type="language_code",
)

# ============================================================================
# 1. SEARCH WIKIPEDIA
# ============================================================================
_search_desc = (
    "**Tool: search_wikipedia_tool** - Search Wikipedia articles by keyword.\n"
    "**Use ONLY when**: Title is UNKNOWN or ambiguous (e.g., 'articles about AI').\n"
    "**Do NOT use for**: Known subjects like 'Emmanuel Macron' → use get_wikipedia_summary_tool.\n"
    "**Output**: List of articles with title, snippet, page_id."
)
search_wikipedia_catalogue_manifest = ToolManifest(
    name="search_wikipedia_tool",
    agent="wikipedia_agent",
    description=_search_desc,
    # VERY RESTRICTIVE: Only trigger when user explicitly mentions "Wikipedia"
    # General encyclopedic queries like "who is Einstein" should go to unified_web_search
    # Keywords in ENGLISH ONLY (semantic pivot translates all queries to English)
    semantic_keywords=[
        "list Wikipedia articles",
        "Wikipedia list",
    ],
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="Search terms",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max results (def: {WIKIPEDIA_TOOL_DEFAULT_LIMIT}, max: {WIKIPEDIA_TOOL_DEFAULT_MAX_RESULTS})",
            constraints=[
                ParameterConstraint(kind="maximum", value=WIKIPEDIA_TOOL_DEFAULT_MAX_RESULTS)
            ],
        ),
        _LANG_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="wikipedias", type="array", description="Found articles"),
        OutputFieldSchema(path="wikipedias[].title", type="string", description="Title"),
        OutputFieldSchema(
            path="wikipedias[].snippet", type="string", description="Snippet", semantic_type="text"
        ),
        OutputFieldSchema(
            path="wikipedias[].page_id",
            type="integer",
            description="ID",
            semantic_type="wikipedia_page_id",
        ),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=400, est_cost_usd=0.001, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="wikipedias",  # Must match CONTEXT_DOMAIN_WIKIPEDIA (domain + "s" pattern)
    reference_examples=["wikipedias[0].title", "wikipedias[0].page_id"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🔍", i18n_key="search_wikipedia", visible=True, category="tool"),
)

# ============================================================================
# 2. GET SUMMARY
# ============================================================================
_summary_desc = (
    "**Tool: get_wikipedia_summary_tool** - Get article introduction/summary.\n"
    "**PREFERRED for known subjects**: Use directly when title is identifiable "
    "(proper nouns, famous people, places, concepts).\n"
    "**Use for**: 'Who is X?', 'What is Y?', 'Tell me about Z', definitions, bios."
)
get_wikipedia_summary_catalogue_manifest = ToolManifest(
    name="get_wikipedia_summary_tool",
    agent="wikipedia_agent",
    description=_summary_desc,
    # VERY RESTRICTIVE: Only trigger when user explicitly mentions "Wikipedia"
    # Queries like "who is Einstein" should go to unified_web_search
    # Keywords in ENGLISH ONLY (semantic pivot translates all queries to English)
    semantic_keywords=[
        "Wikipedia summary",
        "Wikipedia page",
        "on Wikipedia",
        "from Wikipedia",
    ],
    parameters=[
        ParameterSchema(
            name="title", type="string", required=True, description="Exact article title"
        ),
        _LANG_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="title", type="string", description="Title"),
        OutputFieldSchema(path="summary", type="string", description="Text", semantic_type="text"),
        OutputFieldSchema(path="url", type="string", description="URL", semantic_type="URL"),
        OutputFieldSchema(path="thumbnail", type="string", nullable=True, description="Image"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=500, est_cost_usd=0.001, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="wikipedias",  # Must match CONTEXT_DOMAIN_WIKIPEDIA (domain + "s" pattern)
    reference_examples=["summary", "url"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📖", i18n_key="get_wikipedia_summary", visible=True, category="tool"
    ),
)

# ============================================================================
# 3. GET FULL ARTICLE
# ============================================================================
_article_desc = (
    "**Tool: get_wikipedia_article_tool** - Get full article content.\n"
    "High token cost, use sparingly. Requires exact 'title'.\n"
    "**Use for**: Deep research, comprehensive details."
)
get_wikipedia_article_catalogue_manifest = ToolManifest(
    name="get_wikipedia_article_tool",
    agent="wikipedia_agent",
    description=_article_desc,
    # VERY RESTRICTIVE: Only trigger when user explicitly mentions "Wikipedia"
    # Keywords in ENGLISH ONLY (semantic pivot translates all queries to English)
    semantic_keywords=[
        "full Wikipedia article",
        "complete Wikipedia article",
        "Wikipedia article content",
        "read Wikipedia article",
    ],
    parameters=[
        ParameterSchema(
            name="title", type="string", required=True, description="Exact article title"
        ),
        ParameterSchema(
            name="sections",
            type="boolean",
            required=False,
            description="Include section headers (def: True)",
        ),
        ParameterSchema(
            name="max_length",
            type="integer",
            required=False,
            description="Char limit (def: 10000)",
            constraints=[ParameterConstraint(kind="maximum", value=50000)],
        ),
        _LANG_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="title", type="string", description="Title"),
        OutputFieldSchema(
            path="content", type="string", description="Full text", semantic_type="text"
        ),
        OutputFieldSchema(path="sections", type="array", description="Headers"),
        OutputFieldSchema(path="url", type="string", description="URL", semantic_type="URL"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=3000, est_cost_usd=0.005, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="wikipedias",  # Must match CONTEXT_DOMAIN_WIKIPEDIA (domain + "s" pattern)
    reference_examples=["content", "sections"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📚", i18n_key="get_wikipedia_article", visible=True, category="tool"
    ),
)

# ============================================================================
# 4. GET RELATED
# ============================================================================
_related_desc = (
    "**Tool: get_wikipedia_related_tool** - Get related/linked articles for exploration."
)
get_wikipedia_related_catalogue_manifest = ToolManifest(
    name="get_wikipedia_related_tool",
    agent="wikipedia_agent",
    description=_related_desc,
    parameters=[
        ParameterSchema(name="title", type="string", required=True, description="Source title"),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max (def: {WIKIPEDIA_TOOL_DEFAULT_LIMIT}, max: {WIKIPEDIA_TOOL_DEFAULT_MAX_RESULTS})",
            constraints=[
                ParameterConstraint(kind="maximum", value=WIKIPEDIA_TOOL_DEFAULT_MAX_RESULTS)
            ],
        ),
        _LANG_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="title", type="string", description="Source"),
        OutputFieldSchema(path="related", type="array", description="Linked articles"),
        OutputFieldSchema(path="related[].title", type="string", description="Article title"),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="wikipedias",  # Must match CONTEXT_DOMAIN_WIKIPEDIA (domain + "s" pattern)
    reference_examples=["related[0].title"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🔗", i18n_key="get_wikipedia_related", visible=True, category="tool"
    ),
)

__all__ = [
    "search_wikipedia_catalogue_manifest",
    "get_wikipedia_summary_catalogue_manifest",
    "get_wikipedia_article_catalogue_manifest",
    "get_wikipedia_related_catalogue_manifest",
]
