"""
Catalogue manifests for Gmail tools.
Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_emails_tool replaces search_emails_tool + get_email_details_tool
- Always returns full email content (body, headers, attachments)
- Supports query mode (search) OR ID mode (direct fetch)
"""

from src.core.config import settings
from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.core.field_names import FIELD_QUERY
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. GET EMAILS (Unified - replaces search + details)
# ============================================================================
_get_emails_desc = (
    "**Tool: get_emails_tool** - Get emails with full details.\n"
    "\n"
    "**MODES**:\n"
    "- Query mode: get_emails_tool(query='from:john') → search + return full details\n"
    "- ID mode: get_emails_tool(message_id='abc123') → fetch specific email\n"
    "- Batch mode: get_emails_tool(message_ids=['abc', 'def']) → fetch multiple emails\n"
    "- List mode: get_emails_tool() → return latest emails with full details\n"
    "\n"
    "**SEARCHABLE FIELDS** (query parameter - Gmail advanced search):\n"
    "- from:, to:, subject:, body keywords, has:attachment, is:unread, after:/before:\n"
    "- Gmail supports most search criteria natively\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'latest/recent emails' → query='' (empty, returns latest by date)\n"
    "- 'received emails' → query='-in:sent -in:draft'\n"
    "- 'emails from X' → query='from:X'\n"
    "- 'emails about Y' → query='Y' (keywords, no quotes)\n"
    "- 'show this email' → message_id='ID from context'\n"
    "\n"
    "**FOLDER/LABEL MAPPINGS** (MUST use label: syntax when user specifies a folder):\n"
    "- 'inbox' / 'in my inbox' → query='label:INBOX'\n"
    "- 'sent' → query='label:SENT'\n"
    "- 'drafts' → query='label:DRAFT'\n"
    "- 'trash' / 'deleted' → query='label:TRASH'\n"
    "- 'spam' → query='label:SPAM'\n"
    "- 'starred' / 'important' → query='label:STARRED'\n"
    "⚠️ When user specifies a folder, ALWAYS use label: syntax, NOT -in: exclusions.\n"
    "\n"
    "**QUERY RULES**:\n"
    "- Use plain keywords WITHOUT quotes for text search\n"
    "- Use 'from:', 'to:' for sender/recipient filtering\n"
    "- Use 'is:unread', 'has:attachment' for status filtering\n"
    "- Use 'after:', 'before:' for date filtering\n"
    "\n"
    "**RETURNS**: Full email content (body, headers, attachments)."
)

get_emails_catalogue_manifest = ToolManifest(
    name="get_emails_tool",
    agent="email_agent",
    description=_get_emails_desc,
    # Discriminant phrases - Email mailbox operations
    semantic_keywords=[
        # Email retrieval from mailbox
        "show emails in my inbox mailbox",
        "get latest messages from email account",
        "read unread emails in inbox",
        "list recent messages received by email",
        # Email search in mailbox
        "find emails from specific sender",
        "search messages with attachment in inbox",
        "emails about topic in my mailbox",
        "starred important emails in account",
        # Email content reading
        "read full body of email message",
        "show email content and attachments",
        "get complete message text from inbox",
        "view email thread conversation",
        # Email filtering
        "emails received today in mailbox",
        "messages from last week in inbox",
        "unread important emails to check",
    ],
    parameters=[
        # Query mode parameter
        ParameterSchema(
            name=FIELD_QUERY,
            type="string",
            required=False,
            description="Gmail query (optional). Empty for latest emails.",
            constraints=[],
        ),
        # ID mode parameters
        ParameterSchema(
            name="message_id",
            type="string",
            required=False,
            description="Single message ID for direct fetch (optional).",
        ),
        ParameterSchema(
            name="message_ids",
            type="array",
            required=False,
            description="Multiple message IDs for batch fetch (optional).",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max results for query mode (def: {settings.emails_tool_default_limit}, max: {settings.emails_tool_default_max_results})",
            constraints=[
                ParameterConstraint(kind="maximum", value=settings.emails_tool_default_max_results)
            ],
        ),
        ParameterSchema(
            name="use_cache", type="boolean", required=False, description="Use cache (def: true)"
        ),
    ],
    outputs=[
        # Full email outputs (merged from both tools)
        OutputFieldSchema(
            path="emails", type="array", description="List of emails with full details"
        ),
        OutputFieldSchema(
            path="emails[].id", type="string", description="Message ID", semantic_type="message_id"
        ),
        OutputFieldSchema(
            path="emails[].threadId",
            type="string",
            description="Thread ID",
            semantic_type="thread_id",
        ),
        OutputFieldSchema(path="emails[].snippet", type="string", description="Preview snippet"),
        OutputFieldSchema(
            path="emails[].labelIds",
            type="array",
            description="Labels",
            semantic_type="email_label",
        ),
        OutputFieldSchema(path="emails[].headers", type="object", description="Email headers"),
        OutputFieldSchema(path="emails[].body", type="string", description="Full email body"),
        OutputFieldSchema(path="emails[].attachments", type="array", description="Attachment info"),
        OutputFieldSchema(path="total", type="integer", description="Total count"),
    ],
    cost=CostProfile(
        est_tokens_in=150, est_tokens_out=1200, est_cost_usd=0.003, est_latency_ms=800
    ),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=["id", "snippet", "body"],
    context_key="emails",
    reference_examples=["emails[0].id", "emails[0].body", "emails[0].subject", "total"],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📧", i18n_key="get_emails", visible=True, category="tool"),
)


