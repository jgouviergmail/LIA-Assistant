"""
Contacts normalizer: Microsoft Graph contact → dict format Google People API.

Converts Microsoft Graph API contact objects to the dict structure
expected by contacts_tools.py (same format as GooglePeopleClient), and back:
a contact's e-mails, phones and addresses are written in the SLOTS Exchange
stores them in (ADR-369, D4) — three e-mails, two business and two home
phones, one mobile, one address of each kind. A list Exchange cannot hold is
refused with its bound, never truncated.
"""

from collections.abc import Mapping
from typing import Any, Final

import structlog

from src.domains.connectors.clients.normalizers.contact_values import (
    ContactValuesRefused,
    TypedAddress,
    TypedValue,
    addresses_read,
    bounded,
    desired_addresses,
    desired_values,
    kept_or_built,
    values_read,
)

logger = structlog.get_logger(__name__)

#: What an Exchange contact holds (Email1-3, Business/Business2, Home/Home2,
#: Mobile, one address per kind) — the bounds the contacts editor publishes.
GRAPH_EMAILS_MAX: Final = 3
GRAPH_BUSINESS_PHONES_MAX: Final = 2
GRAPH_HOME_PHONES_MAX: Final = 2
GRAPH_MOBILE_PHONES_MAX: Final = 1
GRAPH_ADDRESSES_PER_KIND_MAX: Final = 1

#: A phone's slot by its kind; no kind is the mobile (where a lone number always went).
_PHONE_SLOTS: Final = {
    "mobile": "mobilePhone",
    "cell": "mobilePhone",
    "work": "businessPhones",
    "business": "businessPhones",
}
#: An address's slot by its kind; no kind is home (where a lone address always went).
_ADDRESS_SLOTS: Final = {
    "home": "homeAddress",
    "work": "businessAddress",
    "business": "businessAddress",
}
_ADDRESS_FIELDS: Final = ("street", "city", "state", "postalCode", "countryOrRegion")
#: An address slot emptied — Graph keeps a slot it is not sent.
_NO_ADDRESS: Final = dict.fromkeys(_ADDRESS_FIELDS, "")


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
    if company or job_title or department:
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

            formatted = _formatted(addr)

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
    except ValueError, IndexError:
        logger.warning("microsoft_birthday_parse_failed", birthday=birthday_str)
    return None


