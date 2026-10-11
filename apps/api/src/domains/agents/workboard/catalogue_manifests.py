"""Catalogue manifests for the workboard tools (ADR-276, lot 3).

Six capabilities over the person's own board of tickets: create one, change
one, comment on one, list them, read one, delete one.

Two rules shape every manifest here, and neither is decoration:

- **every bound the service enforces is PUBLISHED** as a
  :class:`ParameterConstraint` read from settings (ADR-184). An enforced but
  hidden bound is not a contract, it is a trap: the planner produces a value it
  cannot know is too long, the validator rejects it, and the model gets blamed
  for obeying. Reading them from ``settings`` rather than typing the numbers is
  the other half — a ``.env`` change must move the published bound with the
  enforced one.
- **a description says what the capability is NOT.** A ticket is confused with
  three neighbouring things — a provider to-do, a timed notification, a
  scheduled routine — and the router only has these sentences to tell them
  apart.

The tools themselves hold no business rule: ``WorkboardService`` owns the
rights, the bounds and the transitions, and a tool that decided any of them
again would be a second authority.
"""

from dataclasses import replace
from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.agents.constants import CONTEXT_DOMAIN_TICKETS
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
from src.domains.agents.workboard.creation_manifest import (
    create_ticket_catalogue_manifest as create_ticket_catalogue_manifest,
)

#: Every column of the board, spelled for a model that must pick one. Derived
#: from nothing on purpose: the enum's values are what the API accepts, and
#: this sentence is what a model reads — they are checked against each other by
#: ``test_workboard_manifests``.
_COLUMNS = "idea, todo, in_progress, waiting, confirming, validating, done"

TICKET_AGENT_MANIFEST = AgentManifest(
    name="ticket_agent",
    description=(
        "Agent specialized in the user's own WORKBOARD: a board of tickets in "
        "seven columns that the user — or LIA on their behalf — works through. "
        "Create a ticket, move it between columns, comment on it, list what is "
        "on the board or overdue, hand one to LIA or to a connected user, "
        "delete one. NOT the user's provider to-do list (use task), NOT a "
        "timed notification (use reminder), NOT a recurring scheduled job "
        "(use automation)."
    ),
    tools=[
        "create_ticket_tool",
        "update_ticket_tool",
        "comment_ticket_tool",
        "list_tickets_tool",
        "get_ticket_tool",
        "delete_ticket_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="🗂️",
        i18n_key="ticket_agent",
        visible=True,
        category="agent",
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


#: How a tool names the ticket it acts on. The service resolves an id OR a
#: unique folded title, and REFUSES an ambiguous one rather than guessing —
#: handing one ticket's fate to a question about another is the failure this
#: parameter exists to avoid.
_TICKET_REFERENCE = ParameterSchema(
    name="ticket",
    type="string",
    required=True,
    description=(
        "The ticket: its id, or its exact title. A title matching several "
        "tickets is refused rather than guessed at — ask the user which one."
    ),
    constraints=[
        ParameterConstraint(kind="min_length", value=1),
        ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars),
    ],
)


def _ticket_outputs(prefix: str) -> list[OutputFieldSchema]:
    """Expose the same summary leaves every workboard tool actually produces."""
    return [
        OutputFieldSchema(
            path=f"{prefix}.id",
            type="string",
            description="Ticket UUID",
            semantic_type="ticket_id",
        ),
        OutputFieldSchema(
            path=f"{prefix}.title", type="string", description="Ticket title", semantic_type="Text"
        ),
        OutputFieldSchema(
            path=f"{prefix}.status",
            type="string",
            description="Workboard column",
            semantic_type="ticket_status",
        ),
        OutputFieldSchema(
            path=f"{prefix}.priority",
            type="string",
            description="Priority",
            semantic_type="ticket_priority",
        ),
        OutputFieldSchema(
            path=f"{prefix}.start_at",
            type="string",
            nullable=True,
            description="Start instant (ISO 8601)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            path=f"{prefix}.due_at",
            type="string",
            nullable=True,
            description="Due instant (ISO 8601)",
            semantic_type="datetime",
        ),
    ]


update_ticket_catalogue_manifest = ToolManifest(
    name="update_ticket_tool",
    mutation_policy="draft",
    initiative_eligible=False,
    agent="ticket_agent",
    description=(
        "Changes a ticket on the workboard: its column, priority, dates, "
        "title, description, who holds it, or whether the user follows it. "
        "Use for 'move this ticket to in progress', 'close…', 'push… back to "
        "Thursday', 'give this ticket to Marie', 'hand this to LIA'. Set run_now=true to "
        "ask LIA to run a ticket it holds right away instead of waiting for "
        "the sweep. Only the fields given are changed."
        " Preparation produces mandatory native human confirmation, without persisting a change or "
        "sending notifications. Use request for the full current source UI schema, including clearing "
        "dates, execution mode, move with position, and run_now; it is exclusive with legacy fields. "
        "Source rights and actual predicted consequences are shown. A changed ticket, peer relationship, "
        "answer note or affected column requires a new proposal. LIA work remains subject to normal "
        "quotas and costs; requesting a run never claims its completion. Assignment notices follow commit."
    ),
    parameters=[
        replace(_TICKET_REFERENCE, required=False),
        ParameterSchema(
            name="request",
            type="object",
            required=False,
            description="Full current UI update, exclusive with legacy fields",
            schema=WorkboardUpdateInput.model_json_schema(),
        ),
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=f"Move it to this column: {_COLUMNS}.",
            constraints=[ParameterConstraint(kind="enum", value=_COLUMNS.split(", "))],
            semantic_type="ticket_status",
        ),
        ParameterSchema(
            name="priority",
            type="string",
            required=False,
            description="low | medium | high | urgent.",
            constraints=[
                ParameterConstraint(kind="enum", value=["low", "medium", "high", "urgent"])
            ],
            semantic_type="ticket_priority",
        ),
        ParameterSchema(
            name="title",
            type="string",
            required=False,
            description="A new title. Only the ticket's OWNER may change it.",
            constraints=[
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars)
            ],
            semantic_type="Text",
        ),
        ParameterSchema(
            name="description",
            type="string",
            required=False,
            description="A new description. Only the ticket's OWNER may change it.",
            constraints=[
                ParameterConstraint(
                    kind="max_length", value=settings.workboard_description_max_chars
                )
            ],
            semantic_type="Text",
        ),
        ParameterSchema(
            name="start_at",
            type="string",
            required=False,
            description="A new start date, as the user's LOCAL date and time (ISO 8601).",
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="due_at",
            type="string",
            required=False,
            description="A new due date, as the user's LOCAL date and time (ISO 8601).",
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="assignee",
            type="string",
            required=False,
            description=(
                "Hand it over: 'me', 'lia', or the exact NAME of a connected "
                "user. A ticket somebody else holds cannot be given to LIA."
            ),
            constraints=[ParameterConstraint(kind="max_length", value=255)],
        ),
        ParameterSchema(
            name="follow",
            type="boolean",
            required=False,
            description="Whether the user wants to be told about this ticket in the chat.",
        ),
        ParameterSchema(
            name="run_now",
            type="boolean",
            required=False,
            description=(
                "Ask LIA to run this ticket at the next sweep instead of "
                "waiting for its start date. Only for a ticket LIA holds."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success", type="boolean", description="Whether exact confirmation was prepared"
        ),
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Native source update confirmation; no change saved yet",
        ),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=50, est_cost_usd=0.0001, est_latency_ms=120),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "move this ticket to another column",
        "mark a ticket as done",
        "change a ticket's priority or due date",
        "hand a ticket to somebody else",
        "ask LIA to run a ticket now",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="✏️", i18n_key="update_ticket", visible=True, category="tool"),
    tool_category="update",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


