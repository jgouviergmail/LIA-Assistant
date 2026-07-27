"""Structured-output contract of the query analyzer.

The analyzer LLM answers with one JSON object per turn; these models are what
that object is parsed into. They live apart from the service because they are a
*contract* — read by the context-resolution service and by the tests — while
the service around them is orchestration.

Extracted from ``query_analyzer_service.py`` on 2026-07-27 (ADR-160), which had
reached its frozen size cap: the file may only shrink, so the feature moved out
rather than the cap moving up.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField

from src.domains.agents.services.analysis.skill_suppression import normalize_skill_name

__all__ = [
    "ConstraintHints",
    "ContextReferenceOutput",
    "QueryAnalysisOutput",
    "ResolvedReference",
]


class ResolvedReference(BaseModel):
    """A resolved reference from the query."""

    original: str = PydanticField(description="Original reference in user query")
    resolved: str = PydanticField(description="Resolved value")
    type: str = PydanticField(description="Reference type: temporal, person, contextual")


class ConstraintHints(BaseModel):
    """Detected constraints in user query for filtering results.

    OpenAI structured output requires explicit field definitions.
    Using dict[str, bool] generates additionalProperties which is incompatible.
    """

    has_distance: bool = PydanticField(default=False, description="Distance/proximity criterion")
    has_quality: bool = PydanticField(default=False, description="Quality/rating criterion")
    has_iteration: bool = PydanticField(default=False, description="Per-item iteration pattern")
    has_time: bool = PydanticField(default=False, description="Temporal constraint")
    has_count: bool = PydanticField(default=False, description="Numeric count limit")


class ContextReferenceOutput(BaseModel):
    """LLM-detected reference to items from previous conversation results.

    Populated by the QueryAnalyzer LLM to indicate whether the user's query
    references specific items from a previous assistant response (ordinal,
    demonstrative, or pronoun references). Used by ContextResolutionService
    to resolve references to actual items via ToolContextManager.

    Examples of has_reference=True:
        - "details of the first one" → ordinal, ordinal_positions=[1]
        - "delete this email" → demonstrative, reference_domain="email"
        - "reply to it" → pronoun, reference_domain="email"

    Examples of has_reference=False:
        - "this photo is nice" → attachment, not a previous result
        - "this morning" → temporal expression
        - "search for restaurants" → new query
    """

    has_reference: bool = PydanticField(
        default=False,
        description=(
            "True ONLY when user refers to a specific item from a previous assistant response "
            "in the conversation (ordinal like 'the 2nd one', demonstrative like 'this email', "
            "or pronoun like 'reply to it'). "
            "False for attachments ('this photo'), temporal expressions ('this morning'), "
            "new queries, or general conversation."
        ),
    )
    reference_type: str = PydanticField(
        default="none",
        description=(
            "'ordinal' (the first, the 2nd, the last, the 1st and 3rd), "
            "'demonstrative' (this email, that contact), "
            "'pronoun' (it, them, reply to him), "
            "or 'none'"
        ),
    )
    ordinal_positions: list[int] = PydanticField(
        default_factory=list,
        description=(
            "1-based positions for ordinal references. "
            "Examples: [1] for 'the first', [2] for 'the second', "
            "[1, 3] for 'the first and third', [-1] for 'the last'. "
            "Empty list when not an ordinal reference."
        ),
    )
    reference_domain: str = PydanticField(
        default="",
        description=(
            "Domain of the referenced items, using the domain name from AVAILABLE DOMAINS "
            "(singular form): contact, email, event, task, file, place, reminder. "
            "Empty string if domain should be inferred from last search context."
        ),
    )


class QueryAnalysisOutput(BaseModel):
    """Structured output from query analysis LLM."""

    model_config = ConfigDict(extra="ignore")

    intent: str = PydanticField(description="action or conversation")
    primary_domain: str | None = PydanticField(
        default=None, description="Primary domain for the query"
    )
    secondary_domains: list[str] = PydanticField(
        default_factory=list, description="Additional domains needed"
    )
    confidence: float = PydanticField(default=0.8, ge=0.0, le=1.0, description="Confidence 0-1")
    english_query: str = PydanticField(
        description="Complete self-contained query in English with ALL actions preserved"
    )
    resolved_references: list[ResolvedReference] = PydanticField(
        default_factory=list, description="Resolved references from context/memory"
    )
    reasoning: str = PydanticField(description="Reasoning in max 10 words")
    is_mutation_intent: bool = PydanticField(
        default=False,
        description="True if user wants to create, update, delete, or send",
    )
    has_cardinality_risk: bool = PydanticField(
        default=False,
        description="True if intent targets a set (all/every/each/entire)",
    )
    for_each_detected: bool = PydanticField(
        default=False,
        description=(
            "True ONLY when user wants the SAME action REPEATED on EACH item of a collection "
            "(e.g., 'delete all my emails', 'cancel every meeting'). "
            "False when user names specific recipients/targets "
            "(e.g., 'send an email to Alice and Bob' = ONE email with 2 recipients, NOT for_each)."
        ),
    )
    for_each_collection_key: str | None = PydanticField(
        default=None,
        description="Collection to iterate: contacts, events, places, emails, tasks, or files",
    )
    cardinality_magnitude: int | None = PydanticField(
        default=None,
        description="Explicit count: 'tous/all' → 999, number → N, unknown → null",
    )
    constraint_hints: ConstraintHints = PydanticField(
        default_factory=ConstraintHints,
        description="Detected query constraints for result filtering",
    )
    context_reference: ContextReferenceOutput = PydanticField(
        default_factory=ContextReferenceOutput,
        description=(
            "Detected reference to items from a previous assistant response. "
            "Set has_reference=true only when user points to previously returned results."
        ),
    )
    encyclopedia_keywords: list[str] = PydanticField(
        default_factory=list,
        description="1-3 encyclopedic keywords in user's original language for web enrichment",
    )
    is_news_query: bool = PydanticField(
        default=False,
        description="True only if user explicitly asks for news or recent events",
    )
    is_app_help_query: bool = PydanticField(
        default=False,
        description="True if user asks about THIS AI assistant's features or usage",
    )
    skill_name: str | None = PydanticField(
        default=None,
        description="Matching skill name from AVAILABLE SKILLS, or null",
    )
    semantic_filter_terms: list[str] = PydanticField(
        default_factory=list,
        description=(
            "Probabilistic HINT for downstream planning — not authoritative. "
            "List semantic qualifiers in the user query that describe item "
            "categories, qualities, or priorities WITHOUT literal counterparts "
            "in structured fields (e.g., 'medical', 'urgent', 'important', "
            "'best', 'professional', 'recent'). Emit the English-pivoted form "
            "(lowercase). Leave empty if: (a) no such qualifiers, OR (b) the "
            "user explicitly cites the term as a literal value to match "
            "(quoted, or 'with X in the title'). These terms should NOT be "
            "passed as `query` to indexable stores — they need downstream "
            "filtering by the Response LLM."
        ),
    )
    has_temporal_reference: bool = PydanticField(
        default=False,
        description=(
            "True when the query contains ANY concrete time bound that says WHEN "
            "to look: an explicit date ('on Aug 15'), a relative day/period "
            "('tomorrow', 'the day after tomorrow', 'the next 2 days', 'next "
            "week', 'this weekend', 'in August', 'today'). False for open/vague "
            "horizons with NO specific bound ('my next appointments', "
            "'upcoming events', 'my next 3 meetings') and for queries with no "
            "time reference at all. Used to keep user-intended date bounds while "
            "discarding bounds the planner may hallucinate for open queries."
        ),
    )

    @field_validator("skill_name", mode="after")
    @classmethod
    def _normalize_skill_name(cls, value: str | None) -> str | None:
        """Map the model's textual "null" onto a real absent value.

        The prompt says "leave it null" in prose and the structured output is
        not strict, so the model writes the four characters ``null`` — truthy
        for every ``if skill_name:`` downstream. Normalising here keeps that
        parsing artefact out of the routing, the planner bypass and the logs.

        Args:
            value: Raw field value from the LLM.

        Returns:
            The stripped name, or None when blank or a sentinel.
        """
        return normalize_skill_name(value)
