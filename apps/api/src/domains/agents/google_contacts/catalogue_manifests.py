"""
Catalogue manifests for Google Contacts tools.
Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_contacts_tool replaces search_contacts_tool + list_contacts_tool + get_contact_details_tool
- Always returns full contact content (all fields)
- Supports query mode (search) OR ID mode (direct fetch)
"""

from src.core.config import settings
from src.core.constants import GOOGLE_CONTACTS_SCOPES
from src.core.field_names import FIELD_QUERY, FIELD_RESOURCE_NAME
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.google_contacts.common_mappings import get_contacts_field_mappings
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
# 1. GET CONTACTS (Unified - replaces search + list + details)
# ============================================================================
_get_contacts_desc = (
    "**Tool: get_contacts_tool** - Get contacts with full details.\n"
    "\n"
    "**MODES**:\n"
    "- Query mode: get_contacts_tool(query='John') → search + return full details\n"
    "- ID mode: get_contacts_tool(resource_name='people/c123') → fetch specific contact\n"
    "- Batch mode: get_contacts_tool(resource_names=['people/c1', 'people/c2']) → fetch multiple\n"
    "- List mode: get_contacts_tool() → return recent contacts with full details\n"
    "\n"
    "**SEARCHABLE FIELDS** (query parameter):\n"
    "- names, family names, emails, phone numbers, organizations ONLY\n"
    "- Other fields (addresses, cities, regions): Response LLM filters results\n"
    "- Example: 'Dupont in Lyon' → query='Dupont'\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'find John' → query='John'\n"
    "- 'who is 06...' → query='06...'\n"
    "- 'show my contacts' → query='' (empty, returns all)\n"
    "- 'details of this contact' → resource_name='ID from context'\n"
    "\n"
    "**RETURNS**: Full contact info (names, emails, phones, addresses, organizations, etc.)."
)