# ============================================================================
# 2. SEND EMAIL
# ============================================================================
_send_desc = "**Tool: send_email_tool** - Send new email. **REQUIRES HITL**. Irreversible."

send_email_catalogue_manifest = ToolManifest(
    name="send_email_tool",
    agent="email_agent",
    description=_send_desc,
    semantic_keywords=[
        "send email",
        "write email",
        "send message",
        "write message",
        "send email with attachment",
        "email someone",
        "create new email",
    ],
    parameters=[
        ParameterSchema(
            name="to",
            type="string",
            required=True,
            description="Recipient(s)",
            constraints=[ParameterConstraint(kind="min_length", value=3)],
            semantic_type="email_address",  # Cross-domain: can use contacts[].emails[].value
        ),
        ParameterSchema(
            name="subject",
            type="string",
            required=False,  # Optional if content_instruction provided
            description="Subject. Required unless content_instruction is provided.",
        ),
        ParameterSchema(
            name="body",
            type="string",
            required=False,  # Optional if content_instruction provided
            description="Content. Required unless content_instruction is provided.",
        ),
        # Content generation: allows the planner to delegate creative content generation
        ParameterSchema(
            name="content_instruction",
            type="string",
            required=False,
            description=(
                "Creative content instruction for LLM generation. "
                "Use when user requests creative content (poem, story, etc.) instead of dictating exact text. "
                "If provided, subject and body will be generated by LLM based on this instruction. "
                "Example: 'write a love poem about Excel' or 'compose a formal thank you note'."
            ),
        ),
        ParameterSchema(
            name="cc",
            type="string",
            required=False,
            description="CC",
            semantic_type="email_address",
        ),
        ParameterSchema(
            name="bcc",
            type="string",
            required=False,
            description="BCC",
            semantic_type="email_address",
        ),
        ParameterSchema(name="is_html", type="boolean", required=False, description="Is HTML body"),
    ],
    outputs=[
        OutputFieldSchema(
            path="message_id", type="string", description="Sent ID", semantic_type="message_id"
        ),
        OutputFieldSchema(
            path="to", type="string", description="Recipient", semantic_type="email_address"
        ),
    ],
    cost=CostProfile(est_tokens_in=200, est_tokens_out=100, est_cost_usd=0.01, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before sending)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        # draft_critique allows the user to view/modify the exact content before sending
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_id", "to"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✉️", i18n_key="send_email", visible=True, category="tool"),
)

# ============================================================================
# 4. REPLY EMAIL
# ============================================================================
_reply_desc = (
    "**Tool: reply_email_tool** - Reply to existing email. **REQUIRES HITL**.\n"
    "Auto-fills recipient and subject. Provide only 'body'."
)

