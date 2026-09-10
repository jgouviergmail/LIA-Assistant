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

from datetime import UTC, datetime

from src.core.config import settings
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


create_ticket_catalogue_manifest = ToolManifest(
    name="create_ticket_tool",
    mutation_policy="reversible",
    mutation_policy_reason=(
        "A ticket is a note on the person's own board: it acts on nothing outside it, and deleting it is one click away."
    ),
    agent="ticket_agent",
    description=(
        "Creates a ticket on the user's workboard. Use when they want to keep "
        "track of something to do, note an idea, or ask LIA to take a task on "
        "('mets ça sur mon tableau', 'crée un ticket pour…', 'note que je dois "
        "…', 'occupe-toi de…'). Set assignee='lia' when they ask LIA to DO it "
        "— LIA then runs it on its own and comments the result on the ticket. "
        "To break a complex task down, create the parent first and call this "
        "again with parent_ticket for each step. NOT for a provider to-do "
        "(use task), a timed notification (use reminder) or a recurring job "
        "(use automation)."
    ),
    parameters=[
        ParameterSchema(
            name="title",
            type="string",
            required=True,
            description="What the ticket is, in the user's own words.",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars),
            ],
        ),
        ParameterSchema(
            name="description",
            type="string",
            required=False,
            description=(
                "What the ticket is about, in the user's own words. When "
                "assignee='lia' this IS the brief LIA will run, so keep "
                "everything it needs — and nothing it should not do."
            ),
            constraints=[
                ParameterConstraint(
                    kind="max_length", value=settings.workboard_description_max_chars
                )
            ],
        ),
        ParameterSchema(
            name="priority",
            type="string",
            required=False,
            description="low | medium | high | urgent. Defaults to medium.",
            constraints=[
                ParameterConstraint(kind="enum", value=["low", "medium", "high", "urgent"])
            ],
        ),
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=(
                f"The column to create it in: {_COLUMNS}. Defaults to todo. "
                "Use idea for something merely noted — a ticket in idea is "
                "never run."
            ),
            constraints=[ParameterConstraint(kind="enum", value=_COLUMNS.split(", "))],
        ),
        ParameterSchema(
            name="start_at",
            type="string",
            required=False,
            description=(
                "When work may start, as the user's LOCAL date and time "
                "(ISO 8601). A ticket assigned to LIA is not run before it."
            ),
        ),
        ParameterSchema(
            name="due_at",
            type="string",
            required=False,
            description="When it is due, as the user's LOCAL date and time (ISO 8601).",
        ),
        ParameterSchema(
            name="assignee",
            type="string",
            required=False,
            description=(
                "Who holds it: 'me' (the user, default), 'lia' (LIA runs it "
                "alone and comments the result), or the exact NAME of a "
                "connected user to hand it to."
            ),
            constraints=[
                ParameterConstraint(kind="max_length", value=255),
            ],
        ),
        ParameterSchema(
            name="parent_ticket",
            type="string",
            required=False,
            description=(
                "The ticket this one is a step of, by id or exact title. ONE "
                "level only: a step never has steps of its own."
            ),
            constraints=[
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars)
            ],
        ),
        ParameterSchema(
            name="follow",
            type="boolean",
            required=False,
            description=(
                "Whether to be told in the chat about what happens to this "
                "ticket. Off by default — a board that talks about every "
                "ticket teaches the user to ignore it."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Whether it was created"),
        OutputFieldSchema(path="ticket", type="object", description="The new ticket"),
        OutputFieldSchema(path="ticket.id", type="string", description="The new ticket's id"),
        OutputFieldSchema(path="ticket.title", type="string", description="Its title"),
        OutputFieldSchema(path="ticket.status", type="string", description="Its column"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=60, est_cost_usd=0.0001, est_latency_ms=120),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "add a ticket to my board",
        "put this on my workboard",
        "note this down as something to do",
        "ask LIA to take care of this task",
        "break this task into steps on the board",
    ],
    reference_examples=[],
    display=DisplayMetadata(emoji="🗂️", i18n_key="create_ticket", visible=True, category="tool"),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


update_ticket_catalogue_manifest = ToolManifest(
    name="update_ticket_tool",
    mutation_policy="reversible",
    mutation_policy_reason=(
        "Every field it touches is on the person's own board and can be set back, and the ticket's history records who changed what."
    ),
    agent="ticket_agent",
    description=(
        "Changes a ticket on the workboard: its column, priority, dates, "
        "title, description, who holds it, or whether the user follows it. "
        "Use for 'passe ce ticket en cours', 'termine…', 'repousse… à jeudi', "
        "'donne ce ticket à Marie', 'confie ça à LIA'. Set run_now=true to "
        "ask LIA to run a ticket it holds right away instead of waiting for "
        "the sweep. Only the fields given are changed."
    ),
    parameters=[
        _TICKET_REFERENCE,
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=f"Move it to this column: {_COLUMNS}.",
            constraints=[ParameterConstraint(kind="enum", value=_COLUMNS.split(", "))],
        ),
        ParameterSchema(
            name="priority",
            type="string",
            required=False,
            description="low | medium | high | urgent.",
            constraints=[
                ParameterConstraint(kind="enum", value=["low", "medium", "high", "urgent"])
            ],
        ),
        ParameterSchema(
            name="title",
            type="string",
            required=False,
            description="A new title. Only the ticket's OWNER may change it.",
            constraints=[
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars)
            ],
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
        ),
        ParameterSchema(
            name="start_at",
            type="string",
            required=False,
            description="A new start date, as the user's LOCAL date and time (ISO 8601).",
        ),
        ParameterSchema(
            name="due_at",
            type="string",
            required=False,
            description="A new due date, as the user's LOCAL date and time (ISO 8601).",
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
        OutputFieldSchema(path="success", type="boolean", description="Whether it was changed"),
        OutputFieldSchema(path="ticket", type="object", description="The ticket as it now stands"),
        OutputFieldSchema(path="ticket.id", type="string", description="The ticket's id"),
        OutputFieldSchema(path="ticket.status", type="string", description="Its column now"),
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
    mutation_policy="reversible",
    mutation_policy_reason=(
        "A comment is text on the person's own board; it leaves nothing outside LIA and the thread shows who wrote it."
    ),
    agent="ticket_agent",
    description=(
        "Adds a comment to a ticket — plain text, kept on the ticket's thread "
        "where both sides read it. Use when the user wants to record where "
        "something stands, or say something to whoever else holds the ticket."
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
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Whether it was added"),
        OutputFieldSchema(path="comment", type="object", description="The new comment"),
        OutputFieldSchema(path="comment.id", type="string", description="The comment's id"),
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
        "overdue, or by a fragment of the title. Use for 'qu'est-ce qu'il y a "
        "sur mon tableau', 'qu'est-ce qui est en retard', 'ce que LIA a en "
        "cours', 'les tickets de Marie'."
    ),
    parameters=[
        ParameterSchema(
            name="status",
            type="string",
            required=False,
            description=f"Only this column: {_COLUMNS}.",
            constraints=[ParameterConstraint(kind="enum", value=_COLUMNS.split(", "))],
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
        "ticket the user names, and to answer 'où en est…'."
    ),
    parameters=[_TICKET_REFERENCE],
    outputs=[
        OutputFieldSchema(path="ticket", type="object", description="The ticket itself"),
        OutputFieldSchema(path="children", type="array", description="Its steps, when it has any"),
        OutputFieldSchema(path="comments", type="array", description="The thread, oldest first"),
        OutputFieldSchema(
            path="last_run", type="object", description="Outcome, cost and error of the last run"
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
    agent="ticket_agent",
    description=(
        "Deletes a ticket from the workboard, with its steps, its comments "
        "and its history. Irreversible, so it returns a confirmation card and "
        "deletes nothing until the user accepts it. "
        "A ticket can be deleted from any column. Only its OWNER may delete "
        "it — somebody merely holding it cannot."
    ),
    parameters=[_TICKET_REFERENCE],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Whether it was deleted"),
        OutputFieldSchema(
            path="deleted", type="integer", description="Rows removed, the steps included"
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
