"""What a model is told about the categories of the workboard (ADR-276).

A category is a lane of the board: a name its owner files tickets under. The
assistant does three things with one — it READS a ticket's category, it NARROWS
the board to one, and it FILES a ticket under one — and always names it the way
the person does, by its name.

It administers none. Creating, renaming, reordering and deleting a category
are done by the user on the board itself (owner arbitration, 2026-11-11): no
tool exists for it, and each manifest that touches a category says so, because
a model told nothing invents a capability and then reports a failure.

Kept in its own module, beside ``creation_manifest``: the three ticket
manifests that take a category share ONE parameter here, so the bound a name
is held to is published once and cannot drift between them (ADR-184).
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.core.i18n_workboard_categories import workboard_category_place
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: Said wherever a model could be tempted to create a category by naming one.
MANAGED_ON_THE_BOARD = (
    "Categories are created, renamed, reordered and deleted by the user on the "
    "board itself, never by a tool"
)

#: WHERE on the board, with its two names left open: they are the PERSON's,
#: the words their own screen shows, so the answer that quotes them sends
#: nobody to a « Categories » button a German board labels « Kategorien ». The
#: sentence around them stays technical English: a model alone reads it
#: (ADR-256).
_MANAGED_FROM = (
    "the '{button}' button of the page named '{page}' in the application's "
    "menu, both written as the user's screen shows them: the user creates, "
    "renames, reorders and deletes categories there, and no tool does it"
)


def categories_managed_from(language: str) -> str:
    """Where the user administers categories, named as THEIR screen names it.

    What the reader's RESULT says. An answer can then tell the user where to go
    whichever mode ran the turn: the model that writes the pipeline's answer
    reads a tool's data, never its description. The page is NAMED as the
    application's menu names it: measured on a real turn (2026-11-11), « the
    workboard page » was rendered « the dashboard page ».

    Args:
        language: The language the turn runs in (any spelling of a code).

    Returns:
        The sentence, in technical English around the person's two labels.
    """
    place = workboard_category_place(language)
    return _MANAGED_FROM.format(button=place.button, page=place.page)


def category_name_parameter(description: str) -> ParameterSchema:
    """The ``category`` parameter of a ticket tool: a category's NAME.

    The bound is the one a category's name is stored under
    (``workboard_category_name_max_chars``): a longer name can match no
    category, and the producer must be able to read that.

    Args:
        description: What naming a category does for THIS tool.

    Returns:
        The published parameter.
    """
    return ParameterSchema(
        name="category",
        type="string",
        required=False,
        description=description,
        constraints=[
            ParameterConstraint(kind="min_length", value=1),
            ParameterConstraint(
                kind="max_length", value=settings.workboard_category_name_max_chars
            ),
        ],
    )


def category_output(prefix: str) -> OutputFieldSchema:
    """The ``category`` leaf of a ticket a reader returns.

    Args:
        prefix: Where the ticket sits in the payload.

    Returns:
        The published output field.
    """
    return OutputFieldSchema(
        path=f"{prefix}.category",
        type="string",
        nullable=True,
        description=(
            "Name of the category the ticket is filed under, as its owner wrote it; "
            "null when it is filed under no category of the user's board"
        ),
        semantic_type="Text",
    )


list_ticket_categories_catalogue_manifest = ToolManifest(
    name="list_ticket_categories_tool",
    mutation_policy="read",
    agent="ticket_agent",
    description=(
        "Lists the categories the user's workboard is split into — the lanes of "
        "the board — each with the EXACT number of tickets filed under it, and "
        "how many tickets are filed under no category. Use for 'what categories "
        "do I have' and 'how many tickets in each category'. ALSO the tool to "
        "call when the user asks to create, rename, reorder or delete a "
        f"category. {MANAGED_ON_THE_BOARD}: this result says where, beside the "
        "categories that already exist. 'mine' is false for the category of a "
        "ticket the user holds for somebody else: it can be read and filtered "
        "on, never filed under. Read-only."
    ),
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="managed_from",
            type="string",
            description=(
                "Where the user administers categories, the page and the button "
                "named as the user's own screen shows them, in the turn's "
                "language: what to tell them when they ask to create, rename, "
                "reorder or delete one"
            ),
            semantic_type="Text",
        ),
        OutputFieldSchema(
            path="categories", type="array", description="Every category on the user's board"
        ),
        OutputFieldSchema(
            path="categories[].name",
            type="string",
            description="The category's name, as its owner wrote it",
            semantic_type="Text",
        ),
        OutputFieldSchema(
            path="categories[].mine",
            type="boolean",
            description="Whether it is the user's own — only those can take one of their tickets",
        ),
        OutputFieldSchema(
            path="categories[].tickets",
            type="integer",
            description="EXACT number of tickets filed under it, over the whole board",
        ),
        OutputFieldSchema(
            path="unfiled_tickets",
            type="integer",
            nullable=True,
            description=(
                "EXACT number of tickets filed under no category; absent when the "
                "board has no category at all"
            ),
        ),
    ],
    cost=CostProfile(est_tokens_in=20, est_tokens_out=120, est_cost_usd=0.0001, est_latency_ms=100),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "what categories does my workboard have",
        "how many tickets are in each category",
        "list the lanes of my board",
        "how many tickets are not categorized yet",
        # A request no tool serves still has to land somewhere that can answer
        # it: here, where the result says where it is done.
        "create a category on my workboard",
        "rename, reorder or delete a category of my board",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="🏷️", i18n_key="list_ticket_categories", visible=True, category="tool"
    ),
    tool_category="search",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
