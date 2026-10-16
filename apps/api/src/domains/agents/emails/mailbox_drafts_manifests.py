"""Catalogue manifests of the mailbox draft tools (ADR-344).

A mailbox draft is the person's own unsent message in their mailbox — never the
confirmation card LIA builds before an action. Beside ``catalogue_manifests.py``
because that module is at its size cap (``attachment_manifest.py`` precedent).
What a manifest publishes is what its tool enforces (ADR-184).

``emails[].id`` of a draft is deliberately left untyped: a draft's message id
must never be offered to ``reply_email_tool`` or ``forward_email_tool`` as the
message they answer, and a typed output would make this listing their source.
The handle every draft tool takes is ``mailbox_draft_id``.
"""

from src.core.config import settings
from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_QUERY
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

MAILBOX_DRAFT_ID_TYPE = "mailbox_draft_id"

#: The count parameters' wording, read by the manifest AND the tool's schema: the
#: ReAct loop binds the schema and never sees the manifest (ADR-310), so a bound
#: only the manifest's constraint published would be hidden from it (ADR-184).
LIST_MAX_RESULTS_DESCRIPTION = (
    f"How many drafts the person asked for, 1 to {settings.emails_tool_default_max_results} "
    f"(default: {settings.emails_tool_default_limit})."
)
DELETE_MAX_RESULTS_DESCRIPTION = (
    "Or how many of the newest drafts ('my last 3 drafts' -> 3), 1 to "
    f"{settings.email_drafts_bulk_max} per call."
)

_list_desc = (
    "**Tool: list_mailbox_drafts_tool** - List the person's mailbox DRAFTS: their own unsent "
    "messages saved in Gmail, Outlook or iCloud.\n"
    "\n"
    "**USAGE**:\n"
    "- 'my drafts', 'my last 5 drafts' → no query, `max_results` = the number asked\n"
    "- 'my drafts for Marie' → query='to:marie'; about a topic → query='subject:budget' or words\n"
    "- Before editing, deleting or sending a draft named by its recipient or subject, list it "
    "to get its `mailbox_draft_id`\n"
    "\n"
    "**NOT FOR**: received or sent messages (get_emails_tool).\n"
    "\n"
    "**RETURNS**: `emails[]`, newest saves first, each with `mailbox_draft_id` (the handle the "
    "draft tools take), recipients, subject and the person's own words (`quotes_history`: a "
    "message is quoted below them); `result_size_estimate` as the provider states it; "
    "`next_page_token` continues the listing; `set_aside_on_page`, when present, counts drafts "
    "of this page a date condition set aside after the provider's search — more may follow."
)