def build_contact_body(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    *,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
) -> dict[str, Any]:
    """
    Build a Microsoft Graph contact request body from parameters.

    Args:
        name: Contact display name (required).
        email: Email address (optional).
        phone: Phone number (optional).
        organization: Company name (optional).
        notes: Personal notes (optional).
        emails: Every e-mail (optional; not with ``email``).
        phones: Every phone, each in its kind's slot (optional; not with ``phone``).
        addresses: Every address, one per kind (optional).

    Returns:
        Dict suitable for POST /me/contacts.

    Raises:
        ContactValuesRefused: A list Exchange cannot hold.
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

    values = contact_value_fields(
        {}, email=email, phone=phone, emails=emails, phones=phones, addresses=addresses
    )
    body.update({field: value for field, value in values.items() if _filled(value)})

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
    *,
    current: Mapping[str, Any] | None = None,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
) -> dict[str, Any]:
    """
    Build a Microsoft Graph contact PATCH body from parameters.

    Only includes fields that are provided (non-None). A single e-mail, phone
    or address replaces the contact's PRIMARY one and keeps the others; a list
    replaces its slots whole — Graph replaces an array it is sent.

    Args:
        name: New display name (optional).
        email: New primary email address (optional).
        phone: New primary phone number (optional).
        organization: New company name (optional).
        notes: New personal notes (optional).
        address: New primary address as formatted string (optional).
        current: The contact as Graph stores it (needed for any value field).
        emails: Every e-mail (optional).
        phones: Every phone (optional).
        addresses: Every address (optional).

    Returns:
        Dict suitable for PATCH /me/contacts/{id}.

    Raises:
        ContactValuesRefused: A list Exchange cannot hold.
    """
    body: dict[str, Any] = {}

    if name is not None:
        name_parts = name.strip().split(" ", 1)
        body["givenName"] = name_parts[0]
        body["surname"] = name_parts[1] if len(name_parts) > 1 else ""
        body["displayName"] = name

    body.update(
        contact_value_fields(
            current or {},
            email=email,
            phone=phone,
            address=address,
            emails=emails,
            phones=phones,
            addresses=addresses,
        )
    )

    if organization is not None:
        body["companyName"] = organization

    if notes is not None:
        body["personalNotes"] = notes

    return body


def contact_value_fields(
    current: Mapping[str, Any],
    *,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
) -> dict[str, Any]:
    """The Graph fields a write of e-mails, phones and addresses sets.

    Args:
        current: The contact as Graph stores it (``{}`` for a new one).
        email: A single e-mail, replacing the primary one.
        phone: A single phone, replacing the primary one.
        address: A single address, replacing the primary one.
        emails: Every e-mail.
        phones: Every phone.
        addresses: Every address.

    Returns:
        Each Graph field written: every slot of a list asked for, none of the others.

    Raises:
        ContactValuesRefused: A list Exchange cannot hold.
        ValueError: A single value and its list given together.
    """
    fields: dict[str, Any] = {}
    written_emails = _emails(current, email, emails)
    if written_emails is not None:
        fields["emailAddresses"] = written_emails
    fields.update(_phones(current, phone, phones))
    fields.update(_addresses(current, address, addresses))
    return fields


def _shown_email(entry: Mapping[str, Any]) -> bool:
    """An address the read side shows — an Exchange X500 path is never one."""
    value = entry.get("address")
    return bool(value) and not str(value).startswith("/")


def _emails(
    current: Mapping[str, Any], single: str | None, given: list[TypedValue] | None
) -> list[Mapping[str, Any]] | None:
    stored = [e for e in current.get("emailAddresses") or [] if isinstance(e, Mapping)]
    shown = [e for e in stored if _shown_email(e)]
    wanted = desired_values(single, given, [{"value": e["address"], "type": None} for e in shown])
    if wanted is None:
        return None
    written = kept_or_built(
        shown,
        wanted,
        same=lambda entry, value: str(entry["address"]).casefold() == value["value"].casefold(),
        build=lambda value, _replaced: {"address": value["value"]},
    )
    # An X500 path is never shown, so never asked for — and never silently dropped.
    hidden = [e for e in stored if not _shown_email(e)]
    return bounded([*written, *hidden], "emails", GRAPH_EMAILS_MAX)


def _phones(
    current: Mapping[str, Any], single: str | None, given: list[TypedValue] | None
) -> dict[str, Any]:
    wanted = desired_values(single, given, values_read(_extract_phones(dict(current))))
    if wanted is None:
        return {}
    slots: dict[str, list[str]] = {"mobilePhone": [], "businessPhones": [], "homePhones": []}
    for phone in wanted:
        kind = str(phone["type"] or "mobile").casefold()
        slots[_PHONE_SLOTS.get(kind, "homePhones")].append(phone["value"])
    mobile = bounded(slots["mobilePhone"], "mobile_phones", GRAPH_MOBILE_PHONES_MAX)
    return {
        "mobilePhone": mobile[0] if mobile else None,
        "businessPhones": bounded(
            slots["businessPhones"], "business_phones", GRAPH_BUSINESS_PHONES_MAX
        ),
        "homePhones": bounded(slots["homePhones"], "home_phones", GRAPH_HOME_PHONES_MAX),
    }


def _addresses(
    current: Mapping[str, Any], single: str | None, given: list[TypedAddress] | None
) -> dict[str, Any]:
    wanted = desired_addresses(single, given, addresses_read(_extract_addresses(dict(current))))
    if wanted is None:
        return {}
    written: dict[str, Any] = dict.fromkeys(
        ("homeAddress", "businessAddress", "otherAddress"), _NO_ADDRESS
    )
    for address in wanted:
        slot = _ADDRESS_SLOTS.get(str(address["type"] or "home").casefold(), "otherAddress")
        if written[slot] is not _NO_ADDRESS:
            raise ContactValuesRefused("addresses", GRAPH_ADDRESSES_PER_KIND_MAX)
        stored = current.get(slot)
        unchanged = isinstance(stored, Mapping) and _formatted(stored) == address["formatted"]
        written[slot] = (
            dict(stored) if unchanged else {**_NO_ADDRESS, "street": address["formatted"]}
        )
    return {slot: dict(value) for slot, value in written.items()}


def _formatted(address: Mapping[str, Any]) -> str:
    """An address on one line, as the read side shows it."""
    return ", ".join(str(address[part]) for part in _ADDRESS_FIELDS if address.get(part))


def _filled(value: object) -> bool:
    """Whether a new contact's field carries anything (an empty slot is not sent)."""
    return bool(value) and value != _NO_ADDRESS
