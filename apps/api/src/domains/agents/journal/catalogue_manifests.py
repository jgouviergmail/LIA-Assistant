"""Catalogue manifests for the journal search tool (ADR-318).

LIA's own journal — the directives, patterns and portrait facets it writes from
its conversations with the person — as an active, routable lookup. Internal, no
OAuth, read-only; the passive per-turn injection is unchanged. Registered only
where the deployment ships journals (``JOURNALS_ENABLED``), and gated at call
time by the operator's switch and the person's own preference. Every bound
published here is the bound the tool enforces, read from the same setting
(ADR-184).
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.constants import AGENT_JOURNAL
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: Shortest subject a lookup accepts (a published ``min_length``).
JOURNAL_SEARCH_QUERY_MIN_CHARS = 2

#: The wording of the lookup's parameters, read by the manifest AND the schema.
JOURNAL_QUERY_DESCRIPTION = (
    "The subject to look up in LIA's journal, in a few words, in the user's language."
)
JOURNAL_MAX_RESULTS_DESCRIPTION = (
    f"Most entries to return, 1 to {settings.journal_search_max_results} (default: the maximum)."
)

# =============================================================================
# Agent Manifest: journal_agent
# =============================================================================

JOURNAL_AGENT_MANIFEST = AgentManifest(
    name=AGENT_JOURNAL,
    description=(
        "Agent for LIA's own journal: the directives, patterns and portrait facets "
        "LIA wrote from its past conversations with the user. Semantic lookup. "
        "Read-only."
    ),
    tools=["search_journal_tool"],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(emoji="📓", i18n_key="journal_agent", visible=True, category="agent"),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: search_journal_tool
# =============================================================================

search_journal_catalogue_manifest = ToolManifest(
    name="search_journal_tool",
    agent=AGENT_JOURNAL,
    description=(
        "**Tool: search_journal_tool** - Search LIA's OWN journal: what LIA noted "
        "for itself from past conversations — how to work with the user (directives "
        "such as 'WHEN … → DO …'), patterns it observed, facets of its portrait of "
        "the user. Use it when LIA is asked what it noticed, learned or noted, or to "
        "recall how it should handle a subject the request does not settle. The "
        "entries most relevant to the user's message already reach the answer: search "
        "for a subject the message does not name. An empty result means nothing is "
        "noted on it; a failure means the search could not run, never that nothing "
        "is noted. NOT the user's memories (memory), NOT their documents (document)."
    ),
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description=JOURNAL_QUERY_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="min_length", value=JOURNAL_SEARCH_QUERY_MIN_CHARS)
            ],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=JOURNAL_MAX_RESULTS_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=settings.journal_search_max_results),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="entries", type="array", description="Matching entries, most relevant first"
        ),
        OutputFieldSchema(path="entries[].title", type="string", description="Entry title"),
        OutputFieldSchema(
            path="entries[].content", type="string", description="What LIA wrote, as written"
        ),
        OutputFieldSchema(
            path="entries[].kind",
            type="string",
            description="directive, pattern or portrait_facet",
        ),
        OutputFieldSchema(
            path="entries[].confidence",
            type="string",
            nullable=True,
            description="low (a hypothesis), medium, high (confirmed by the user's reactions)",
        ),
        OutputFieldSchema(
            path="entries[].written_on",
            type="string",
            nullable=True,
            description="ISO date the entry was written",
        ),
        OutputFieldSchema(
            path="count",
            type="integer",
            description="Number of entries returned — the most relevant, at most max_results",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40, est_tokens_out=400, est_cost_usd=0.00002, est_latency_ms=400
    ),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "what did you note about me in your journal",
        "what have you learned about how I work",
        "what did you notice about my habits",
        "your own notes on this subject",
    ],
    reference_examples=["entries[0].content"],
    display=DisplayMetadata(emoji="📓", i18n_key="search_journal", visible=True, category="tool"),
    tool_category="search",
    # The injection already serves the entries the message evokes: a proactive
    # lookup would re-read what the turn holds.
    initiative_eligible=False,
    # A vector store: conceptual terms are what it matches, never a leak.
    text_search_mode="semantic",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "JOURNAL_AGENT_MANIFEST",
    "JOURNAL_MAX_RESULTS_DESCRIPTION",
    "JOURNAL_QUERY_DESCRIPTION",
    "JOURNAL_SEARCH_QUERY_MIN_CHARS",
    "search_journal_catalogue_manifest",
]