list_mailbox_drafts_catalogue_manifest = ToolManifest(
    name="list_mailbox_drafts_tool",
    agent="email_agent",
    description=_list_desc,
    concurrency_safe=True,
    # A turn that lists twice reads once; a write in between empties the reuse
    # (ADR-337: mutations invalidate the turn's reads).
    result_reuse_ttl_seconds=30,
    semantic_keywords=[
        "show my email drafts",
        "list my unsent draft messages",
        "my last five drafts in the mailbox",
        "drafts I prepared for a recipient",
        "the draft email I wrote to Marie",
        "find the draft about the budget",
        "what drafts are waiting in my mailbox",
        "open my saved draft emails",
    ],
    parameters=[
        ParameterSchema(
            name=FIELD_QUERY,
            type="string",
            required=False,
            description="to:/cc:/subject: or words to narrow the drafts (optional)",
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=LIST_MAX_RESULTS_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=settings.emails_tool_default_max_results),
            ],
        ),
        ParameterSchema(
            name="page_token",
            type="string",
            required=False,
            description="next_page_token of a previous page, to continue the listing",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="emails",
            type="array",
            description="The drafts, newest saves first",
            semantic_type="EmailMessage",
        ),
        OutputFieldSchema(
            path=f"emails[].{FIELD_MAILBOX_DRAFT_ID}",
            type="string",
            description="The draft's handle in the mailbox (what every draft tool takes)",
            semantic_type=MAILBOX_DRAFT_ID_TYPE,
        ),
        OutputFieldSchema(
            path="emails[].id",
            type="string",
            description="The draft's current message id (never a message to reply to)",
        ),
        OutputFieldSchema(
            path="emails[].to", type="string", description="Recipients", semantic_type="Text"
        ),
        OutputFieldSchema(
            path="emails[].cc", type="string", description="Copies", semantic_type="Text"
        ),
        OutputFieldSchema(
            path="emails[].subject", type="string", description="Subject", semantic_type="Text"
        ),
        OutputFieldSchema(
            path="emails[].body",
            type="string",
            description="The person's own words (the quoted message stays in the draft)",
            semantic_type="Text",
        ),
        OutputFieldSchema(
            path="emails[].quotes_history",
            type="boolean",
            description="Whether a message is quoted below the person's words",
        ),
        OutputFieldSchema(
            path="emails[].date_formatted",
            type="string",
            description="Last saved, in the user timezone and language",
            semantic_type="formatted_time",
        ),
        OutputFieldSchema(path="count", type="integer", description="Drafts in this page"),
        OutputFieldSchema(
            path="result_size_estimate",
            type="integer",
            nullable=True,
            description="The provider's total, as stated (absent when it states none)",
        ),
    ],
    cost=CostProfile(est_tokens_in=120, est_tokens_out=600, est_cost_usd=0.002, est_latency_ms=900),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    # Proactive enrichment has no use for the person's unsent drafts.
    initiative_eligible=False,
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=[FIELD_MAILBOX_DRAFT_ID, "subject", "to"],
    context_key="emails",
    reference_examples=[
        f"emails[0].{FIELD_MAILBOX_DRAFT_ID}",
        f"emails[*].{FIELD_MAILBOX_DRAFT_ID}",
        "emails[0].to",
        "count",
    ],
    display=DisplayMetadata(
        emoji="📝", i18n_key="list_mailbox_drafts", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)


# ============================================================================
# WRITES — reversible: a draft stays in the person's own mailbox, sent to nobody
# ============================================================================

_SAVE_REASON = (
    "The draft is saved in the person's own mailbox and sent to nobody: they can edit or "
    "delete it there, and only sending it — a separate, confirmed action — reaches anyone."
)
_DRAFT_PERMISSIONS = PermissionProfile(
    required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
)
_DRAFT_COST = CostProfile(
    est_tokens_in=150, est_tokens_out=300, est_cost_usd=0.002, est_latency_ms=1200
)

#: What every draft-saving tool returns: the saved draft, its handle first.
_SAVED_DRAFT_OUTPUTS = [
    OutputFieldSchema(
        path="emails", type="array", description="The saved draft", semantic_type="EmailMessage"
    ),
    OutputFieldSchema(
        path=f"emails[].{FIELD_MAILBOX_DRAFT_ID}",
        type="string",
        description="The draft's handle in the mailbox",
        semantic_type=MAILBOX_DRAFT_ID_TYPE,
    ),
    OutputFieldSchema(path="emails[].to", type="string", description="Recipients"),
    OutputFieldSchema(path="emails[].subject", type="string", description="Subject"),
    OutputFieldSchema(path="emails[].body", type="string", description="The person's own words"),
    OutputFieldSchema(
        path="emails[].quotes_history",
        type="boolean",
        description="Whether a message is quoted below the person's words",
    ),
]
_SAVED_DRAFT_EXAMPLES = [f"emails[0].{FIELD_MAILBOX_DRAFT_ID}", "emails[0].subject"]


def _text_param(name: str, description: str, *, required: bool = False) -> ParameterSchema:
    """A free-text parameter."""
    return ParameterSchema(name=name, type="string", required=required, description=description)


def _recipients(name: str, description: str, *, required: bool = False) -> ParameterSchema:
    """Recipients typed like send_email_tool's: a contacts step may feed them, and the
    tool resolves a contact NAME itself."""
    return ParameterSchema(
        name=name,
        type="string",
        required=required,
        description=description,
        semantic_type="email_address",
    )


_RECEIVED_MESSAGE = ParameterSchema(
    name="message_id",
    type="string",
    required=True,
    description="The received e-mail (from get_emails_tool or CONTEXT)",
    semantic_type="message_id",
)

