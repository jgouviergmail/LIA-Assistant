"""Catalogue manifests for interactive pages (ADR-370).

A virtual agent, like ``document_generation_agent``: no LangGraph graph, one tool.
The domain of its own is what lets a switch remove the capability from every turn
(``CapabilitySpec.agents``), and what gives the analyzer one sentence telling a
thing to use from its source code.

The wording of the tool and of its parameters is read by the manifest AND by the
``@tool`` schema: the ReAct loop binds the schema, never the manifest.
"""

from typing import Final, Literal

from src.domains.agents.constants import AGENT_INTERACTIVE_PAGE
from src.domains.agents.registry.catalogue import (
    REASON_LOCAL_ARTEFACT,
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.interactive_pages.schemas import PageMode

#: The modes, in the model's words. A test holds it equal to ``PageMode``.
PageModeName = Literal["create", "revise", "show", "code"]

PAGE_TOOL_DESCRIPTION: Final = (
    "**Tool: generate_interactive_page** - Create a self-contained interactive web "
    "page and show it LIVE in the conversation, with its downloadable .html file.\n"
    "**Use for**: something the person wants to USE: a game, a quiz, a calculator, a "
    "timer, a simulation, an animation, a small tool or a web page, including when "
    "they say 'in HTML'.\n"
    "**NOT for**: a request to SEE, GET or explain source code ('give me the HTML "
    "code for X'): answer that directly, in a code block. NOT for documents "
    "(generate_document) nor images.\n"
    "**Output**: the page is displayed below the response. Never repeat its code."
)
PAGE_INSTRUCTIONS_DESCRIPTION: Final = (
    "What the page must do and look like, or the change to make to it, in the "
    "person's own terms. Required by the create and revise modes."
)
PAGE_MODE_DESCRIPTION: Final = (
    "create: a new page. revise: change the latest page or HTML code of this "
    "conversation. show: display that page or code as it is, nothing rewritten. "
    "code: show the exact source of that page."
)
PAGE_SOURCE_DATA_DESCRIPTION: Final = (
    "Facts the page must use, typically the result of earlier steps "
    "(e.g. $steps.step_1.web_searches). With show or code: HTML code the person "
    "pasted, shown as it is."
)
PAGE_FILENAME_DESCRIPTION: Final = "Filename requested by the user, without extension."

# ============================================================================
# AGENT MANIFEST
# ============================================================================

interactive_page_agent_manifest = AgentManifest(
    name=AGENT_INTERACTIVE_PAGE,
    description="Agent for interactive web pages shown live in the conversation.",
    tools=["generate_interactive_page"],
    max_parallel_runs=1,
    default_timeout_ms=180000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
)

# ============================================================================
# GENERATE INTERACTIVE PAGE TOOL
# ============================================================================

generate_interactive_page_catalogue_manifest = ToolManifest(
    name="generate_interactive_page",
    mutation_policy="artefact",
    mutation_policy_reason=REASON_LOCAL_ARTEFACT,
    agent=AGENT_INTERACTIVE_PAGE,
    description=PAGE_TOOL_DESCRIPTION,
    semantic_keywords=[
        "make me a game I can play",
        "create an interactive web page",
        "build a calculator or a quiz I can use",
        "create a small web app",
        "show this page directly in the conversation",
        "change the page you made",
    ],
    parameters=[
        ParameterSchema(
            name="instructions",
            type="string",
            required=False,
            description=PAGE_INSTRUCTIONS_DESCRIPTION,
            semantic_type="Text",
        ),
        ParameterSchema(
            name="mode",
            type="string",
            required=False,
            description=PAGE_MODE_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=[mode.value for mode in PageMode])],
        ),
        ParameterSchema(
            name="source_data",
            type="string",
            required=False,
            description=PAGE_SOURCE_DATA_DESCRIPTION,
            semantic_type="Text",
        ),
        ParameterSchema(
            name="filename",
            type="string",
            required=False,
            description=PAGE_FILENAME_DESCRIPTION,
            semantic_type="file_name",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation that the page is displayed",
            semantic_type="Text",
        ),
    ],
    # Measured 2026-11-04 on the production slot: 0.0106 EUR per 1,000 output
    # tokens, 4,000 to 8,000 tokens for a page; the prompt is about 900 tokens.
    cost=CostProfile(
        est_tokens_in=1500,
        est_tokens_out=6000,
        est_cost_usd=0.08,
        est_latency_ms=60000,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    tool_category="create",
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="\U0001f3ae",  # video game
        i18n_key="generate_interactive_page",
        visible=True,
        category="tool",
    ),
)
