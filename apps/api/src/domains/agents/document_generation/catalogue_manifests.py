"""Catalogue manifests for the Document Generation tool (ADR-226).

Defines the AgentManifest (virtual agent — no LangGraph graph, like
image_generation_agent) and the ToolManifest for generate_document, used by
the SmartCatalogueService for domain detection and tool selection.
"""

from src.domains.agents.constants import AGENT_DOCUMENT_GENERATION
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
from src.domains.document_generation.schemas import DocumentType

# ============================================================================
# AGENT MANIFEST
# ============================================================================

document_agent_manifest = AgentManifest(
    name=AGENT_DOCUMENT_GENERATION,
    description=("Agent for AI document generation (csv, xlsx, docx, pptx, pdf, md, txt)."),
    tools=["generate_document"],
    max_parallel_runs=1,
    default_timeout_ms=180000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
)

# ============================================================================
# GENERATE DOCUMENT TOOL
# ============================================================================
_desc = (
    "**Tool: generate_document** - Create a downloadable document from "
    "instructions and optional source data.\n"
    "The document is displayed as a downloadable card below the assistant "
    "response and expires automatically.\n"
    "**Use for**: 'Export this as CSV/Excel', 'Write a report about... as "
    "PDF/Word', 'Make a presentation about...', 'Formalize these results "
    "into a file'.\n"
    "**Chaining**: pass research results from earlier steps via source_data "
    "(e.g. $steps.step_1.web_searches) so the document is grounded in them.\n"
    "**Output**: downloadable document card below the response."
)

# The exact closed set the tool validates against — derived from the enum, so
# manifest and validator can never drift (ADR-184: an enforced constraint is
# published to whoever produces the value).
_DOC_TYPE_VALUES: list[str] = [t.value for t in DocumentType]

generate_document_catalogue_manifest = ToolManifest(
    name="generate_document",
    mutation_policy="artefact",
    mutation_policy_reason=REASON_LOCAL_ARTEFACT,
    agent=AGENT_DOCUMENT_GENERATION,
    description=_desc,
    semantic_keywords=[
        "create a csv or excel spreadsheet file",
        "export results as a document file",
        "write a report as pdf or word document",
        "make a powerpoint presentation file",
        "formalize data into a structured file",
        "generate a downloadable file",
    ],
    parameters=[
        ParameterSchema(
            name="instructions",
            type="string",
            required=True,
            description=(
                "What the document must contain: subject, structure, level of " "detail, audience."
            ),
        ),
        ParameterSchema(
            name="doc_type",
            type="string",
            required=True,
            description="Target format.",
            constraints=[ParameterConstraint(kind="enum", value=_DOC_TYPE_VALUES)],
        ),
        ParameterSchema(
            name="source_data",
            type="string",
            required=False,
            description=(
                "Raw material to ground the document in — typically the result "
                "of earlier research steps (e.g. $steps.step_1.web_searches)."
            ),
        ),
        ParameterSchema(
            name="filename",
            type="string",
            required=False,
            description="Filename requested by the user, without extension.",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation with the generated filename",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=2000,
        est_tokens_out=8000,
        est_cost_usd=0.05,
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
        emoji="\U0001f4c4",  # page facing up
        i18n_key="generate_document",
        visible=True,
        category="tool",
    ),
)
