"""
Catalogue manifest of ``get_emails_tool`` — one tool, three detail levels (ADR-287).

Extracted from ``catalogue_manifests.py`` (size-frozen) when the levels, the
paging and the body pagination joined the contract. What this manifest
publishes is what the tool enforces (ADR-184): the default and the maximum
page size, the three levels, the paging token, the body parts.
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
    "**Tool: get_emails_tool** - Search the mailbox or fetch messages by id.\n"
    "\n"
    "**USAGE**:\n"
    "- Search: use `query` parameter\n"
    "- Fetch by ID (from $steps or CONTEXT only): use `message_id` or `message_ids`\n"
    "- List all: omit query\n"
    "\n"
    "**DETAIL** (what each message carries, and what it costs):\n"
    "- `metadata` (no body, no model call): sender, subject, date, snippet, labels, "
    "attachments. For listings.\n"
    "- `full` (default, no model call): the clean text body, one PART at a time "
    "(`part`; read `body_parts`, pass `part=2` for the next one). For one or a few messages.\n"
    "- `summary` (one short model call per NEW message, then cached): gist, key_points, "
    "actions, category, importance. For syntheses over many messages "
    "(unread, this week, newsletters, routines).\n"
    "\n"
    "**SEARCHABLE FIELDS** (query parameter - Gmail advanced search):\n"
    "- from:, to:, subject:, body keywords, has:attachment, is:unread, after:/before:\n"
    "- Gmail supports most search criteria natively\n"
    "\n"
    "**SCOPE**:\n"
    "- 'latest/recent/received emails' with no other precision → query='in:inbox' — the inbox is "
    "what the person calls their mail; archived messages are not in it\n"
    "- a SPECIFIC message ('emails from X', 'emails about Y') → add `in:anywhere` so an archived "
    "one is found: query='from:X in:anywhere', query='Y in:anywhere' (keywords, no quotes)\n"
    "- 'show this email' → message_id=ID from $steps or CONTEXT\n"
    "\n"
    "**HOW MANY**: `max_results` is the number the person asked for ('my last 6 emails' → 6). "
    "Under `summary` every message is a paid model call: never fetch 20 to pick 6. A narrower need "
    "('from newsletter X') goes in the query (`from:`, `subject:`), never in a larger page.\n"
    "\n"
    "**FOLDER/LABEL MAPPINGS** (MUST use label: syntax when user explicitly specifies a folder):\n"
    "- 'inbox' → query='label:INBOX'\n"
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
    "**RETURNS**: the messages at the requested detail; `result_size_estimate` is the "
    "provider ESTIMATE (never an exact count); `next_page_token` continues the same search."
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
            description=(
                "Gmail query (optional). Recent mail with no other precision: in:inbox; "
                "a specific message: add in:anywhere."
            ),
            constraints=[],
        ),
        # ID mode parameters
        ParameterSchema(
            name="message_id",
            type="string",
            required=False,
            description="Single message ID for direct fetch (optional).",
            semantic_type="message_id",
        ),
        ParameterSchema(
            name="message_ids",
            type="array",
            required=False,
            description="Multiple message IDs for batch fetch (optional).",
            semantic_type="message_id",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=(
                f"The number the person asked for (def: {settings.emails_tool_default_limit}, "
                f"max: {settings.emails_tool_default_max_results}); under summary each one is a "
                "paid model call"
            ),
            constraints=[
                ParameterConstraint(kind="maximum", value=settings.emails_tool_default_max_results)
            ],
        ),
        ParameterSchema(
            name="detail",
            type="string",
            required=False,
            description=(
                "metadata (no body) | full (default: body, paginated) | summary "
                "(digest per message, cached)"
            ),
            constraints=[ParameterConstraint(kind="enum", value=["metadata", "full", "summary"])],
        ),
        ParameterSchema(
            name="page_token",
            type="string",
            required=False,
            description="next_page_token of a previous page, to continue the same search",
        ),
        ParameterSchema(
            name="part",
            type="integer",
            required=False,
            description="1-based part of a long body under full (def: 1; see body_parts)",
            constraints=[ParameterConstraint(kind="minimum", value=1)],
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
        OutputFieldSchema(
            path="emails[].snippet",
            type="string",
            description="Preview snippet",
            semantic_type="message_snippet",
        ),
        OutputFieldSchema(
            path="emails[].labelIds",
            type="array",
            description="Labels",
            semantic_type="email_label",
        ),
        OutputFieldSchema(path="emails[].subject", type="string", description="Email subject line"),
        OutputFieldSchema(
            path="emails[].from",
            type="string",
            description="Sender (RFC 5322 name-addr, e.g. 'Jane <jane@x.com>')",
            semantic_type="email_address",  # Cross-domain: "reply to/invite the sender"
        ),
        OutputFieldSchema(
            path="emails[].body",
            type="string",
            description="Clean text body, one part (full only; see body_part/body_parts)",
            semantic_type="email_body",
        ),
        OutputFieldSchema(
            path="emails[].body_parts",
            type="integer",
            description="Number of parts of the body (full only)",
        ),
        OutputFieldSchema(
            path="emails[].date_formatted",
            type="string",
            description="Date in the user timezone and language",
        ),
        OutputFieldSchema(
            path="emails[].attachments",
            type="array",
            description="Attachment info",
            semantic_type="attachment_info",
        ),
        OutputFieldSchema(path="count", type="integer", description="Messages in this page"),
        OutputFieldSchema(
            path="result_size_estimate",
            type="integer",
            description="Provider estimate of all matches (an ESTIMATE, never exact)",
        ),
        OutputFieldSchema(path="detail", type="string", description="The level served"),
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
    # context_save_mode set dynamically by tool (LIST for search, DETAILS for ID fetch)
    reference_examples=["emails[0].id", "emails[0].body", "emails[0].subject", "count"],
    version="3.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📧", i18n_key="get_emails", visible=True, category="tool"),
)


__all__ = ["get_emails_catalogue_manifest"]
