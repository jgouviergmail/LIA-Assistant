"""Verified Google contact group contracts, re-exported by the native catalogue."""

from src.core.constants import GOOGLE_CONTACTS_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

list_contact_groups_catalogue_manifest = ToolManifest(
    name="list_contact_groups_tool",
    agent="contact_agent",
    description=(
        "**Tool: list_contact_groups_tool** - List the user's contact groups "
        "(family, colleagues, clients, ...) with EXACT member counts. "
        "Google Contacts only (clear unsupported message otherwise)."
    ),
    semantic_keywords=[
        "list my contact groups labels",
        "what groups of contacts do I have",
        "show my family colleagues contact groups",
        "contact group members count",
    ],
    parameters=[],
    outputs=[
        OutputFieldSchema(path="groups", type="array", description="User-defined groups"),
        OutputFieldSchema(
            path="groups[].name", type="string", description="Group name", semantic_type="Text"
        ),
        OutputFieldSchema(
            path="groups[].member_count",
            type="integer",
            description="Exact member count (API aggregate)",
        ),
        OutputFieldSchema(path="total", type="integer", description="Number of groups"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=150, est_cost_usd=0.002, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    # Groups are plain structured data (no registry items) — reuse the
    # registered "contacts" context type rather than inventing a new one.
    context_key="contacts",
    reference_examples=["groups[0].name", "groups[0].member_count", "total"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="👥", i18n_key="list_contact_groups", visible=True, category="tool"
    ),
)

get_contact_group_members_catalogue_manifest = ToolManifest(
    name="get_contact_group_members_tool",
    agent="contact_agent",
    description=(
        "**Tool: get_contact_group_members_tool** - Get the members of one "
        "contact group with their email addresses. Use BEFORE sending an "
        "email to a whole group ('send this to my family group'): the member "
        "emails feed the email tool recipients. Google Contacts only."
    ),
    semantic_keywords=[
        "send email to my family contact group",
        "who is in my colleagues group",
        "members of a contact group with emails",
        "email everyone in a group of contacts",
    ],
    parameters=[
        ParameterSchema(
            name="group_name",
            type="string",
            required=True,
            description=(
                "Group name as the user says it (e.g. 'famille'). "
                "Matched case-insensitively against the user's groups."
            ),
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="group", type="object", description="Resolved group"),
        OutputFieldSchema(
            path="group.name",
            type="string",
            description="Resolved group name",
            semantic_type="Text",
        ),
        OutputFieldSchema(path="members", type="array", description="Members"),
        OutputFieldSchema(
            path="members[].name",
            type="string",
            description="Member name",
            semantic_type="person_name",
        ),
        OutputFieldSchema(
            path="members[].emails",
            type="array",
            description="Member email addresses",
            semantic_type="email_address",  # Cross-domain: feeds email recipients
        ),
        OutputFieldSchema(path="total", type="integer", description="Member count"),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=300, est_cost_usd=0.004, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="contacts",
    reference_examples=["members[0].emails", "members[0].name", "total"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="👥", i18n_key="get_contact_group_members", visible=True, category="tool"
    ),
)
