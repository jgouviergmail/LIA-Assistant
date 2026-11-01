"""Catalogue manifest of the read-state tool (ADR-369, owner decision D2).

Beside ``catalogue_manifests.py`` because that module is at its size cap (the
``attachment_manifest.py`` precedent). What it publishes is what the tool
enforces (ADR-184): the bound on one call is written ONCE, in the words both the
planner's manifest and the ReAct tool schema read (ADR-310).
"""

from src.core.constants import EMAIL_READ_STATE_MAX_MESSAGES, GOOGLE_GMAIL_SCOPES
from src.domains.agents.registry.catalogue import (
    REASON_UNDONE_BY_ONE_CALL,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: The message selection's wording, read by the manifest AND the tool's schema.
READ_STATE_IDS_DESCRIPTION = (
    "The messages' ids (from get_emails_tool or CONTEXT), at most "
    f"{EMAIL_READ_STATE_MAX_MESSAGES} per call: `more_remaining` says whether some were left."
)
#: The state's wording, read by both readers too.
READ_STATE_READ_DESCRIPTION = "True marks them read, false marks them unread."

set_email_read_state_catalogue_manifest = ToolManifest(
    name="set_email_read_state_tool",
    agent="email_agent",
    description=(
        "**Tool: set_email_read_state_tool** - Mark e-mails of the person's mailbox as READ or "
        "UNREAD (Gmail, Outlook or iCloud). Asks no confirmation.\n"
        "- 'mark these as read', 'mark the email from Paul as unread'\n"
        "- The ids come from get_emails_tool or CONTEXT; a search is never done here\n"
        "**RETURNS**: `updated` the ids changed, `failed` each one not changed and why "
        "(not_found when it left the mailbox since it was listed), `more_remaining`."
    ),
    # A state change on existing messages: a mutation (no naming convention says so).
    tool_category="update",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    semantic_keywords=[
        "mark this email as read",
        "mark these messages as unread",
        "mark the email from Paul as unread",
        "mark all these emails read",
        "set the message back to unread",
    ],
    parameters=[
        ParameterSchema(
            name="message_ids",
            type="array",
            required=True,
            description=READ_STATE_IDS_DESCRIPTION,
            semantic_type="message_id",
        ),
        ParameterSchema(
            name="read",
            type="boolean",
            required=True,
            description=READ_STATE_READ_DESCRIPTION,
        ),
    ],
    outputs=[
        OutputFieldSchema(path="updated", type="array", description="The ids changed"),
        OutputFieldSchema(path="failed", type="array", description="Ids not changed, and why"),
        OutputFieldSchema(path="read", type="boolean", description="The state set"),
        OutputFieldSchema(
            path="more_remaining", type="boolean", description="Whether ids were left"
        ),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=80, est_cost_usd=0.0, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    reference_examples=["updated", "failed", "more_remaining"],
    display=DisplayMetadata(
        emoji="✉️", i18n_key="set_email_read_state", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

__all__ = [
    "READ_STATE_IDS_DESCRIPTION",
    "READ_STATE_READ_DESCRIPTION",
    "set_email_read_state_catalogue_manifest",
]