reply_email_catalogue_manifest = ToolManifest(
    name="reply_email_tool",
    agent="email_agent",
    description=_reply_desc,
    semantic_keywords=[
        "reply to this email message",
        "respond to sender of email",
        "answer back to received message",
        "reply all to email recipients",
    ],
    parameters=[
        ParameterSchema(
            name="message_id", type="string", required=True, description="Original Msg ID"
        ),
        ParameterSchema(name="body", type="string", required=True, description="Reply content"),
        ParameterSchema(
            name="reply_all", type="boolean", required=False, description="Reply All (def: false)"
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message_id", type="string", description="Sent ID", semantic_type="message_id"
        ),
        OutputFieldSchema(
            path="thread_id", type="string", description="Thread ID", semantic_type="thread_id"
        ),
    ],
    cost=CostProfile(est_tokens_in=200, est_tokens_out=100, est_cost_usd=0.01, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before sending)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_id", "thread_id"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="↩️", i18n_key="reply_email", visible=True, category="tool"),
)

# ============================================================================
# 5. FORWARD EMAIL
# ============================================================================
_fwd_desc = "**Tool: forward_email_tool** - Forward email to new recipient. **REQUIRES HITL**."

forward_email_catalogue_manifest = ToolManifest(
    name="forward_email_tool",
    agent="email_agent",
    description=_fwd_desc,
    semantic_keywords=[
        "forward email",
        "transfer email",
        "share email",
        "transfer message",
    ],
    parameters=[
        ParameterSchema(
            name="message_id", type="string", required=True, description="Original Msg ID"
        ),
        ParameterSchema(
            name="to",
            type="string",
            required=True,
            description="New Recipient",
            constraints=[ParameterConstraint(kind="min_length", value=3)],
            semantic_type="email_address",  # Cross-domain: can use contacts[].emails[].value
        ),
        ParameterSchema(name="body", type="string", required=False, description="Intro note"),
        ParameterSchema(
            name="cc",
            type="string",
            required=False,
            description="CC",
            semantic_type="email_address",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="message_id", type="string", description="Sent ID", semantic_type="message_id"
        ),
        OutputFieldSchema(
            path="to", type="string", description="Recipient", semantic_type="email_address"
        ),
    ],
    cost=CostProfile(est_tokens_in=250, est_tokens_out=100, est_cost_usd=0.01, est_latency_ms=900),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before sending)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_id", "to"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="➡️", i18n_key="forward_email", visible=True, category="tool"),
)

# ============================================================================
# 6. DELETE EMAIL
# ============================================================================
_del_desc = (
    "**Tool: delete_email_tool** - Move email to trash. **REQUIRES HITL**. Recoverable 30 days."
)

