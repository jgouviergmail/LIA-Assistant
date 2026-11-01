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

from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField

from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis, read_analysis
from src.domains.agents.analysis.requested_outcomes import GoalRequirement
from src.domains.agents.analysis.resolved_references import (
    AnalyzerReferenceType,
    parse_reference_type,
)
from src.domains.agents.services.analysis.skill_suppression import normalize_skill_name

__all__ = [
    "DESCRIPTIVE_SELECTIONS",
    "DESCRIPTIVE_SELECTION_LATEST",
    "DESCRIPTIVE_SELECTION_ONE",
    "REFERENCE_TYPE_DESCRIPTIVE",
    "ConstraintHints",
    "ContextReferenceOutput",
    "QueryAnalysisOutput",
    "ResolvedReference",
]

#: A shown item designated by WHAT it is or WHO it involves (ADR-367).
REFERENCE_TYPE_DESCRIPTIVE: Final = "descriptive"
#: The one item a description designates — asked about when several fit.
DESCRIPTIVE_SELECTION_ONE: Final = "one"
#: The most recent item a description fits, when the person asks for it.
DESCRIPTIVE_SELECTION_LATEST: Final = "latest"
DESCRIPTIVE_SELECTIONS: Final = frozenset({DESCRIPTIVE_SELECTION_ONE, DESCRIPTIVE_SELECTION_LATEST})


class ResolvedReference(BaseModel):
    """A resolved reference from the query, typed by what its VALUE is."""

    original: str = PydanticField(description="Original reference in user query")
    resolved: str = PydanticField(description="Resolved value")
    type: AnalyzerReferenceType = PydanticField(
        default=AnalyzerReferenceType.CONTEXTUAL,
        description=(
            "What the resolved value is: person (a person's name), place (a place, a city "
            "or an address), temporal (a date, a time or a range), contextual (anything else)"
        ),
    )

    @field_validator("type", mode="before")
    @classmethod
    def _read_type(cls, raw: object) -> AnalyzerReferenceType:
        """A type outside the vocabulary is ``contextual`` — never a failed analysis."""
        return parse_reference_type(raw)


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
    """LLM-detected reference to an item already shown to the person.

    Populated by the QueryAnalyzer LLM to indicate whether the user's query
    designates a specific item a previous result showed — by position, by
    pointing at it, by a pronoun, or by DESCRIBING it (ADR-367). Used by
    ContextResolutionService to resolve the reference to the shown item: the
    model only reads the request; which items a description designates is
    decided by code (``context/descriptor_match.py``).

    Examples of has_reference=True:
        - "details of the first one" → ordinal, ordinal_positions=[1]
        - "delete this email" → demonstrative, reference_domain="email"
        - "reply to it" → pronoun, reference_domain="email"
        - "reply to Marc's email" → descriptive, descriptor="Marc"

    Examples of has_reference=False:
        - "this photo is nice" → attachment, not a previous result
        - "this morning" → temporal expression
        - "search for restaurants" → new query
        - "send an email to Alice" → something new is created
    """

    has_reference: bool = PydanticField(
        default=False,
        description=(
            "True when the user designates a specific item already shown to them — by "
            "position, by pointing at it, by a pronoun, or by describing it. False for "
            "attachments, temporal expressions, new searches, operations on a whole set, "
            "something newly created, or general conversation."
        ),
    )
    reference_type: str = PydanticField(
        default="none",
        description=(
            "'ordinal' (by position), 'demonstrative' (this/that item), 'pronoun' (it, "
            "them), 'descriptive' (by its sender, a recipient, a person or place it "
            "involves, a word of its subject, title or name), or 'none'"
        ),
    )
    descriptor: str = PydanticField(
        default="",
        description=(
            "Descriptive references only: the words that single the item out (names, "
            "subject or title words) as the user wrote them, in their base form, "
            "without articles, prepositions, the action or the kind of item. Empty "
            "otherwise."
        ),
    )
    selection: str = PydanticField(
        default=DESCRIPTIVE_SELECTION_ONE,
        description=(
            "Descriptive references only: 'one' (default), or 'latest' only when the "
            "user explicitly asks for the most recent matching item."
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

    @field_validator("selection", mode="before")
    @classmethod
    def _read_selection(cls, raw: object) -> str:
        """A selection outside the vocabulary is ``one`` — never a failed analysis."""
        value = str(raw or "").strip().lower()
        return value if value in DESCRIPTIVE_SELECTIONS else DESCRIPTIVE_SELECTION_ONE


class QueryAnalysisOutput(BaseModel):
    """Structured output from query analysis LLM."""

    model_config = ConfigDict(extra="ignore")

    requested_outcomes: list[GoalRequirement] = PydanticField(
        default_factory=list,
        description="Explicit results requested in the current message, with exact source quotes; no anticipated needs.",
    )

    efficacy_analysis: EfficacyAnalysis = PydanticField(
        default_factory=EfficacyAnalysis,
        description="At most two cognitive domains of the explicit user request; empty if uncertain. Clarification/verification describe a current need, never a personality judgement.",
    )

    @field_validator("efficacy_analysis", mode="before")
    @classmethod
    def read_optional_efficacy(cls, raw: object) -> EfficacyAnalysis:
        return read_analysis(raw)

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