create_mailbox_draft_catalogue_manifest = ToolManifest(
    name="create_mailbox_draft_tool",
    agent="email_agent",
    description=(
        "**Tool: create_mailbox_draft_tool** - Save a NEW draft in the person's own mailbox. "
        "Sends nothing, asks no confirmation.\n"
        "Use for 'prepare / draft / write an e-mail to X and keep it as a draft'; for SENDING "
        "use send_email_tool.\n"
        "- `to` may be names of contacts, or empty: a draft may wait for its recipient\n"
        "- The person dictated the text → `body` (+ `subject`); they said what it should say → "
        "`content_instruction`; they asked for an empty draft → neither\n"
        "**RETURNS**: the saved draft, with its `mailbox_draft_id`."
    ),
    mutation_policy="reversible",
    mutation_policy_reason=_SAVE_REASON,
    semantic_keywords=[
        "prepare a draft email for someone",
        "write an email draft and keep it",
        "save an email as a draft",
        "create a new draft message",
        "draft a message to Marie without sending",
    ],
    parameters=[
        _recipients("to", "Recipient(s): addresses or contact names (optional)"),
        _text_param("subject", "Subject (optional)"),
        _text_param("body", "The text, when dictated"),
        _text_param("content_instruction", "What it should say, for LIA to write it"),
        _recipients("cc", "Copies (optional)"),
        _recipients("bcc", "Blind copies (optional)"),
        ParameterSchema(name="is_html", type="boolean", required=False, description="HTML body"),
    ],
    outputs=_SAVED_DRAFT_OUTPUTS,
    cost=_DRAFT_COST,
    permissions=_DRAFT_PERMISSIONS,
    context_key="emails",
    reference_examples=_SAVED_DRAFT_EXAMPLES,
    display=DisplayMetadata(
        emoji="📝", i18n_key="create_mailbox_draft", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

create_mailbox_reply_draft_catalogue_manifest = ToolManifest(
    name="create_mailbox_reply_draft_tool",
    agent="email_agent",
    description=(
        "**Tool: create_mailbox_reply_draft_tool** - Save the REPLY to a received e-mail as a "
        "draft, in its thread, the original quoted below. Sends nothing, asks no "
        "confirmation.\n"
        "Use for 'prepare / draft a reply to this e-mail'; for SENDING a reply use "
        "reply_email_tool.\n"
        "- Without `body`, LIA writes the reply from the received e-mail; `content_instruction` "
        "says what it should answer ('accept', 'ask for Friday')\n"
        "- `reply_all` answers every recipient\n"
        "**RETURNS**: the saved draft, with its `mailbox_draft_id`."
    ),
    mutation_policy="reversible",
    mutation_policy_reason=_SAVE_REASON,
    semantic_keywords=[
        "prepare a reply draft to this email",
        "draft an answer to Marie's last email",
        "write a response to this message and keep it as a draft",
        "save a reply as a draft without sending",
    ],
    parameters=[
        _RECEIVED_MESSAGE,
        _text_param("body", "The reply's text, when dictated"),
        _text_param("content_instruction", "What the reply should say, for LIA to write it"),
        ParameterSchema(
            name="reply_all", type="boolean", required=False, description="Answer every recipient"
        ),
    ],
    outputs=_SAVED_DRAFT_OUTPUTS,
    cost=_DRAFT_COST,
    permissions=_DRAFT_PERMISSIONS,
    context_key="emails",
    reference_examples=_SAVED_DRAFT_EXAMPLES,
    display=DisplayMetadata(
        emoji="📝", i18n_key="create_mailbox_reply_draft", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

create_mailbox_forward_draft_catalogue_manifest = ToolManifest(
    name="create_mailbox_forward_draft_tool",
    agent="email_agent",
    description=(
        "**Tool: create_mailbox_forward_draft_tool** - Save the FORWARD of a received e-mail as "
        "a draft, with its files. Sends nothing, asks no confirmation.\n"
        "Use for 'prepare a forward of this e-mail to X'; for SENDING use forward_email_tool.\n"
        "- `to` is required (addresses or contact names); `body` is a note above the e-mail\n"
        "**RETURNS**: the saved draft, with its `mailbox_draft_id`."
    ),
    mutation_policy="reversible",
    mutation_policy_reason=_SAVE_REASON,
    semantic_keywords=[
        "prepare a forward of this email as a draft",
        "draft forwarding this message to Paul",
        "save a forward without sending it",
    ],
    parameters=[
        _RECEIVED_MESSAGE,
        _recipients("to", "Recipient(s): addresses or contact names", required=True),
        _text_param("body", "A note above the forwarded e-mail (optional)"),
        _recipients("cc", "Copies (optional)"),
    ],
    outputs=_SAVED_DRAFT_OUTPUTS,
    cost=_DRAFT_COST,
    permissions=_DRAFT_PERMISSIONS,
    context_key="emails",
    reference_examples=_SAVED_DRAFT_EXAMPLES,
    display=DisplayMetadata(
        emoji="📝", i18n_key="create_mailbox_forward_draft", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

_EXISTING_DRAFT = ParameterSchema(
    name=FIELD_MAILBOX_DRAFT_ID,
    type="string",
    required=True,
    description="The draft's handle (from list_mailbox_drafts_tool or CONTEXT)",
    semantic_type=MAILBOX_DRAFT_ID_TYPE,
)

update_mailbox_draft_catalogue_manifest = ToolManifest(
    name="update_mailbox_draft_tool",
    agent="email_agent",
    description=(
        "**Tool: update_mailbox_draft_tool** - Edit a draft of the person's mailbox. Sends "
        "nothing, asks no confirmation.\n"
        "- Fields given replace their value (empty string clears a recipient field); fields not "
        "given stay\n"
        "- `instructions` applies a change to the text ('make it shorter', 'add that I am late')\n"
        "- The message a reply quotes stays below the person's words\n"
        "**RETURNS**: the edited draft; its `mailbox_draft_id` may change (iCloud): use the "
        "returned one."
    ),
    mutation_policy="reversible",
    mutation_policy_reason=(
        "The draft stays in the person's own mailbox and is sent to nobody: they can edit it "
        "again or delete it there."
    ),
    semantic_keywords=[
        "edit my draft email",
        "change the recipient of my draft",
        "make my draft shorter",
        "modify the last draft I wrote to Marie",
    ],
    parameters=[
        _EXISTING_DRAFT,
        _recipients("to", "New recipient(s)"),
        _recipients("cc", "New copies"),
        _recipients("bcc", "New blind copies"),
        _text_param("subject", "New subject"),
        _text_param("body", "New text"),
        _text_param("instructions", "A change to apply to the draft"),
    ],
    outputs=_SAVED_DRAFT_OUTPUTS,
    cost=_DRAFT_COST,
    permissions=_DRAFT_PERMISSIONS,
    context_key="emails",
    reference_examples=_SAVED_DRAFT_EXAMPLES,
    display=DisplayMetadata(
        emoji="📝", i18n_key="update_mailbox_draft", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

delete_mailbox_drafts_catalogue_manifest = ToolManifest(
    name="delete_mailbox_drafts_tool",
    agent="email_agent",
    description=(
        "**Tool: delete_mailbox_drafts_tool** - Move drafts of the person's mailbox to its "
        "trash, where they stay recoverable. Asks no confirmation.\n"
        "Name the drafts ONE way, in ONE step (no for_each, no prior listing needed):\n"
        "- `mailbox_draft_ids` from CONTEXT or a listing\n"
        "- `query` (to:/subject:/words) and/or `max_results` ('my last 3 drafts' → 3)\n"
        "- `all_drafts`=true ('delete all my drafts')\n"
        f"At most {settings.email_drafts_bulk_max} per call: `more_remaining` says whether "
        "drafts remain.\n"
        "**RETURNS**: `emails[]` the drafts trashed, `failed[]` each draft not trashed and why "
        "(not_found, refused, unavailable), `more_remaining`."
    ),
    mutation_policy="reversible",
    mutation_policy_reason=(
        "Drafts go to the mailbox's own trash (Gmail and iCloud trash, Outlook Deleted Items), "
        "where the person can restore them: nothing is deleted for good, nothing is sent."
    ),
    semantic_keywords=[
        "delete all my drafts",
        "remove my last three drafts",
        "trash the draft for Marie",
        "clean up my draft emails",
    ],
    parameters=[
        ParameterSchema(
            name="mailbox_draft_ids",
            type="array",
            required=False,
            description="The drafts' handles",
            semantic_type=MAILBOX_DRAFT_ID_TYPE,
        ),
        _text_param(FIELD_QUERY, "Or a search among the drafts"),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=DELETE_MAX_RESULTS_DESCRIPTION,
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=settings.email_drafts_bulk_max),
            ],
        ),
        ParameterSchema(
            name="all_drafts", type="boolean", required=False, description="Or every draft"
        ),
    ],
    outputs=[
        OutputFieldSchema(path="emails", type="array", description="The drafts trashed"),
        OutputFieldSchema(path="failed", type="array", description="Drafts not trashed, and why"),
        OutputFieldSchema(
            path="more_remaining", type="boolean", description="Whether drafts remain"
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=150, est_cost_usd=0.0, est_latency_ms=1500),
    permissions=_DRAFT_PERMISSIONS,
    reference_examples=["emails", "failed", "more_remaining"],
    display=DisplayMetadata(
        emoji="🗑️", i18n_key="delete_mailbox_drafts", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)


# ============================================================================
# SEND — the one draft act that reaches someone, so it asks first
# ============================================================================

send_mailbox_draft_catalogue_manifest = ToolManifest(
    name="send_mailbox_draft_tool",
    agent="email_agent",
    description=(
        "**Tool: send_mailbox_draft_tool** - SEND a draft of the person's mailbox. "
        "**REQUIRES HITL**: the person sees the draft as the mailbox holds it and confirms, "
        "edits or cancels.\n"
        "- One draft per call: several drafts ('send all my drafts') → for_each over "
        "list_mailbox_drafts_tool's `emails`\n"
        "- A draft with no recipient is refused: add one with update_mailbox_draft_tool first\n"
        "**RETURNS**: the confirmation; once confirmed, the draft leaves as it was shown."
    ),
    mutation_policy="draft",
    semantic_keywords=[
        "send my draft email",
        "send the draft I prepared for Marie",
        "send all my drafts",
        "send the last draft now",
    ],
    parameters=[_EXISTING_DRAFT],
    outputs=[
        # Untyped on purpose: Outlook and iCloud name no sent message.
        OutputFieldSchema(path="message_id", type="string", description="The sent message"),
    ],
    cost=CostProfile(
        est_tokens_in=150, est_tokens_out=100, est_cost_usd=0.002, est_latency_ms=1000
    ),
    # The confirmation is the draft card itself (draft critique), never a second gate.
    permissions=_DRAFT_PERMISSIONS,
    reference_examples=["message_id"],
    display=DisplayMetadata(
        emoji="📤", i18n_key="send_mailbox_draft", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

# The mailbox draft family — loop-registered by the catalogue loader.
MAILBOX_DRAFT_TOOL_MANIFESTS: tuple[ToolManifest, ...] = (
    list_mailbox_drafts_catalogue_manifest,
    create_mailbox_draft_catalogue_manifest,
    create_mailbox_reply_draft_catalogue_manifest,
    create_mailbox_forward_draft_catalogue_manifest,
    update_mailbox_draft_catalogue_manifest,
    delete_mailbox_drafts_catalogue_manifest,
    send_mailbox_draft_catalogue_manifest,
)


__all__ = [
    "DELETE_MAX_RESULTS_DESCRIPTION",
    "LIST_MAX_RESULTS_DESCRIPTION",
    "MAILBOX_DRAFT_ID_TYPE",
    "MAILBOX_DRAFT_TOOL_MANIFESTS",
    "create_mailbox_draft_catalogue_manifest",
    "create_mailbox_forward_draft_catalogue_manifest",
    "create_mailbox_reply_draft_catalogue_manifest",
    "delete_mailbox_drafts_catalogue_manifest",
    "list_mailbox_drafts_catalogue_manifest",
    "send_mailbox_draft_catalogue_manifest",
    "update_mailbox_draft_catalogue_manifest",
]