comment_ticket_catalogue_manifest = ToolManifest(
    name="comment_ticket_tool",
    mutation_policy="draft",
    initiative_eligible=False,
    agent="ticket_agent",
    description=(
        "Prepare mandatory human confirmation for an exact literal comment. Preparation posts nothing. "
        "The current source ticket and pending action are pinned. On an owner-held confirming ticket, "
        "the source classifies the complete comment: pure approval authorizes the stored action and returns "
        "the ticket to LIA; refusal closes it; amendment discards the old action and allows a fresh run. "
        "The source pending preview and consequences are shown. Changed ticket/pending action requires "
        "a new proposal. No network or model is called by commenting; subsequent LIA runs keep normal quotas/costs."
    ),
    parameters=[
        _TICKET_REFERENCE,
        ParameterSchema(
            name="body",
            type="string",
            required=True,
            description="The comment, in the user's own language.",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=settings.workboard_comment_max_chars),
            ],
            semantic_type="Text",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success", type="boolean", description="Whether exact confirmation was prepared"
        ),
        OutputFieldSchema(
            path="draft", type="object", description="Native comment confirmation; no write yet"
        ),
    ],
    cost=CostProfile(est_tokens_in=60, est_tokens_out=30, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "add a note to a ticket",
        "comment on a ticket of my board",
        "record where this ticket stands",
        "leave a message on a shared ticket",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="💬", i18n_key="comment_ticket", visible=True, category="tool"),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


