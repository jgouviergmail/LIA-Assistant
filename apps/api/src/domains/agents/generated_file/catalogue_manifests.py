"""Catalogue manifests for the generated-files lookup (ADR-318).

The files LIA produced for the person — images, documents, browser screenshots,
and the images a connection shared (ADR-316) — live in their gallery for a
bounded time (ADR-279). The lookup finds them again and shows them as the
chat's own cards. Internal, no OAuth, read-only, unflagged: the gallery ships on
every deployment. The families are the gallery's generated origins, pinned to
them by a test; the bound is the setting the tool enforces (ADR-184).
"""

from datetime import UTC, datetime
from typing import Final, Literal, get_args

from src.core.config import settings
from src.core.date_contract import ISO_MOMENT_DESCRIPTION
from src.domains.agents.constants import AGENT_GENERATED_FILE
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
from src.domains.attachments.models import AttachmentOrigin

#: A family of generated files, in the model's words.
GeneratedFileFamily = Literal["image", "document", "screenshot"]

#: Each family and the gallery origin it reads. Together they are exactly the
#: gallery's GENERATED origins (``attachments/origin``) — a test holds it.
GENERATED_FILE_ORIGINS: Final[dict[str, AttachmentOrigin]] = {
    "image": AttachmentOrigin.GENERATED_IMAGE,
    "document": AttachmentOrigin.GENERATED_DOCUMENT,
    "screenshot": AttachmentOrigin.BROWSER_SCREENSHOT,
}
GENERATED_FILE_FAMILIES: Final[tuple[str, ...]] = get_args(GeneratedFileFamily)

#: The wording of the lookup's parameters, read by the manifest AND the schema.
GENERATED_FILES_QUERY_DESCRIPTION = (
    "Words of the file's title or name (the request that produced it), e.g. 'invoice' or "
    "'cat'. Omitted: every file."
)
GENERATED_FILES_FAMILY_DESCRIPTION = (
    "image (generated or shared images), document (generated files: PDF, Word, Excel, "
    "PowerPoint, CSV, text), screenshot (browser screenshots). Omitted: every family."
)
GENERATED_FILES_START_DESCRIPTION = (
    f"Produced on or after this day (or instant). {ISO_MOMENT_DESCRIPTION}"
)
GENERATED_FILES_END_DESCRIPTION = (
    f"Produced on or before this day (an instant is exclusive). {ISO_MOMENT_DESCRIPTION}"
)
GENERATED_FILES_MAX_RESULTS_DESCRIPTION = (
    f"Most files to return and show, 1 to {settings.generated_files_search_max_results} "
    "(default: the maximum). The total is always exact."
)

# =============================================================================
# Agent Manifest: generated_file_agent
# =============================================================================

GENERATED_FILE_AGENT_MANIFEST = AgentManifest(
    name=AGENT_GENERATED_FILE,
    description=(
        "Agent for the files LIA produced for the user — generated images and "
        "documents, browser screenshots, images a connection shared — found again "
        "and shown in the chat. Read-only."
    ),
    tools=["find_generated_files_tool"],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="🖼️", i18n_key="generated_file_agent", visible=True, category="agent"
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: find_generated_files_tool
# =============================================================================

find_generated_files_catalogue_manifest = ToolManifest(
    name="find_generated_files_tool",
    agent=AGENT_GENERATED_FILE,
    mutation_policy="read",
    # Reads the person's own gallery (explicit: the name has no get_/search_ prefix).
    tool_category="search",
    description=(
        "**Tool: find_generated_files_tool** - Find again the files LIA PRODUCED for the "
        "user: generated images and documents, browser screenshots, images a connection "
        "shared. The files found are SHOWN to the user as cards below the answer — never "
        "add a link or an image yourself. LIA keeps them "
        f"{settings.attachments_ttl_hours} hours; an older file is gone, say so. NOT the "
        "user's Drive files (file), NOT creating a new image or document (image_generation, "
        "document_generation)."
    ),
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description=GENERATED_FILES_QUERY_DESCRIPTION,
        ),
        ParameterSchema(
            name="family",
            type="string",
            required=False,
            description=GENERATED_FILES_FAMILY_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(GENERATED_FILE_FAMILIES))],
        ),
        ParameterSchema(
            name="start_date",
            type="string",
            required=False,
            description=GENERATED_FILES_START_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="end_date",
            type="string",
            required=False,
            description=GENERATED_FILES_END_DESCRIPTION,
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=GENERATED_FILES_MAX_RESULTS_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(
                    kind="maximum", value=settings.generated_files_search_max_results
                ),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="files", type="array", description="The files, newest first"),
        OutputFieldSchema(path="files[].title", type="string", description="What the file is"),
        OutputFieldSchema(path="files[].family", type="string", description="Its family"),
        OutputFieldSchema(
            path="files[].created", type="string", description="Local ISO time produced"
        ),
        OutputFieldSchema(
            path="files[].expires", type="string", description="Local ISO time it is deleted"
        ),
        OutputFieldSchema(
            path="files[].shared_by",
            type="string",
            nullable=True,
            description="Who shared it, for an image a connection sent",
        ),
        OutputFieldSchema(path="total", type="integer", description="EXACT count of matches"),
    ],
    cost=CostProfile(est_tokens_in=40, est_tokens_out=300, est_cost_usd=0.0, est_latency_ms=100),
    permissions=PermissionProfile(
        required_scopes=[], data_classification="CONFIDENTIAL", hitl_required=False
    ),
    semantic_keywords=[
        "show me again the image you generated",
        "find the document you created for me yesterday",
        "where is the report you made",
        "the screenshot of the web page you visited",
        "the picture my contact shared with me",
    ],
    reference_examples=["files[0].title", "total"],
    display=DisplayMetadata(
        emoji="🖼️", i18n_key="find_generated_files", visible=True, category="tool"
    ),
    # It SHOWS what it finds: a proactive lookup would put cards nobody asked for.
    initiative_eligible=False,
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "GENERATED_FILES_END_DESCRIPTION",
    "GENERATED_FILES_FAMILY_DESCRIPTION",
    "GENERATED_FILES_MAX_RESULTS_DESCRIPTION",
    "GENERATED_FILES_QUERY_DESCRIPTION",
    "GENERATED_FILES_START_DESCRIPTION",
    "GENERATED_FILE_AGENT_MANIFEST",
    "GENERATED_FILE_FAMILIES",
    "GENERATED_FILE_ORIGINS",
    "GeneratedFileFamily",
    "find_generated_files_catalogue_manifest",
]
