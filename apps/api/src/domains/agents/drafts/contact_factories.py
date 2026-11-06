"""The contact draft factories — moved out of drafts/service.py (ADR-369, lot 9).

``service.py`` is frozen at its audited size: what the drafts gained is paid for by moving this
cohesive group out, never by a raised cap. Re-exported by the package, where every caller reads
them.
"""

from typing import Any

from src.core.i18n import resolve_language
from src.domains.agents.drafts.models import (
    ContactDeleteDraftInput,
    ContactDraftInput,
    ContactUpdateDraftInput,
)
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.google_contacts.extras import ContactExtras
from src.domains.agents.tools.output import UnifiedToolOutput


def create_contact_draft(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    extras: ContactExtras | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "create_contact_tool",
    user_language: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact draft.

    Args:
        name: Contact name
        email: Contact email
        phone: Contact phone
        organization: Company name
        notes: Additional notes
        extras: What it holds beyond these
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    kept = extras or ContactExtras()
    draft_input = ContactDraftInput(
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        given_name=kept.given_name,
        family_name=kept.family_name,
        job_title=kept.job_title,
        website=kept.website,
        birthday=kept.birthday,
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_contact_draft(draft_input, source_tool=source_tool)


def create_contact_update_draft(
    resource_name: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
    current_contact: dict[str, Any] | None = None,
    extras: ContactExtras | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "update_contact_tool",
    user_language: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact update draft.

    Args:
        resource_name: Contact resource name (people/c...)
        name: New contact name (optional)
        email: New contact email (optional)
        phone: New contact phone (optional)
        organization: New company name (optional)
        notes: New notes (optional)
        address: New address (optional, e.g. '15 rue de la Paix, Paris 75001')
        current_contact: Current contact data for comparison
        extras: What changes beyond these
        related_registry_ids: Related registry items
        source_tool: Source tool name
        user_language: Language for HITL

    Returns:
        UnifiedToolOutput with draft
    """
    service = DraftService()
    draft_input = ContactUpdateDraftInput(
        **(extras or ContactExtras()).fields(),
        resource_name=resource_name,
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        address=address,
        current_contact=current_contact or {},
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_contact_update_draft(draft_input, source_tool=source_tool)


def create_contact_delete_draft(
    resource_name: str,
    current_contact: dict[str, Any] | None = None,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
    related_registry_ids: list[str] | None = None,
    source_tool: str = "delete_contact_tool",
    user_language: str | None = None,
) -> UnifiedToolOutput:
    """
    Convenience function to create a contact delete draft.

    Homogenized with create_contact_update_draft for draft type changes.

    Args:
        resource_name: Contact resource name (people/c...).
        current_contact: Full contact object for display and type change.
        name: Contact name.
        email: Contact email.
        phone: Contact phone.
        organization: Company name.
        notes: Notes.
        address: Address.
        related_registry_ids: Related registry items.
        source_tool: Source tool name.
        user_language: Language for HITL.

    Returns:
        UnifiedToolOutput with draft.
    """
    service = DraftService()
    draft_input = ContactDeleteDraftInput(
        resource_name=resource_name,
        current_contact=current_contact or {},
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        address=address,
        related_registry_ids=related_registry_ids or [],
        user_language=resolve_language(user_language),
    )
    return service.create_contact_delete_draft(draft_input, source_tool=source_tool)