list_tickets_catalogue_manifest = ToolManifest(
    name="list_tickets_tool",
    mutation_policy="read",
    context_key=CONTEXT_DOMAIN_TICKETS,
    agent="ticket_agent",
    description=(
        "Lists what is on the user's workboard, with the EXACT total beside "
        "the page. Filter by column, by who holds it, by priority, by what is "
        "overdue, or by a fragment of the title. Use for 'what is on my "
        "board', 'what is overdue', 'what LIA is working on', 'Marie's "
        "tickets'."
    ),
    parameters=[
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=f"Only this column: {_COLUMNS}.",
            constraints=[ParameterConstraint(kind="enum", value=_COLUMNS.split(", "))],
            semantic_type="ticket_status",
        ),
        ParameterSchema(
            name="assignee",
            type="string",
            required=False,
            description=(
                "Only what one side holds: 'me', 'lia', 'peer' (somebody "
                "else), or 'all' (default)."
            ),
            constraints=[ParameterConstraint(kind="enum", value=["me", "lia", "peer", "all"])],
        ),
        ParameterSchema(
            name="priority",
            type="string",
            required=False,
            description="Only this priority: low | medium | high | urgent.",
            constraints=[
                ParameterConstraint(kind="enum", value=["low", "medium", "high", "urgent"])
            ],
            semantic_type="ticket_priority",
        ),
        ParameterSchema(
            name="overdue",
            type="boolean",
            required=False,
            description="Only tickets past their due date and still open.",
        ),
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description="Only tickets whose title contains this fragment.",
            constraints=[
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars)
            ],
        ),
        ParameterSchema(
            name="limit",
            type="integer",
            required=False,
            description="How many tickets to return. The exact total is returned beside them.",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=100),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="tickets", type="array", description="The page of tickets"),
        *_ticket_outputs("tickets[]"),
        OutputFieldSchema(
            path="total",
            type="integer",
            description="EXACT number matching the filters, not the page length",
        ),
        OutputFieldSchema(
            path="counts", type="object", description="Exact count per column, every column present"
        ),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=200, est_cost_usd=0.0002, est_latency_ms=120),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "what is on my workboard",
        "which tickets are overdue",
        "what is LIA working on",
        "list the tickets in a column",
        "show the tickets a connected user holds",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="📋", i18n_key="list_tickets", visible=True, category="tool"),
    tool_category="search",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


get_ticket_catalogue_manifest = ToolManifest(
    name="get_ticket_tool",
    mutation_policy="read",
    context_key=CONTEXT_DOMAIN_TICKETS,
    agent="ticket_agent",
    description=(
        "Reads ONE ticket in full: its description, its steps, its comment "
        "thread, and what the last LIA run produced — its outcome, what it "
        "cost, and the error code when it failed. Use before acting on a "
        "ticket the user names, and to answer 'where does … stand'."
    ),
    parameters=[_TICKET_REFERENCE],
    outputs=[
        OutputFieldSchema(path="ticket", type="object", description="The ticket itself"),
        *_ticket_outputs("ticket"),
        OutputFieldSchema(
            path="ticket.description",
            type="string",
            nullable=True,
            description="Ticket brief",
            semantic_type="Text",
        ),
        OutputFieldSchema(path="children", type="array", description="Its steps, when it has any"),
        *_ticket_outputs("children[]"),
        OutputFieldSchema(path="comments", type="array", description="The thread, oldest first"),
        OutputFieldSchema(
            path="comments[].body",
            type="string",
            description="Comment content",
            semantic_type="Text",
        ),
        OutputFieldSchema(
            path="last_run", type="object", description="Outcome, cost and error of the last run"
        ),
        OutputFieldSchema(
            path="last_run.at",
            type="string",
            nullable=True,
            description="Last run instant (ISO 8601)",
            semantic_type="datetime",
        ),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=250, est_cost_usd=0.0002, est_latency_ms=120),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "read one ticket of my board in full",
        "where does this ticket stand",
        "what did LIA do on this ticket",
        "show the comments of a ticket",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="🔍", i18n_key="get_ticket", visible=True, category="tool"),
    tool_category="readonly",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


delete_ticket_catalogue_manifest = ToolManifest(
    name="delete_ticket_tool",
    mutation_policy="draft",
    initiative_eligible=False,
    agent="ticket_agent",
    description=(
        "Deletes a ticket from the workboard, with its steps, its comments "
        "and its history. Irreversible, so it returns a confirmation card and "
        "deletes nothing until the user accepts it. "
        "A ticket can be deleted from any column. Only its OWNER may delete "
        "it — somebody merely holding it cannot."
        " The exact subtree titles, counts and active runs are frozen; any change requires "
        "a new proposal. Native application and Workboard capabilities are rechecked before "
        "the write. Source deletion and acknowledged persistence are verified. Existing "
        "in-flight actions may continue; deleting a ticket does not cancel them."
    ),
    parameters=[_TICKET_REFERENCE],
    outputs=[
        OutputFieldSchema(
            path="success", type="boolean", description="Whether exact confirmation was prepared"
        ),
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Exact native subtree deletion confirmation; no removal yet",
        ),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=30, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        # Draft-based, like every destructive native tool: the tool RETURNS a
        # confirmation card and the confirmed replay performs the deletion.
        # `hitl_required` stays False — the draft IS the confirmation
        # (test_hitl_required_consistency doctrine).
        hitl_required=False,
    ),
    semantic_keywords=[
        "delete a ticket from my board",
        "remove this ticket entirely",
        "get rid of a ticket and its steps",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_ticket", visible=True, category="tool"),
    tool_category="delete",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
