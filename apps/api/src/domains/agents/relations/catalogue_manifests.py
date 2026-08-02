"""Catalogue manifests for the three CRM read tools.

Each lives in the domain whose catalogue lacked a read capability — telephony
could only place a call, so a question about a past call had no honest way to
cover its own primary domain (production 2026-08-01).

None of them declares ``serves_domains``: reaching them from ``contact`` was
measured to evict three mutation tools per crowded catalogue. And none declares
``context_key`` — they answer a question, they do not open a browsable list, so
they must not overwrite the conversational context of the real ``tasks`` or
``peers`` collections.
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.constants import AGENT_PEER, AGENT_TASK, AGENT_TELEPHONY
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)


def _person_parameter() -> ParameterSchema:
    """The subject of the question — a person, as the user names them."""
    return ParameterSchema(
        name="person_name",
        type="string",
        required=True,
        description=(
            "Person the question is about, as the user says it. Resolved "
            "through the same name folding as the relationship card."
        ),
        constraints=[
            ParameterConstraint(kind="min_length", value=2),
            ParameterConstraint(kind="max_length", value=120),
        ],
        semantic_type="person_name",
    )


def _limit_parameter() -> ParameterSchema:
    """Page size — with the ceiling PUBLISHED, not merely enforced (ADR-184)."""
    ceiling = settings.relations_max_items_per_section
    return ParameterSchema(
        name="limit",
        type="integer",
        required=False,
        description=f"Items to return (default and max: {ceiling}).",
        constraints=[
            ParameterConstraint(kind="minimum", value=1),
            ParameterConstraint(kind="maximum", value=ceiling),
        ],
    )


def _identity_outputs() -> list[OutputFieldSchema]:
    """Who the answer is about — so the model never re-guesses the person."""
    return [
        OutputFieldSchema(
            path="person",
            type="string",
            description="Relationship the answer is about.",
            semantic_type="person_name",
        ),
        OutputFieldSchema(
            path="identity_confidence",
            type="string",
            description="How confidently the name was matched (high | medium | low).",
        ),
        OutputFieldSchema(
            path="is_peer",
            type="boolean",
            description="Whether this person is a CONNECTED user of this LIA instance.",
        ),
    ]


_CALLS_DESC = (
    "**Tool: get_calls_tool** - READ the past calls with ONE person: what the "
    "call was about, how it ended, its summary and when it happened. Use for "
    "'when did I last call X', 'what did we discuss on the phone', 'my recent "
    "calls with X'. This is the READ side of telephony — it never places a "
    "call. To actually phone someone, that is place_phone_call_tool."
)

get_calls_catalogue_manifest = ToolManifest(
    name="get_calls_tool",
    agent=AGENT_TELEPHONY,
    description=_CALLS_DESC,
    semantic_keywords=[
        "when did I last call this person",
        "what did we say on the phone",
        "my recent phone calls with someone",
        "history of calls with a person",
        "outcome of my last call with them",
    ],
    parameters=[_person_parameter(), _limit_parameter()],
    outputs=[
        *_identity_outputs(),
        OutputFieldSchema(
            path="calls",
            type="array",
            description="Page of past calls, newest first: objective, outcome, summary, instant.",
        ),
        OutputFieldSchema(
            path="calls_total",
            type="integer",
            description=(
                "EXACT number of calls with this person (database aggregate). "
                "Never count the rows to answer 'how many' — the array is a page."
            ),
        ),
    ],
    cost=CostProfile(est_tokens_in=60, est_tokens_out=250, est_cost_usd=0.0002, est_latency_ms=250),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    max_iterations=1,
    reference_examples=["calls[0].objective", "calls[0].occurred_at", "calls_total", "person"],
    display=DisplayMetadata(emoji="📞", i18n_key="get_calls", visible=True, category="tool"),
    tool_category="search",
    version="1.0.0",
    maintainer="Team Agents",
    updated_at=datetime.now(UTC),
)

_OPEN_LOOPS_DESC = (
    "**Tool: get_open_loops_tool** - READ the open commitments with ONE person: "
    "what the user owes them, what they owe the user, and for how long. Use for "
    "'what do I owe X', 'where do we stand with X', 'anything pending with X'. "
    "These are CRM commitments captured from conversations — "
    "NOT the user's task list (that is get_tasks_tool)."
)

get_open_loops_catalogue_manifest = ToolManifest(
    name="get_open_loops_tool",
    agent=AGENT_TASK,
    description=_OPEN_LOOPS_DESC,
    semantic_keywords=[
        "what do I owe this person",
        "what is pending between us",
        "open commitments with someone",
        "what am I waiting for from them",
        "unfinished business with a person",
    ],
    parameters=[_person_parameter(), _limit_parameter()],
    outputs=[
        *_identity_outputs(),
        OutputFieldSchema(
            path="open_loops",
            type="array",
            description=(
                "Page of open commitments: subject, direction, days open, and "
                "`due_hint` when a deadline was captured — absent means none was."
            ),
        ),
        OutputFieldSchema(
            path="open_loops_total",
            type="integer",
            description="EXACT number of open commitments (database aggregate).",
        ),
    ],
    cost=CostProfile(est_tokens_in=60, est_tokens_out=250, est_cost_usd=0.0002, est_latency_ms=250),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    max_iterations=1,
    reference_examples=["open_loops[0].subject", "open_loops_total", "person"],
    display=DisplayMetadata(emoji="🔄", i18n_key="get_open_loops", visible=True, category="tool"),
    tool_category="search",
    version="1.0.0",
    maintainer="Team Agents",
    updated_at=datetime.now(UTC),
)

_PEER_MESSAGES_DESC = (
    "**Tool: get_peer_messages_tool** - READ the messages relayed through LIA "
    "with ONE connected person: direction, text and instant. Use for 'what did "
    "I pass on to them', 'did they reply', 'our recent exchanges through LIA'. "
    "To SEND one, that is send_peer_message_tool."
)

get_peer_messages_catalogue_manifest = ToolManifest(
    name="get_peer_messages_tool",
    agent=AGENT_PEER,
    description=_PEER_MESSAGES_DESC,
    semantic_keywords=[
        "what did I relay to this person through LIA",
        "did they answer my relayed message",
        "our recent exchanges through the assistant",
        "messages passed between our assistants",
        "history of relayed messages with someone",
    ],
    parameters=[_person_parameter(), _limit_parameter()],
    outputs=[
        *_identity_outputs(),
        OutputFieldSchema(
            path="peer_messages",
            type="array",
            description=(
                "Page of relayed messages. `content` is null when the text is "
                "not the user's to show (a delivered directive is scrubbed): "
                "the exchange happened, say so without inventing its words."
            ),
        ),
        OutputFieldSchema(
            path="peer_messages_total",
            type="integer",
            description=(
                "EXACT number of relayed messages — present ONLY when both "
                "directions were kept. Absent means no exact count describes "
                "the list: do not state one."
            ),
        ),
    ],
    cost=CostProfile(est_tokens_in=60, est_tokens_out=250, est_cost_usd=0.0002, est_latency_ms=250),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="SENSITIVE"
    ),
    max_iterations=1,
    reference_examples=["peer_messages[0].content", "peer_messages_total", "person"],
    display=DisplayMetadata(
        emoji="✉️", i18n_key="get_peer_messages", visible=True, category="tool"
    ),
    tool_category="search",
    version="1.0.0",
    maintainer="Team Agents",
    updated_at=datetime.now(UTC),
)

#: Every manifest of this family, so registration and tests iterate ONE list.
RELATION_READ_MANIFESTS = (
    get_calls_catalogue_manifest,
    get_open_loops_catalogue_manifest,
    get_peer_messages_catalogue_manifest,
)

__all__ = [
    "RELATION_READ_MANIFESTS",
    "get_calls_catalogue_manifest",
    "get_open_loops_catalogue_manifest",
    "get_peer_messages_catalogue_manifest",
]
