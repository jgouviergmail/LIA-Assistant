"""Catalogue manifests for the Gmail settings tool family (lot I, 2026-08).

Split from ``catalogue_manifests`` (size-frozen by the file-size ratchet):
one cohesive family — reading mailbox settings and the HITL-drafted vacation
responder write — registered by the catalogue loader via
``GMAIL_SETTINGS_TOOL_MANIFESTS``.
"""

from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. GET GMAIL SETTINGS
# ============================================================================
_get_gmail_settings_desc = (
    "**Tool: get_gmail_settings_tool** - Read Gmail mailbox settings.\n"
    "\n"
    "Returns the vacation responder state (enabled, subject, body, dates), the "
    "exact list of filters (criteria and actions) and the send-as aliases.\n"
    "Use for 'is my auto-reply on?', 'what filters do I have?', or before "
    "changing the vacation responder. Gmail only, no parameters."
)

get_gmail_settings_catalogue_manifest = ToolManifest(
    name="get_gmail_settings_tool",
    agent="email_agent",
    description=_get_gmail_settings_desc,
    semantic_keywords=[
        "gmail settings",
        "vacation responder status",
        "auto reply status",
        "out of office status",
        "list email filters",
        "email aliases",
        "send as addresses",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(path="vacation_responder", type="object", description="Auto-reply state"),
        OutputFieldSchema(
            path="vacation_responder.enabled", type="boolean", description="Auto-reply on/off"
        ),
        OutputFieldSchema(path="filters", type="array", description="Gmail filters"),
        OutputFieldSchema(path="filter_count", type="integer", description="Exact filter count"),
        OutputFieldSchema(path="send_as", type="array", description="Send-as aliases"),
        OutputFieldSchema(path="send_as_count", type="integer", description="Exact alias count"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=200, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["vacation_responder", "filter_count"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="⚙️", i18n_key="get_gmail_settings", visible=True, category="tool"
    ),
)


# ============================================================================
# 2. SET VACATION RESPONDER (HITL draft)
# ============================================================================
_set_vacation_desc = (
    "**Tool: set_vacation_responder_tool** - Set or disable the Gmail auto-reply.\n"
    "\n"
    "**USAGE**:\n"
    "- Enable: enable=true with body (required) and optional subject/dates\n"
    "- Disable: enable=false alone\n"
    "- Dates are YYYY-MM-DD in the user's timezone; end_date is INCLUSIVE\n"
    "\n"
    "Returns a confirmation draft: nothing is written until the user approves "
    "the exact wording (the auto-reply is sent verbatim to every sender)."
)

set_vacation_responder_catalogue_manifest = ToolManifest(
    name="set_vacation_responder_tool",
    # ADR-256: changes a Gmail setting that auto-replies to every sender.
    tool_category="update",
    agent="email_agent",
    description=_set_vacation_desc,
    semantic_keywords=[
        "vacation responder",
        "auto reply",
        "out of office message",
        "away message",
        "holiday auto response",
        "disable auto reply",
    ],
    parameters=[
        ParameterSchema(
            name="enable",
            type="boolean",
            required=True,
            description="True to turn the auto-reply on, False to turn it off",
        ),
        ParameterSchema(
            name="subject",
            type="string",
            required=False,
            description="Auto-reply subject (when enabling)",
        ),
        ParameterSchema(
            name="body",
            type="string",
            required=False,
            description="Auto-reply message body, sent verbatim. Required when enabling.",
        ),
        # Plain YYYY-MM-DD strings — no registered temporal semantic_type fits
        # (the "datetime" core type is ISO 8601 datetime, not a bare date).
        ParameterSchema(
            name="start_date",
            type="string",
            required=False,
            description="First active day, YYYY-MM-DD (user timezone)",
        ),
        ParameterSchema(
            name="end_date",
            type="string",
            required=False,
            description="Last active day INCLUSIVE, YYYY-MM-DD (user timezone)",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="enabled", type="boolean", description="Auto-reply on/off"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=80, est_cost_usd=0.005, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # Draft-based: HITL is handled by draft_critique (preview before writing),
        # like send_email/delete_email. hitl_required MUST stay False — the flag
        # only drives ReAct's pre-execution interrupt, redundant for draft tools.
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success", "enabled"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🌴", i18n_key="set_vacation_responder", visible=True, category="tool"
    ),
)


# ============================================================================
# 3. CREATE EMAIL FILTER (HITL draft)
# ============================================================================
_create_filter_desc = (
    "**Tool: create_email_filter_tool** - Create a Gmail filter.\n"
    "\n"
    "**USAGE**:\n"
    "- At least ONE criterion: from_sender, subject_contains or query\n"
    "- At least ONE action: label_name (existing label), archive, mark_as_read\n"
    "- The label must exist — create it first with create_label_tool\n"
    "\n"
    "Returns a confirmation draft: a filter rewrites how every future "
    "matching email is handled, so nothing is created until the user approves."
)

create_email_filter_catalogue_manifest = ToolManifest(
    name="create_email_filter_tool",
    agent="email_agent",
    description=_create_filter_desc,
    semantic_keywords=[
        "create email filter",
        "automatically label mail from sender",
        "auto archive newsletters",
        "filter incoming emails rule",
        "mark matching mail as read automatically",
    ],
    parameters=[
        ParameterSchema(
            name="from_sender",
            type="string",
            required=False,
            description="Match mail from this sender (address or domain)",
            semantic_type="email_address",
        ),
        ParameterSchema(
            name="subject_contains",
            type="string",
            required=False,
            description="Match mail whose subject contains this text",
        ),
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description="Gmail query criteria (e.g. 'has:attachment larger:5M')",
        ),
        ParameterSchema(
            name="label_name",
            type="string",
            required=False,
            description="Existing label to apply (case-insensitive)",
            semantic_type="email_label",
        ),
        ParameterSchema(
            name="archive",
            type="boolean",
            required=False,
            description="Skip the inbox for matching mail",
        ),
        ParameterSchema(
            name="mark_as_read",
            type="boolean",
            required=False,
            description="Mark matching mail as read",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="filter_id", type="string", description="Created filter id"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=80, est_cost_usd=0.005, est_latency_ms=700),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES,
        # Draft-based: HITL is handled by draft_critique (preview before
        # writing) — hitl_required MUST stay False (ReAct interrupt only).
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success", "filter_id"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📥", i18n_key="create_email_filter", visible=True, category="tool"
    ),
)


# Gmail settings family (lot I) — loop-registered by the catalogue loader.
GMAIL_SETTINGS_TOOL_MANIFESTS: tuple[ToolManifest, ...] = (
    get_gmail_settings_catalogue_manifest,
    set_vacation_responder_catalogue_manifest,
    create_email_filter_catalogue_manifest,
)


__all__ = [
    "GMAIL_SETTINGS_TOOL_MANIFESTS",
    "get_gmail_settings_catalogue_manifest",
    "set_vacation_responder_catalogue_manifest",
    "create_email_filter_catalogue_manifest",
]
