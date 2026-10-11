"""Catalogue contracts for Gmail labels, distinct ids and human-readable names.

Re-exported by catalogue_manifests for the unchanged registration interface.
"""

from src.core.constants import GOOGLE_GMAIL_SCOPES
from src.domains.agents.registry.catalogue import (
    REASON_ADDITIVE_METADATA,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
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
            semantic_type="email_label",
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
        OutputFieldSchema(
            path="labels[].id",
            type="string",
            description="Label ID",
            semantic_type="email_label_id",
        ),
        OutputFieldSchema(
            path="labels[].name",
            type="string",
            description="Label name (path)",
            semantic_type="email_label",
        ),
        OutputFieldSchema(path="total_user_labels", type="integer", description="Total count"),
        # `name_filter` is echoed back by the client ONLY when the call carried
        # one (the tool passes the client result through as structured_data).
        # A conditional field cannot be advertised as a reference path: the
        # planner would emit `$steps.X.name_filter` and the unfiltered call —
        # the common one — resolves nothing. Published means produced, every time.
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
    initiative_eligible=False,  # Structural tool, not useful for proactive enrichment
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
    mutation_policy="draft",
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
            semantic_type="email_label",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="label", type="object", description="Created label"),
        OutputFieldSchema(
            path="label.id", type="string", description="Label ID", semantic_type="email_label_id"
        ),
        OutputFieldSchema(
            path="label.name", type="string", description="Label name", semantic_type="email_label"
        ),
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
    mutation_policy="draft",
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
            semantic_type="email_label",
        ),
        ParameterSchema(
            name="new_name",
            type="string",
            required=True,
            description="New label name",
            semantic_type="email_label",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(
            path="old_name", type="string", description="Previous name", semantic_type="email_label"
        ),
        OutputFieldSchema(
            path="new_name", type="string", description="New name", semantic_type="email_label"
        ),
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
    mutation_policy="draft",
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
            semantic_type="email_label",
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
        # Draft-based: delete_label_tool returns requires_confirmation=True
        # (label_delete draft) → draft_critique. hitl_required stays False (see
        # test_hitl_required_consistency.py). Note: delete_label_direct_tool is a
        # separate, internal, non-draft variant.
        required_scopes=GOOGLE_GMAIL_SCOPES,
        hitl_required=False,
        data_classification="INTERNAL",
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
    mutation_policy="reversible",
    mutation_policy_reason=REASON_ADDITIVE_METADATA,
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
            semantic_type="email_label",
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
            semantic_type="message_id",
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
        OutputFieldSchema(
            path="labels_applied",
            type="array",
            description="Labels applied",
            semantic_type="email_label",
        ),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=100, est_cost_usd=0.002, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_GMAIL_SCOPES, hitl_required=False, data_classification="INTERNAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["message_count", "labels_applied"],
    # Declared explicitly: the name carries no CRUD verb, so category inference
    # defaulted it to "readonly" — which made this Gmail label MUTATION eligible
    # for proactive execution by the initiative node and invisible to the
    # invalid-mutation-plan safety net. Mirrors remove_labels_tool ("delete").
    tool_category="update",
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
    mutation_policy="reversible",
    mutation_policy_reason=REASON_ADDITIVE_METADATA,
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
            semantic_type="email_label",
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
            semantic_type="message_id",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="message_count", type="integer", description="Emails modified"),
        OutputFieldSchema(
            path="labels_removed",
            type="array",
            description="Labels removed",
            semantic_type="email_label",
        ),
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
