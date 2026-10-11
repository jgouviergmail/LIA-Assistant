"""Existing ticket creation publishes its full source schema and mandatory draft contract."""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.workboard.constants import STATUS_ORDER

_COLUMNS = ", ".join(STATUS_ORDER)

create_ticket_catalogue_manifest = ToolManifest(
    name="create_ticket_tool",
    mutation_policy="draft",
    agent="ticket_agent",
    description=(
        "Prepares mandatory exact human confirmation to create a ticket on the user's workboard. No creation before confirmation. Use the full request schema, or legacy fields exclusively. Assigning to LIA permits later paid execution under normal quotas; never claim it already ran. Changed parent, assignee, account or cap requires re-confirmation. Unknown completion is not automatically retried. Use when they want to keep "
        "track of something to do, note an idea, or ask LIA to take a task on "
        "('put this on my board', 'create a ticket for…', 'note that I have "
        "to…', 'take care of…'). Set assignee='lia' when they ask LIA to DO it "
        "— LIA then runs it on its own and comments the result on the ticket. "
        "To break a complex task down, create the parent first and call this "
        "again with parent_ticket for each step. NOT for a provider to-do "
        "(use task), a timed notification (use reminder) or a recurring job "
        "(use automation)."
    ),
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=False,
            description="Full current Workboard UI creation configuration; exclusive with legacy fields",
            schema=WorkboardCreateInput.model_json_schema(),
        ),
        ParameterSchema(
            name="title",
            type="string",
            required=False,
            description="What the ticket is, in the user's own words.",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=settings.workboard_title_max_chars),
            ],
            semantic_type="Text",
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
            semantic_type="Text",
        ),
        ParameterSchema(
            name="priority",
            type="string",
            required=False,
            description="low | medium | high | urgent. Defaults to medium.",
            constraints=[
                ParameterConstraint(kind="enum", value=["low", "medium", "high", "urgent"])
            ],
            semantic_type="ticket_priority",
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
            semantic_type="ticket_status",
        ),
        ParameterSchema(
            name="start_at",
            type="string",
            required=False,
            description=(
                "When work may start, as the user's LOCAL date and time "
                "(ISO 8601). A ticket assigned to LIA is not run before it."
            ),
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="due_at",
            type="string",
            required=False,
            description="When it is due, as the user's LOCAL date and time (ISO 8601).",
            semantic_type="datetime",
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
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact creation confirmation"
        )
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
    initiative_eligible=False,
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
