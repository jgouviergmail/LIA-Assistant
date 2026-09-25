"""Catalogue manifests for the memory search tool (ADR-313).

Long-term memory as an active, routable capability. Internal, no OAuth,
read-only — the passive per-turn profile injection is unchanged. Every bound
published here is the bound the tool enforces, read from the SAME source
(ADR-184): the category vocabulary from ``MemoryCategoryType``, the result
ceiling from ``settings.memory_max_results``.
"""

from datetime import UTC, datetime
from typing import get_args

from src.core.config import settings
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
from src.domains.agents.tools.memory_tools import MemoryCategoryType

#: The families a lookup may be narrowed to — the stored vocabulary itself.
MEMORY_SEARCH_CATEGORIES: tuple[str, ...] = get_args(MemoryCategoryType)

#: Shortest subject a lookup accepts (a published ``min_length``).
MEMORY_SEARCH_QUERY_MIN_CHARS = 2

# =============================================================================
# Agent Manifest: memory_agent
# =============================================================================

MEMORY_AGENT_MANIFEST = AgentManifest(
    name="memory_agent",
    description=(
        "Agent specialized in what LIA remembers about the user: long-term "
        "memories built from past conversations (preferences, people, habits, "
        "significant events, standing instructions). Semantic lookup. Read-only."
    ),
    tools=["search_memories_tool"],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="🧠",
        i18n_key="memory_agent",
        visible=True,
        category="agent",
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: search_memories_tool
# =============================================================================

search_memories_catalogue_manifest = ToolManifest(
    name="search_memories_tool",
    agent="memory_agent",
    description=(
        "Search what LIA REMEMBERS about the user (long-term memory built from "
        "past conversations): preferences, the people in their life, habits, "
        "significant events, standing instructions they gave. Use it to look up "
        "a subject the request does not settle — a person, a place, a preference, "
        "a rule — for example the sender of an e-mail just read. The memories "
        "most relevant to the user's message already reach the answer: search "
        "for a subject the message does not name. An empty result means nothing "
        "is remembered about it; a failure means the search could not run, never "
        "that nothing is remembered. Read-only: never call it to store something "
        "new (memories are extracted from the conversation automatically). NOT "
        "the address book (contact), NOT the user's documents (document)."
    ),
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description=(
                "The subject to look up, in a few words, in the user's language "
                "(memories are stored as they were said)."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=MEMORY_SEARCH_QUERY_MIN_CHARS)
            ],
        ),
        ParameterSchema(
            name="category",
            type="string",
            required=False,
            # The families are listed FROM the vocabulary the enum publishes: a
            # family added to MemoryCategoryType must not leave this sentence stale.
            description=(
                f"Narrow to one family: {', '.join(MEMORY_SEARCH_CATEGORIES)} "
                "(procedural = the standing instructions the user gave)."
            ),
            constraints=[ParameterConstraint(kind="enum", value=list(MEMORY_SEARCH_CATEGORIES))],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Most memories to return (default: the maximum).",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=settings.memory_max_results),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="memories",
            type="array",
            description="Matching memories, most relevant first",
        ),
        OutputFieldSchema(
            path="memories[].content",
            type="string",
            description="What is remembered, as it was recorded",
        ),
        OutputFieldSchema(
            path="memories[].category",
            type="string",
            description="The memory's family",
        ),
        OutputFieldSchema(
            path="memories[].usage_nuance",
            type="string",
            nullable=True,
            description=("How the memory may be used; an OBLIGATION when 'sensitive' is true"),
        ),
        OutputFieldSchema(
            path="memories[].sensitive",
            type="boolean",
            description="A sensitive or painful memory: follow its usage_nuance",
        ),
        OutputFieldSchema(
            path="memories[].recorded_on",
            type="string",
            nullable=True,
            description="ISO date the memory was recorded",
        ),
        OutputFieldSchema(
            path="count",
            type="integer",
            description="Number of memories returned",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40,
        est_tokens_out=300,
        est_cost_usd=0.00002,
        est_latency_ms=400,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "what do you remember about me",
        "what do you know about this person",
        "look up what I told you before",
        "the standing rules I gave you",
        "my usual preference for this",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="🧠",
        i18n_key="search_memories",
        visible=True,
        category="tool",
    ),
    tool_category="search",
    # A vector store: conceptual terms are what it matches, never a leak the
    # validator should strip (ADR-318 found every semantic store undeclared).
    text_search_mode="semantic",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "MEMORY_AGENT_MANIFEST",
    "MEMORY_SEARCH_CATEGORIES",
    "MEMORY_SEARCH_QUERY_MIN_CHARS",
    "search_memories_catalogue_manifest",
]
