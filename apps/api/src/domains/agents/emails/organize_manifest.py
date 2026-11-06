"""Catalogue manifests of the mail-sorting tools (ADR-369, lot 4, owner decision D2).

Beside ``catalogue_manifests.py`` because that module is at its size cap (the
``attachment_manifest.py`` precedent). What they publish is what the tools enforce
(ADR-184): the bound and the actions are written ONCE, in the words both the planner's
manifest and the ReAct tool schema read (ADR-310).
"""

from typing import Final

from src.core.constants import EMAIL_ORGANIZE_MAX_MESSAGES, GOOGLE_GMAIL_SCOPES
from src.domains.agents.registry.catalogue import (
    REASON_UNDONE_BY_ONE_CALL,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

#: What a message can be asked to do. Deleting for good is no action here (A2): it stays
#: by the person's own hand, behind a confirmation; ``delete_email_tool`` trashes.
ORGANIZE_ACTIONS: Final = ("archive", "move", "spam", "not_spam", "restore", "star", "unstar")
#: What a folder of the person's own can be asked to do.
MAIL_FOLDER_ACTIONS: Final = ("create", "rename", "delete")

#: The message selection's wording, read by the manifest AND the tool's schema.
ORGANIZE_IDS_DESCRIPTION: Final = (
    "The messages' ids (from get_emails_tool or CONTEXT), at most "
    f"{EMAIL_ORGANIZE_MAX_MESSAGES} per call: `more_remaining` says whether some were left."
)
ORGANIZE_ACTION_DESCRIPTION: Final = (
    "archive; move (needs `folder`); spam; not_spam (back to the inbox); restore (out of "
    "the trash, to the inbox); star; unstar."
)
ORGANIZE_FOLDER_DESCRIPTION: Final = (
    "For `move`: the folder or label, by its name or its full path."
)
MAIL_FOLDER_ACTION_DESCRIPTION: Final = (
    "create (needs `name`; « / » nests it); rename (needs `folder` and `name`); delete (needs "
    "`folder`: a folder holding messages or folders is refused)."
)
MAIL_FOLDER_FOLDER_DESCRIPTION: Final = "The folder, by its name or its full path."
MAIL_FOLDER_NAME_DESCRIPTION: Final = (
    "For create: the new folder's name or path. For rename: its new own name, never a path."
)

organize_emails_catalogue_manifest = ToolManifest(
    name="organize_emails_tool",
    agent="email_agent",
    description=(
        "**Tool: organize_emails_tool** - Sort e-mails of the person's mailbox (Gmail, Outlook "
        "or iCloud): archive them, move them to a folder or label, report them as spam or not, "
        "restore them from the trash, star them. Asks no confirmation.\n"
        "- 'archive this email', 'move the invoices to the Accounting folder', 'star that mail'\n"
        "- The ids come from get_emails_tool or CONTEXT; a search is never done here\n"
        "- To put e-mails in the trash, use delete_email_tool\n"
        "**RETURNS**: `updated` the ids done, `failed` each one not done and why, `moved` what "
        "each message is called from now on (a move changes an id on Outlook and iCloud: name "
        "them by it in a later call), `more_remaining`."
    ),
    # A state change on existing messages: a mutation (no naming convention says so).
    tool_category="update",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    semantic_keywords=[
        "archive this email",
        "move these messages to the folder",
        "put this email in the Invoices folder",
        "this message is spam",
        "this email is not spam",
        "restore the email from the trash",
        "star this message",
        "remove the star from this email",
    ],
    parameters=[
        ParameterSchema(
            name="action",
            type="string",
            required=True,
            description=ORGANIZE_ACTION_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(ORGANIZE_ACTIONS))],
        ),
        ParameterSchema(
            name="message_ids",
            type="array",
            required=True,
            description=ORGANIZE_IDS_DESCRIPTION,
            semantic_type="message_id",
        ),
        ParameterSchema(
            name="folder",
            type="string",
            required=False,
            description=ORGANIZE_FOLDER_DESCRIPTION,
        ),
    ],
    outputs=[
        OutputFieldSchema(path="updated", type="array", description="The ids done"),
        OutputFieldSchema(path="failed", type="array", description="Ids not done, and why"),
        OutputFieldSchema(path="moved", type="object", description="Each id, and its id now"),
        OutputFieldSchema(
            path="more_remaining", type="boolean", description="Whether ids were left"
        ),
    ],
    cost=CostProfile(est_tokens_in=90, est_tokens_out=90, est_cost_usd=0.0, est_latency_ms=1000),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    reference_examples=["updated", "failed", "moved", "more_remaining"],
    display=DisplayMetadata(emoji="🗂️", i18n_key="organize_emails", visible=True, category="tool"),
    version="1.0.0",
    maintainer="Team Agents",
)

manage_mail_folder_catalogue_manifest = ToolManifest(
    name="manage_mail_folder_tool",
    agent="email_agent",
    description=(
        "**Tool: manage_mail_folder_tool** - Create, rename or delete a folder of the person's "
        "own on Outlook or iCloud. Gmail has labels: use create_label_tool, update_label_tool "
        "and delete_label_tool there. Asks no confirmation: a folder holding messages or "
        "folders is never deleted.\n"
        "- 'create a Clients folder', 'rename the folder Old to Archive 2025'\n"
        "**RETURNS**: `folder`, what the folder is called from now on."
    ),
    tool_category="update",
    mutation_policy="reversible",
    mutation_policy_reason=REASON_UNDONE_BY_ONE_CALL,
    semantic_keywords=[
        "create a mail folder",
        "new folder in my mailbox",
        "rename this mail folder",
        "delete this empty mail folder",
    ],
    parameters=[
        ParameterSchema(
            name="action",
            type="string",
            required=True,
            description=MAIL_FOLDER_ACTION_DESCRIPTION,
            constraints=[ParameterConstraint(kind="enum", value=list(MAIL_FOLDER_ACTIONS))],
        ),
        ParameterSchema(
            name="folder",
            type="string",
            required=False,
            description=MAIL_FOLDER_FOLDER_DESCRIPTION,
        ),
        ParameterSchema(
            name="name",
            type="string",
            required=False,
            description=MAIL_FOLDER_NAME_DESCRIPTION,
        ),
    ],
    outputs=[
        OutputFieldSchema(path="folder", type="string", description="The folder, as it is now"),
    ],
    cost=CostProfile(est_tokens_in=70, est_tokens_out=40, est_cost_usd=0.0, est_latency_ms=900),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    reference_examples=["folder"],
    display=DisplayMetadata(
        emoji="📁", i18n_key="manage_mail_folder", visible=True, category="tool"
    ),
    version="1.0.0",
    maintainer="Team Agents",
)

__all__ = [
    "MAIL_FOLDER_ACTIONS",
    "MAIL_FOLDER_ACTION_DESCRIPTION",
    "MAIL_FOLDER_FOLDER_DESCRIPTION",
    "MAIL_FOLDER_NAME_DESCRIPTION",
    "ORGANIZE_ACTIONS",
    "ORGANIZE_ACTION_DESCRIPTION",
    "ORGANIZE_FOLDER_DESCRIPTION",
    "ORGANIZE_IDS_DESCRIPTION",
    "manage_mail_folder_catalogue_manifest",
    "organize_emails_catalogue_manifest",
]
