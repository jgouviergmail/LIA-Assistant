"""
Contacts normalizer: Microsoft Graph contact → dict format Google People API.

Converts Microsoft Graph API contact objects to the dict structure
expected by contacts_tools.py (same format as GooglePeopleClient).
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def normalize_graph_contact(contact: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a Microsoft Graph contact to Google People API dict format.

    Args:
        contact: Microsoft Graph contact dict from /me/contacts.

    Returns:
        Dict in Google People API person format with _provider marker.
    """
    contact_id = contact.get("id", "")
    display_name = contact.get("displayName", "")

    # Names
    names = []
    if display_name:
        names.append(
            {
                "displayName": display_name,
                "givenName": contact.get("givenName", ""),
                "familyName": contact.get("surname", ""),
                "middleName": contact.get("middleName", ""),
            }
        )

    # Email addresses (filter out Exchange X500 addresses like
    # "/o=First Organization/ou=Exchange Administrative Group...")
    email_addresses = []
    for email in contact.get("emailAddresses", []):
        addr = email.get("address", "")
        if addr and not addr.startswith("/"):
            email_addresses.append(
                {
                    "value": addr,
                    "type": email.get("name", "other").lower() if email.get("name") else "other",
                }
            )

    # Phone numbers
    phone_numbers = _extract_phones(contact)

    # Organizations
    organizations = []
    company = contact.get("companyName", "")
    job_title = contact.get("jobTitle", "")
    department = contact.get("department", "")
    if company or job_title:
        organizations.append(
            {
                "name": company,
                "title": job_title,
                "department": department,
            }
        )

    # Addresses
    addresses = _extract_addresses(contact)

    # Birthday
    birthdays = []
    birthday_str = contact.get("birthday")
    if birthday_str:
        birthday = _parse_birthday(birthday_str)
        if birthday:
            birthdays.append({"date": birthday})

    # Notes
    notes = contact.get("personalNotes", "")

    # Photos
    photos = []
    if contact.get("photo"):
        photos.append({"url": f"/me/contacts/{contact_id}/photo/$value"})

    return {
        "resourceName": f"people/{contact_id}",
        "etag": contact.get("@odata.etag", ""),
        "names": names,
        "emailAddresses": email_addresses,
        "phoneNumbers": phone_numbers,
        "organizations": organizations,
        "addresses": addresses,
        "birthdays": birthdays,
        "biographies": [{"value": notes}] if notes else [],
        "photos": photos,
        "_provider": "microsoft",
    }


def _extract_phones(contact: dict[str, Any]) -> list[dict[str, str]]:
    """Extract and normalize phone numbers from Microsoft Graph contact."""
    phones: list[dict[str, str]] = []

    phone_fields = [
        ("homePhones", "home"),
        ("businessPhones", "work"),
        ("mobilePhone", "mobile"),
    ]

    for field, phone_type in phone_fields:
        value = contact.get(field)
        if isinstance(value, list):
            for phone in value:
                if phone:
                    phones.append({"value": phone, "type": phone_type})
        elif isinstance(value, str) and value:
            phones.append({"value": value, "type": phone_type})

    return phones


def _extract_addresses(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and normalize addresses from Microsoft Graph contact."""
    addresses: list[dict[str, Any]] = []

    address_fields = [
        ("homeAddress", "home"),
        ("businessAddress", "work"),
        ("otherAddress", "other"),
    ]

    for field, addr_type in address_fields:
        addr = contact.get(field)
        if addr and any(addr.values()):
            street = addr.get("street", "")
            city = addr.get("city", "")
            state = addr.get("state", "")
            postal_code = addr.get("postalCode", "")
            country = addr.get("countryOrRegion", "")

            # Build formatted value
            parts = [p for p in [street, city, state, postal_code, country] if p]
            formatted = ", ".join(parts)

            addresses.append(
                {
                    "type": addr_type,
                    "streetAddress": street,
                    "city": city,
                    "region": state,
                    "postalCode": postal_code,
                    "country": country,
                    "formattedValue": formatted,
                }
            )

    return addresses


def _parse_birthday(birthday_str: str) -> dict[str, int] | None:
    """
    Parse Microsoft Graph birthday string to Google People API date format.

    Microsoft Graph returns birthday as ISO date string (e.g., "1990-05-15").

    Returns:
        Dict with year, month, day keys (year=0 if unknown).
    """
    try:
        parts = birthday_str.split("T")[0].split("-")
        if len(parts) >= 3:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            # Microsoft uses year 1604 as sentinel for "no year"
            if year <= 1604:
                year = 0
            return {"year": year, "month": month, "day": day}
    except (ValueError, IndexError):
        logger.warning("microsoft_birthday_parse_failed", birthday=birthday_str)
    return None


def build_contact_body(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Build a Microsoft Graph contact request body from parameters.

    Args:
        name: Contact display name (required).
        email: Email address (optional).
        phone: Phone number (optional).
        organization: Company name (optional).
        notes: Personal notes (optional).

    Returns:
        Dict suitable for POST /me/contacts.
    """
    # Parse name into given/surname
    name_parts = name.strip().split(" ", 1)
    given_name = name_parts[0]
    surname = name_parts[1] if len(name_parts) > 1 else ""

    body: dict[str, Any] = {
        "givenName": given_name,
        "surname": surname,
        "displayName": name,
    }

    if email:
        body["emailAddresses"] = [{"address": email, "name": "Email"}]

    if phone:
        body["mobilePhone"] = phone

    if organization:
        body["companyName"] = organization

    if notes:
        body["personalNotes"] = notes

    return body


def build_contact_update_body(
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """
    Build a Microsoft Graph contact PATCH body from parameters.

    Only includes fields that are provided (non-None).

    Args:
        name: New display name (optional).
        email: New email address (optional).
        phone: New phone number (optional).
        organization: New company name (optional).
        notes: New personal notes (optional).
        address: New address as formatted string (optional).

    Returns:
        Dict suitable for PATCH /me/contacts/{id}.
    """
    body: dict[str, Any] = {}

    if name is not None:
        name_parts = name.strip().split(" ", 1)
        body["givenName"] = name_parts[0]
        body["surname"] = name_parts[1] if len(name_parts) > 1 else ""
        body["displayName"] = name

    if email is not None:
        body["emailAddresses"] = [{"address": email, "name": "Email"}]

    if phone is not None:
        body["mobilePhone"] = phone

    if organization is not None:
        body["companyName"] = organization

    if notes is not None:
        body["personalNotes"] = notes

    if address is not None:
        body["homeAddress"] = {"street": address}

    return body
