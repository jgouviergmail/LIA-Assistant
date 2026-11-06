"""What a confirmed contact draft does (LOT 5.4) — moved out of google_contacts_tools.py.

The three executors a confirmed create, update or delete draft runs, and the helper only they
read. Their own module since ADR-369 lot 9: ``google_contacts_tools.py`` is frozen at its audited
size, and the fields a contact gained had to be paid for by a cohesive move rather than a raised
cap. Google, Microsoft and Apple alike, through dynamic provider resolution.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.tools.contact_extras import details_of

logger = structlog.get_logger(__name__)


def _build_contact_url(resource_name: str | None) -> str | None:
    """
    Build Google Contacts URL from resource_name.

    Google Contacts URL format: https://contacts.google.com/person/{person_id}
    resource_name format: people/c{person_id} (e.g., people/c6737050419687533025)

    Args:
        resource_name: Contact resource name (e.g., "people/c6737050419687533025")

    Returns:
        Google Contacts URL or None if resource_name is invalid

    Example:
        >>> _build_contact_url("people/c6737050419687533025")
        "https://contacts.google.com/person/c6737050419687533025"
    """
    if not resource_name:
        return None

    # Extract person_id from resource_name
    # Format: people/{person_id} where person_id starts with 'c'
    if resource_name.startswith("people/"):
        person_id = resource_name.replace("people/", "")
        return f"https://contacts.google.com/person/{person_id}"

    return None


async def execute_contact_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact draft: actually create the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    This is the execute_fn passed to DraftService.process_draft_action().
    It retrieves the Google People client and creates the contact.

    Args:
        draft_content: Dict with contact content from draft
            {name, email, phone, organization, notes, and what ``details_of`` reads}
        user_id: User UUID
        deps: ToolDependencies for getting Google People client

    Returns:
        Dict with create result:
            {success, resource_name, name, email, message}

    Raises:
        Exception: If contact creation fails
    """
    # Get contacts client via dynamic provider resolution
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    # Create contact
    result = await client.create_contact(
        name=draft_content["name"],
        email=draft_content.get("email"),
        phone=draft_content.get("phone"),
        organization=draft_content.get("organization"),
        notes=draft_content.get("notes"),
        details=details_of(draft_content),
    )

    logger.info(
        "contact_draft_executed",
        user_id=str(user_id),
        resource_name=result.get("resourceName"),
    )

    resource_name = result.get("resourceName")
    html_link = _build_contact_url(resource_name)

    return {
        "success": True,
        "resource_name": resource_name,
        "html_link": html_link,
        "name": draft_content["name"],
        "email": draft_content.get("email"),
        "message": APIMessages.contact_created_successfully(draft_content["name"]),
    }


async def execute_contact_update_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact update draft: actually update the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    result = await client.update_contact(
        resource_name=draft_content["resource_name"],
        name=draft_content.get("name"),
        email=draft_content.get("email"),
        phone=draft_content.get("phone"),
        organization=draft_content.get("organization"),
        notes=draft_content.get("notes"),
        address=draft_content.get("address"),
        details=details_of(draft_content),
    )

    # Get display name
    names = result.get("names", [])
    display_name = names[0].get("displayName") if names else draft_content.get("name", "Contact")

    resource_name = draft_content["resource_name"]
    html_link = _build_contact_url(resource_name)

    logger.info(
        "contact_update_draft_executed",
        user_id=str(user_id),
        resource_name=resource_name,
    )

    return {
        "success": True,
        "resource_name": resource_name,
        "html_link": html_link,
        "name": display_name,
        "message": APIMessages.contact_updated_successfully(display_name),
    }


async def execute_contact_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact delete draft: actually delete the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    await client.delete_contact(draft_content["resource_name"])

    # Get name from contact data if available
    contact = draft_content.get("current_contact", {})
    names = contact.get("names", [])
    display_name = names[0].get("displayName") if names else ""

    logger.info(
        "contact_delete_draft_executed",
        user_id=str(user_id),
        resource_name=draft_content["resource_name"],
    )

    return {
        "success": True,
        "resource_name": draft_content["resource_name"],
        "name": display_name,
        "message": APIMessages.contact_deleted_successfully(display_name),
    }