delete_email_catalogue_manifest = ToolManifest(
    name="delete_email_tool",
    agent="email_agent",
    description=_del_desc,
    semantic_keywords=[
        "delete email message from inbox",
        "move email to trash folder",
        "remove message from mailbox",
        "discard unwanted email permanently",
    ],
    parameters=[
        ParameterSchema(
            name="message_id", type="string", required=True, description="Msg ID to delete"
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(
            path="message_id", type="string", description="Deleted ID", semantic_type="message_id"
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=50, est_cost_usd=0.005, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # hitl_required=True: Deletion is destructive and has no draft_critique
        # HITL via approval_gate is required to confirm before deletion
        hitl_required=True,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success", "message_id"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_email", visible=True, category="tool"),
)


# ============================================================================
# 6. LIST LABELS
# ============================================================================
_list_labels_desc = (
    "**Tool: list_labels_tool** - List or search Gmail labels.\n"
    "\n"
    "**USAGE**: Use name_filter to find specific labels (case-insensitive partial match).\n"
    "Example: name_filter='famille' matches 'Famille', 'Famille/Oncles', etc.\n"
    "\n"
    "**RETURNS**: User labels with hierarchical structure (e.g., pro/capge/2024).\n"
    "System labels (INBOX, SENT, etc.) are excluded by default."
)

list_labels_catalogue_manifest = ToolManifest(
    name="list_labels_tool",
    agent="email_agent",
    description=_list_labels_desc,
    semantic_keywords=[
        "list email labels",
        "show gmail folders",
        "get label categories",
        "display email tags",
        "view mailbox labels",
        "show email folders structure",
        "find label by name",
        "search gmail label",
        "filter labels",
    ],
    parameters=[
        ParameterSchema(
            name="name_filter",
            type="string",
            required=False,
            description="Filter labels by name (case-insensitive partial match). "
            "E.g., 'famille' matches 'Famille', 'Famille/Oncles'",
        ),
        ParameterSchema(
            name="include_system",
            type="boolean",
            required=False,
            description="Include system labels (INBOX, SENT, etc.). Default: false",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="labels", type="array", description="List of user labels"),
        OutputFieldSchema(path="labels[].id", type="string", description="Label ID"),
        OutputFieldSchema(path="labels[].name", type="string", description="Label name (path)"),
        OutputFieldSchema(path="total_user_labels", type="integer", description="Total count"),
        OutputFieldSchema(path="name_filter", type="string", description="Filter used (if any)"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=200),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["labels[0].name", "total_user_labels"],
    version="1.1.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏷️", i18n_key="list_labels", visible=True, category="tool"),
)


# ============================================================================
# 7. CREATE LABEL
# ============================================================================
_create_label_desc = (
    "**Tool: create_label_tool** - Create a new Gmail label.\n"
    "\n"
    "Supports hierarchical labels using '/' separator.\n"
    "Example: 'pro/capge/2024' creates nested label structure."
)

create_label_catalogue_manifest = ToolManifest(
    name="create_label_tool",
    agent="email_agent",
    description=_create_label_desc,
    semantic_keywords=[
        "create email label",
        "add new gmail folder",
        "make label category",
        "create email tag",
        "new mailbox label",
    ],
    parameters=[
        ParameterSchema(
            name="name",
            type="string",
            required=True,
            description="Label name. Use '/' for hierarchy (e.g., 'pro/capge/2024')",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="label", type="object", description="Created label"),
        OutputFieldSchema(path="label.id", type="string", description="Label ID"),
        OutputFieldSchema(path="label.name", type="string", description="Label name"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=100, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["label.id", "label.name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏷️", i18n_key="create_label", visible=True, category="tool"),
)


# ============================================================================
# 8. UPDATE LABEL
# ============================================================================
_update_label_desc = (
    "**Tool: update_label_tool** - Rename a Gmail label.\n"
    "\n"
    "Note: Renaming a parent label may affect sublabels."
)

update_label_catalogue_manifest = ToolManifest(
    name="update_label_tool",
    agent="email_agent",
    description=_update_label_desc,
    semantic_keywords=[
        "rename email label",
        "update gmail folder name",
        "change label name",
        "modify email tag",
    ],
    parameters=[
        ParameterSchema(
            name="label_name",
            type="string",
            required=True,
            description="Current label name or path",
        ),
        ParameterSchema(
            name="new_name",
            type="string",
            required=True,
            description="New label name",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="old_name", type="string", description="Previous name"),
        OutputFieldSchema(path="new_name", type="string", description="New name"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=100, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["old_name", "new_name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✏️", i18n_key="update_label", visible=True, category="tool"),
)


# ============================================================================
# 9. DELETE LABEL
# ============================================================================
_delete_label_desc = (
    "**Tool: delete_label_tool** - Delete a Gmail label. **REQUIRES HITL**.\n"
    "\n"
    "If the label has sublabels, they will also be deleted.\n"
    "Use children_only=true to delete only sublabels."
)

delete_label_catalogue_manifest = ToolManifest(
    name="delete_label_tool",
    agent="email_agent",
    description=_delete_label_desc,
    semantic_keywords=[
        "delete email label",
        "remove gmail folder",
        "delete label category",
        "remove email tag",
        "delete sublabels",
    ],
    parameters=[
        ParameterSchema(
            name="label_name",
            type="string",
            required=True,
            description="Label name or path to delete",
        ),
        ParameterSchema(
            name="children_only",
            type="boolean",
            required=False,
            description="If true, only delete sublabels, keep parent. Default: false",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="deleted_count", type="integer", description="Labels deleted"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=100, est_cost_usd=0.001, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=True, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["deleted_count"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_label", visible=True, category="tool"),
)


# ============================================================================
# 10. APPLY LABELS
# ============================================================================
_apply_labels_desc = (
    "**Tool: apply_labels_tool** - Apply/add/put/set labels to email(s).\n"
    "\n"
    "**USAGE**: Use this AFTER searching emails to apply a label to the results.\n"
    "Auto-creates labels if they don't exist (use auto_create=false to disable).\n"
    "Supports single or bulk operations via message_id or message_ids."
)

apply_labels_catalogue_manifest = ToolManifest(
    name="apply_labels_tool",
    agent="email_agent",
    description=_apply_labels_desc,
    semantic_keywords=[
        # Direct actions
        "apply label to email",
        "add label to message",
        "put label to message",
        "set label to message",
        "tag email with label",
        "label emails",
        # Workflow patterns (after search)
        "apply label to search results",
        "label found emails",
        "tag these emails",
        "mark emails with label",
        # Categorization
        "categorize email",
        "organize emails with label",
        "move email to folder",
        # Bulk operations
        "apply label to multiple emails",
        "bulk label emails",
    ],
    parameters=[
        ParameterSchema(
            name="label_names",
            type="array",
            required=True,
            description="Label names to apply",
        ),
        ParameterSchema(
            name="message_id",
            type="string",
            required=False,
            description="Single message ID",
            semantic_type="message_id",
        ),
        ParameterSchema(
            name="message_ids",
            type="array",
            required=False,
            description="Multiple message IDs for bulk operation",
        ),
        ParameterSchema(
            name="auto_create",
            type="boolean",
            required=False,
            description="Create labels if they don't exist. Default: true",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="message_count", type="integer", description="Emails modified"),
        OutputFieldSchema(path="labels_applied", type="array", description="Labels applied"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=100, est_cost_usd=0.002, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_count", "labels_applied"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏷️", i18n_key="apply_labels", visible=True, category="tool"),
)


# ============================================================================
# 11. REMOVE LABELS
# ============================================================================
_remove_labels_desc = (
    "**Tool: remove_labels_tool** - Remove labels from email(s).\n"
    "\n"
    "Supports single or bulk operations."
)

remove_labels_catalogue_manifest = ToolManifest(
    name="remove_labels_tool",
    agent="email_agent",
    description=_remove_labels_desc,
    semantic_keywords=[
        "remove label from email",
        "untag email",
        "remove category from message",
        "unlabel emails",
    ],
    parameters=[
        ParameterSchema(
            name="label_names",
            type="array",
            required=True,
            description="Label names to remove",
        ),
        ParameterSchema(
            name="message_id",
            type="string",
            required=False,
            description="Single message ID",
            semantic_type="message_id",
        ),
        ParameterSchema(
            name="message_ids",
            type="array",
            required=False,
            description="Multiple message IDs for bulk operation",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="message_count", type="integer", description="Emails modified"),
        OutputFieldSchema(path="labels_removed", type="array", description="Labels removed"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=100, est_cost_usd=0.002, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_count", "labels_removed"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🏷️", i18n_key="remove_labels", visible=True, category="tool"),
)


__all__ = [
    # Unified tool (v2.0 - replaces search + details)
    "get_emails_catalogue_manifest",
    # Action tools
    "send_email_catalogue_manifest",
    "reply_email_catalogue_manifest",
    "forward_email_catalogue_manifest",
    "delete_email_catalogue_manifest",
    # Label management tools
    "list_labels_catalogue_manifest",
    "create_label_catalogue_manifest",
    "update_label_catalogue_manifest",
    "delete_label_catalogue_manifest",
    "apply_labels_catalogue_manifest",
    "remove_labels_catalogue_manifest",
]