get_contacts_catalogue_manifest = ToolManifest(
    name="get_contacts_tool",
    agent="contact_agent",
    description=_get_contacts_desc,
    # Discriminant phrases - Personal contact operations
    semantic_keywords=[
        # Contact lookup by identifier
        "find person in my address book by name",
        "lookup contact phone number from contacts",
        "get email address of someone I know",
        "who is this person in my contacts",
        # Contact search
        "search my personal contacts for someone",
        "find contact by phone number reverse lookup",
        "whose email address is this in contacts",
        "person named in my address book",
        # Contact listing
        "show all contacts in my address book",
        "list people in my personal contacts",
        "browse my saved contact entries",
        # Contact details
        "full details of contact from address book",
        "home address of person in my contacts",
        "birthday and organization of contact",
        "complete profile of someone I know",
        # Family and groups
        "family members in my contacts list",
        "colleagues saved in address book",
        "all relatives contact information",
    ],
    parameters=[
        # Query mode parameter
        ParameterSchema(
            name=FIELD_QUERY,
            type="string",
            required=False,
            description="Query (name, email, phone). Optional - empty for all contacts.",
            constraints=[],
        ),
        # ID mode parameters
        ParameterSchema(
            name=FIELD_RESOURCE_NAME,
            type="string",
            required=False,
            description="Single contact ID (people/c...) for direct fetch.",
            constraints=[ParameterConstraint(kind="pattern", value=r"^people/")],
        ),
        ParameterSchema(
            name="resource_names",
            type="array",
            required=False,
            description="Multiple contact IDs (people/c...) for batch fetch. NOT for names - use query parameter to search by name.",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max results (def: {settings.contacts_tool_default_limit}, max: {settings.contacts_tool_default_max_results})",
            constraints=[
                ParameterConstraint(
                    kind="maximum", value=settings.contacts_tool_default_max_results
                )
            ],
        ),
    ],
    outputs=[
        # Full contact outputs (merged from all tools)
        OutputFieldSchema(
            path="contacts", type="array", description="List of contacts with full details"
        ),
        OutputFieldSchema(
            path="contacts[].resource_name", type="string", description="Contact ID (people/...)"
        ),
        OutputFieldSchema(
            path="contacts[].name",
            type="string",
            description="Full Name",
            semantic_type="person_name",  # For cross-domain: can identify a person
        ),
        OutputFieldSchema(
            path="contacts[].emailAddresses",
            type="array",
            description="Email addresses (Google API format)",
        ),
        OutputFieldSchema(
            path="contacts[].emailAddresses[].value",
            type="string",
            description="Email address value",
            semantic_type="email_address",  # For cross-domain: can send emails, invite attendees
        ),
        OutputFieldSchema(
            path="contacts[].phoneNumbers",
            type="array",
            description="Phone numbers (Google API format)",
        ),
        OutputFieldSchema(
            path="contacts[].phoneNumbers[].value",
            type="string",
            description="Phone number value",
            semantic_type="phone_number",  # For cross-domain: can call/SMS
        ),
        OutputFieldSchema(
            path="contacts[].addresses", type="array", description="Physical addresses"
        ),
        OutputFieldSchema(
            path="contacts[].addresses[].formattedValue",
            type="string",
            description="Full formatted postal address (street, city, postal code, country)",
            semantic_type="physical_address",  # For cross-domain: routes.destination, places
        ),
        OutputFieldSchema(
            path="contacts[].organizations", type="array", description="Organizations"
        ),
        OutputFieldSchema(path="contacts[].birthdays", type="array", description="Birthdays"),
        OutputFieldSchema(
            path="contacts[].biographies", type="array", description="Biographies/Notes"
        ),
        OutputFieldSchema(path="total", type="integer", description="Total count"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=900, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    reference_fields=["resource_name", "name", "emailAddresses", "phoneNumbers", "addresses"],
    context_key="contacts",
    context_save_mode=ContextSaveMode.LIST,
    field_mappings=get_contacts_field_mappings(),
    reference_examples=[
        "contacts[0].resource_name",
        "contacts[0].name",
        "contacts[0].emailAddresses[0].value",
        "contacts[0].phoneNumbers[0].value",
        "contacts[0].addresses[0].formattedValue",  # physical_address for routes
        "total",
    ],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="👤", i18n_key="get_contacts", visible=True, category="tool"),
)


# ============================================================================
# 2. CREATE CONTACT
# ============================================================================
_create_desc = "**Tool: create_contact_tool** - Create new contact. **REQUIRES HITL**."
create_contact_catalogue_manifest = ToolManifest(
    name="create_contact_tool",
    agent="contact_agent",
    description=_create_desc,
    semantic_keywords=[
        "create new entry in my address book",
        "add person to my personal contacts",
        "save phone number to contacts list",
        "store email address in address book",
        "add someone new to my contacts",
    ],
    parameters=[
        ParameterSchema(
            name="name",
            type="string",
            required=True,
            description="Full Name",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        ),
        ParameterSchema(name="email", type="string", required=False, description="Email"),
        ParameterSchema(name="phone", type="string", required=False, description="Phone"),
        ParameterSchema(name="organization", type="string", required=False, description="Company"),
        ParameterSchema(name="notes", type="string", required=False, description="Notes"),
    ],
    outputs=[
        OutputFieldSchema(path="resource_name", type="string", description="Created ID"),
        OutputFieldSchema(path="name", type="string", description="Name"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=100, est_cost_usd=0.005, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before creation)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="contacts",
    field_mappings=get_contacts_field_mappings(),
    reference_examples=["resource_name", "name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="➕", i18n_key="create_contact", visible=True, category="tool"),
)

# ============================================================================
# 5. UPDATE CONTACT
# ============================================================================
_update_desc = "**Tool: update_contact_tool** - Update existing contact (name, email, phone, address, etc.). **REQUIRES HITL**."
update_contact_catalogue_manifest = ToolManifest(
    name="update_contact_tool",
    agent="contact_agent",
    description=_update_desc,
    semantic_keywords=[
        "update contact details in address book",
        "edit phone number of existing contact",
        "change email address in my contacts",
        "modify contact information entry",
        "correct address of person in contacts",
    ],
    parameters=[
        ParameterSchema(
            name="resource_name",
            type="string",
            required=True,
            description="ID (people/c...)",
            constraints=[ParameterConstraint(kind="pattern", value=r"^people/")],
        ),
        ParameterSchema(name="name", type="string", required=False, description="New Name"),
        ParameterSchema(name="email", type="string", required=False, description="New Email"),
        ParameterSchema(name="phone", type="string", required=False, description="New Phone"),
        ParameterSchema(name="organization", type="string", required=False, description="New Org"),
        ParameterSchema(name="notes", type="string", required=False, description="New Notes"),
        ParameterSchema(
            name="address",
            type="string",
            required=False,
            description="New Address (e.g. '15 rue de la Paix, Paris 75001')",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="resource_name", type="string", description="ID"),
        OutputFieldSchema(path="name", type="string", description="Name"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=100, est_cost_usd=0.005, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before modification)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="contacts",
    field_mappings=get_contacts_field_mappings(),
    reference_examples=["resource_name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="✏️", i18n_key="update_contact", visible=True, category="tool"),
)

# ============================================================================
# 6. DELETE CONTACT
# ============================================================================
_delete_desc = "**Tool: delete_contact_tool** - Delete contact. **REQUIRES HITL**. Irreversible."
delete_contact_catalogue_manifest = ToolManifest(
    name="delete_contact_tool",
    agent="contact_agent",
    description=_delete_desc,
    semantic_keywords=[
        "delete contact from my address book",
        "remove person from contacts list",
        "erase contact entry permanently",
        "clean up old contacts from address book",
    ],
    parameters=[
        ParameterSchema(
            name="resource_name",
            type="string",
            required=True,
            description="ID to delete",
            constraints=[ParameterConstraint(kind="pattern", value=r"^people/")],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="resource_name", type="string", description="Deleted ID"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=50, est_cost_usd=0.003, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CONTACTS_SCOPES,
        # hitl_required=False: HITL is handled by draft_critique (preview before deletion)
        # Avoids double HITL: approval_gate (plan) + draft_critique (content)
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    context_key="contacts",
    field_mappings=get_contacts_field_mappings(),
    reference_examples=["success", "resource_name"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_contact", visible=True, category="tool"),
)

__all__ = [
    # Unified tool (v2.0 - replaces search + list + details)
    "get_contacts_catalogue_manifest",
    # Action tools
    "create_contact_catalogue_manifest",
    "update_contact_catalogue_manifest",
    "delete_contact_catalogue_manifest",
]
