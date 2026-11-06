"""Catalogue manifest of the file-sharing tool (ADR-369, lot 6, owner decision D2).

Beside ``catalogue_manifests.py``. Sharing tells a third party, so the tool drafts and the card
is the confirmation. What it publishes is what it enforces (ADR-184): the roles are written ONCE,
in the words the planner's manifest and the ReAct tool schema both read (ADR-310).
"""

from typing import Final

from src.core.constants import GOOGLE_DRIVE_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: What a person may be given on a file; nobody is made its owner.
FILE_SHARE_ROLES: Final = ("reader", "writer")

SHARE_FILE_ID_DESCRIPTION: Final = "The file or folder's id (from get_files_tool or CONTEXT)."
SHARE_EMAIL_DESCRIPTION: Final = (
    "The address of the person it is shared with: the drive tells them."
)
SHARE_ROLE_DESCRIPTION: Final = "reader (they read it) or writer (they may change it)."

share_file_catalogue_manifest = ToolManifest(
    name="share_file_tool",
    agent="file_agent",
    description=(
        "**Tool: share_file_tool** - Share a file or a folder with someone (Google Drive or "
        "OneDrive). The drive tells them, so the person is asked to confirm first.\n"
        "- 'share this file with ana@example.org', 'let Bob edit the report'\n"
        "- The id comes from get_files_tool or CONTEXT, the address from the person or the "
        "contacts\n"
        "**RETURNS**: `file_id`."
    ),
    tool_category="update",
    mutation_policy="draft",
    semantic_keywords=[
        "share this file with someone",
        "give access to this document",
        "let my colleague edit this file",
        "share the folder with",
    ],
    parameters=[
        ParameterSchema(
            name="file_id",
            type="string",
            required=True,
            description=SHARE_FILE_ID_DESCRIPTION,
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="email",
            type="string",
            required=True,
            description=SHARE_EMAIL_DESCRIPTION,
            semantic_type="email_address",
        ),
        ParameterSchema(
            name="role",
            type="string",
            required=False,
            description=SHARE_ROLE_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(FILE_SHARE_ROLES))],
        ),
    ],
    outputs=[OutputFieldSchema(path="file_id", type="string", description="The item shared")],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=50, est_cost_usd=0.0, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    reference_examples=["file_id"],
    display=DisplayMetadata(emoji="🔗", i18n_key="share_file", visible=True, category="tool"),
    version="1.0.0",
    maintainer="Team Agents",
)

__all__ = [
    "FILE_SHARE_ROLES",
    "SHARE_EMAIL_DESCRIPTION",
    "SHARE_FILE_ID_DESCRIPTION",
    "SHARE_ROLE_DESCRIPTION",
    "share_file_catalogue_manifest",
]
