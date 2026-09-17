"""
Catalogue manifest of ``get_email_attachment_tool`` — one attachment, read.

Beside ``get_emails_manifest.py`` because ``catalogue_manifests.py`` is at
its size cap. What this manifest publishes is what the tool enforces
(ADR-184): the size bound, the page bound of the vision reading, the parts.
"""

from src.core.config import settings
from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_desc = (
    "**Tool: get_email_attachment_tool** - Read ONE attachment of a message.\n"
    "\n"
    "**USAGE**:\n"
    "- After `get_emails` listed a message's attachments (`attachments[]`): pass `message_id` "
    "and the listed `attachment_id` (preferred), or `filename` when it is unique in the message\n"
    "- `question`: what to look for (guides the reading of an image or a scanned page)\n"
    "- A long text is served in PARTS: read `parts`, pass `part=2` for the next one\n"
    "\n"
    "**WHAT IT READS**:\n"
    "- documents (PDF, Word, Excel, PowerPoint, OpenDocument, CSV, text, HTML, EPUB, JSON, XML): "
    "the text as written\n"
    "- images and PDFs without a text layer (scans, photos of a receipt): a reading by a vision "
    f"model of the first {settings.email_attachment_vision_max_pages} pages, one model call\n"
    f"- bigger than {settings.email_attachment_max_mb} MB, archives, audio, video: refused by name\n"
    "\n"
    "**RETURNS**: `text` (the reading, external content), `route` (text | vision), `part`/`parts`, "
    "`mime_type`, `size`. A refusal names its reason (not found, ambiguous name with the candidate "
    "handles, unsupported, too large, quota, truncated)."
)

get_email_attachment_catalogue_manifest = ToolManifest(
    name="get_email_attachment_tool",
    agent="email_agent",
    description=_desc,
    semantic_keywords=[
        "read the attachment of an email",
        "open the PDF attached to a message",
        "what does the attached invoice say",
        "read the document attached to this mail",
        "content of the attachment in the email",
        "look at the picture attached to the message",
        "extract text from the attached file",
        "summarize the attached report of the email",
        "check the figures in the attached spreadsheet",
        "read the scanned document attached",
    ],
    parameters=[
        ParameterSchema(
            name="message_id",
            type="string",
            required=True,
            description="The message id (from $steps or CONTEXT).",
        ),
        ParameterSchema(
            name="attachment_id",
            type="string",
            required=False,
            description="The listed attachment handle (attachments[].attachment_id); wins over filename.",
        ),
        ParameterSchema(
            name="filename",
            type="string",
            required=False,
            description="The attachment's file name, when its handle is unknown (must be unique).",
        ),
        ParameterSchema(
            name="question",
            type="string",
            required=False,
            description="What to look for in the attachment (optional).",
        ),
        ParameterSchema(
            name="part",
            type="integer",
            required=False,
            description="1-based part of a long text (def: 1; see parts)",
            constraints=[ParameterConstraint(kind="minimum", value=1)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="filename", type="string", description="The file name as sent"),
        OutputFieldSchema(
            path="mime_type", type="string", description="MIME type read from the bytes"
        ),
        OutputFieldSchema(path="route", type="string", description="text | vision"),
        OutputFieldSchema(
            path="text", type="string", description="The reading, one part (external content)"
        ),
        OutputFieldSchema(path="part", type="integer", description="The part served"),
        OutputFieldSchema(path="parts", type="integer", description="Number of parts"),
        OutputFieldSchema(
            path="pages_read", type="integer", description="Pages the vision slot saw"
        ),
        OutputFieldSchema(
            path="pages_total",
            type="integer",
            description="Pages the attachment holds (more than pages_read means a cut)",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=200, est_tokens_out=1500, est_cost_usd=0.004, est_latency_ms=2500
    ),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    mutation_policy="read",
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=["filename", "text"],
    reference_examples=["text", "parts", "filename"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📎", i18n_key="get_email_attachment", visible=True, category="tool"
    ),
)


__all__ = ["get_email_attachment_catalogue_manifest"]
