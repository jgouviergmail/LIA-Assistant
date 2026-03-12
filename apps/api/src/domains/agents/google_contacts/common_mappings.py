"""
Common field mappings for Google Contacts tools.

This module provides reusable field mapping dictionaries to avoid duplication
across multiple Google Contacts tool manifests.

Phase 4 refactoring: Extracted from catalogue_manifests.py to eliminate
~150 lines of duplicated code across search/list/get_details manifests.

Phase: Extended Contact Details Support - Added all Google People API v1 fields
Reference: https://developers.google.com/people/api/rest/v1/people
"""

# Standard Google Contacts field mappings
# Maps user-friendly field names to Google People API field mask paths
# Organized by logical groups for maintainability
GOOGLE_CONTACTS_FIELD_MAPPINGS: dict[str, str] = {
    # ===== GROUP 1: IDENTITY & NAMES =====
    "name": "names",
    "names": "names",
    "nickname": "nicknames",
    "nicknames": "nicknames",
    # ===== GROUP 2: CONTACT INFORMATION =====
    "email": "emailAddresses",
    "emails": "emailAddresses",
    "emailAddresses": "emailAddresses",
    "phone": "phoneNumbers",
    "phones": "phoneNumbers",
    "phoneNumbers": "phoneNumbers",
    "address": "addresses",
    "addresses": "addresses",
    # ===== GROUP 3: PERSONAL INFORMATION =====
    "biography": "biographies",
    "biographies": "biographies",
    "bio": "biographies",
    "birthday": "birthdays",
    "birthdays": "birthdays",
    "photo": "photos",
    "photos": "photos",
    # ===== GROUP 4: PROFESSIONAL INFORMATION =====
    "organization": "organizations",
    "organizations": "organizations",
    "occupation": "occupations",
    "occupations": "occupations",
    "skill": "skills",
    "skills": "skills",
    # ===== GROUP 5: SOCIAL & RELATIONSHIPS =====
    "relation": "relations",
    "relations": "relations",
    "interest": "interests",
    "interests": "interests",
    "event": "events",
    "events": "events",
    # ===== GROUP 6: LINKS & COMMUNICATION =====
    "calendarUrl": "calendarUrls",
    "calendarUrls": "calendarUrls",
    "imClient": "imClients",
    "imClients": "imClients",
    "im": "imClients",
    # ===== GROUP 7: METADATA & CUSTOM DATA =====
    "metadata": "metadata",
    "location": "locations",
    "locations": "locations",
}


def get_contacts_field_mappings() -> dict[str, str]:
    """
    Get standard Google Contacts field mappings.

    Returns a copy to prevent accidental mutations.

    Returns:
        Dictionary mapping user-friendly field names to Google API field masks.

    Example:
        >>> mappings = get_contacts_field_mappings()
        >>> mappings["email"]
        'emailAddresses'
    """
    return GOOGLE_CONTACTS_FIELD_MAPPINGS.copy()
