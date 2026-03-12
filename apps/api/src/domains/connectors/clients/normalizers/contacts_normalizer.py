"""
Contacts normalizer: vCard → dict format Google People API.

Converts vCard strings (CardDAV) to the dict structure
expected by google_contacts_tools.py (same format as GooglePeopleClient).
"""

from typing import Any

import structlog
import vobject

logger = structlog.get_logger(__name__)


def normalize_vcard(vcard_str: str, resource_name: str = "") -> dict[str, Any]:
    """
    Normalize a vCard string to Google People API dict format.

    Args:
        vcard_str: Raw vCard string (3.0 or 4.0 format).
        resource_name: CardDAV URL of the contact (used as resourceName).

    Returns:
        Dict matching Google People API person format.
    """
    try:
        vcard = vobject.readOne(vcard_str)
    except Exception as e:
        logger.warning("vcard_parse_error", error=str(e), resource_name=resource_name)
        return {"resourceName": resource_name, "names": [{"displayName": "Unknown"}]}

    result: dict[str, Any] = {"resourceName": resource_name}

    # Names
    names = _extract_names(vcard)
    if names:
        result["names"] = [names]

    # Email addresses
    emails = _extract_list(vcard, "email")
    if emails:
        result["emailAddresses"] = [
            {"value": e, "type": _get_type_param(vcard, "email", i)} for i, e in enumerate(emails)
        ]

    # Phone numbers
    phones = _extract_list(vcard, "tel")
    if phones:
        result["phoneNumbers"] = [
            {"value": p, "type": _get_type_param(vcard, "tel", i)} for i, p in enumerate(phones)
        ]

    # Organizations
    org = _extract_org(vcard)
    if org:
        result["organizations"] = [org]

    # Birthdays — must match Google People API format: {"date": {"year": N, "month": N, "day": N}}
    bday = _get_value(vcard, "bday")
    if bday:
        bday_dict = _parse_birthday(bday)
        if bday_dict:
            result["birthdays"] = [{"date": bday_dict}]

    # Addresses
    addresses = _extract_addresses(vcard)
    if addresses:
        result["addresses"] = addresses

    # Photos (URL only, not base64 for performance)
    photo = _get_value(vcard, "photo")
    if photo and isinstance(photo, str) and photo.startswith(("http://", "https://")):
        result["photos"] = [{"url": photo}]

    # Notes
    note = _get_value(vcard, "note")
    if note:
        result["biographies"] = [{"value": str(note)}]

    return result


def build_vcard(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
) -> str:
    """
    Build a vCard string from individual parameters.

    Args:
        name: Full name (required).
        email: Email address.
        phone: Phone number.
        organization: Organization name.
        notes: Notes.

    Returns:
        Serialized vCard string (3.0 format for iCloud compatibility).
    """
    card = vobject.vCard()

    # FN (formatted name) — required
    card.add("fn").value = name

    # N (structured name) — parse from full name
    parts = name.strip().split(None, 1)
    n = card.add("n")
    if len(parts) >= 2:
        n.value = vobject.vcard.Name(family=parts[1], given=parts[0])
    else:
        n.value = vobject.vcard.Name(family=parts[0], given="")

    if email:
        card.add("email").value = email

    if phone:
        card.add("tel").value = phone

    if organization:
        o = card.add("org")
        o.value = [organization]

    if notes:
        card.add("note").value = notes

    return card.serialize()


def merge_vcard_fields(
    existing_vcard: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
) -> str:
    """
    Merge updated fields into an existing vCard.

    Only non-None fields are updated; existing fields are preserved.

    Args:
        existing_vcard: Raw vCard string to update.
        name: New full name (updates FN and N).
        email: New email (replaces first email or adds one).
        phone: New phone (replaces first phone or adds one).
        organization: New organization.
        notes: New notes.
        address: New address (free-form string, stored as ADR label).

    Returns:
        Updated serialized vCard string.
    """
    try:
        card = vobject.readOne(existing_vcard)
    except Exception as e:
        logger.warning("vcard_merge_parse_error", error=str(e))
        # Fallback: create new card with provided fields
        return build_vcard(
            name=name or "Unknown",
            email=email,
            phone=phone,
            organization=organization,
            notes=notes,
        )

    if name is not None:
        # Update FN
        if hasattr(card, "fn"):
            card.fn.value = name
        else:
            card.add("fn").value = name

        # Update N
        parts = name.strip().split(None, 1)
        if hasattr(card, "n"):
            if len(parts) >= 2:
                card.n.value = vobject.vcard.Name(family=parts[1], given=parts[0])
            else:
                card.n.value = vobject.vcard.Name(family=parts[0], given="")
        else:
            n = card.add("n")
            if len(parts) >= 2:
                n.value = vobject.vcard.Name(family=parts[1], given=parts[0])
            else:
                n.value = vobject.vcard.Name(family=parts[0], given="")

    if email is not None:
        _replace_or_add(card, "email", email)

    if phone is not None:
        _replace_or_add(card, "tel", phone)

    if organization is not None:
        if hasattr(card, "org"):
            card.org.value = [organization]
        else:
            o = card.add("org")
            o.value = [organization]

    if notes is not None:
        if hasattr(card, "note"):
            card.note.value = notes
        else:
            card.add("note").value = notes

    if address is not None:
        # Store as ADR with label
        if hasattr(card, "adr"):
            # Remove existing ADR entries
            while hasattr(card, "adr"):
                card.remove(card.adr)
        adr = card.add("adr")
        # Free-form: put everything in street address
        adr.value = vobject.vcard.Address(street=address)

    return card.serialize()


# =========================================================================
# PRIVATE HELPERS
# =========================================================================


def _extract_names(vcard: Any) -> dict[str, str]:
    """Extract name fields from vCard."""
    names: dict[str, str] = {}

    fn = _get_value(vcard, "fn")
    if fn:
        names["displayName"] = str(fn)

    n = _get_value(vcard, "n")
    if n and hasattr(n, "given"):
        if n.given:
            names["givenName"] = str(n.given)
        if n.family:
            names["familyName"] = str(n.family)

    # Fallback displayName from N components
    if "displayName" not in names:
        parts = []
        if "givenName" in names:
            parts.append(names["givenName"])
        if "familyName" in names:
            parts.append(names["familyName"])
        if parts:
            names["displayName"] = " ".join(parts)

    return names


def _extract_list(vcard: Any, prop_name: str) -> list[str]:
    """Extract a list of values from a vCard property (e.g., email_list, tel_list)."""
    list_attr = f"{prop_name}_list"
    items = getattr(vcard, list_attr, [])
    values = []
    for item in items:
        val = item.value if hasattr(item, "value") else str(item)
        if val:
            values.append(str(val))
    return values


def _get_type_param(vcard: Any, prop_name: str, index: int) -> str:
    """Get the TYPE parameter for a vCard property at given index."""
    list_attr = f"{prop_name}_list"
    items = getattr(vcard, list_attr, [])
    if index < len(items):
        item = items[index]
        type_values = item.params.get("TYPE", [])
        if type_values:
            return str(type_values[0]).lower()
    return "other"


def _extract_org(vcard: Any) -> dict[str, str] | None:
    """Extract organization from vCard."""
    org = _get_value(vcard, "org")
    if not org:
        return None

    result: dict[str, str] = {}
    if isinstance(org, list | tuple) and org:
        result["name"] = str(org[0])
    else:
        result["name"] = str(org)

    title = _get_value(vcard, "title")
    if title:
        result["title"] = str(title)

    return result


def _extract_addresses(vcard: Any) -> list[dict[str, str]]:
    """Extract addresses from vCard."""
    addresses = []
    adr_list = getattr(vcard, "adr_list", [])

    for adr in adr_list:
        val = adr.value if hasattr(adr, "value") else adr
        if not val:
            continue

        addr: dict[str, str] = {}
        if hasattr(val, "street") and val.street:
            addr["streetAddress"] = str(val.street)
        if hasattr(val, "city") and val.city:
            addr["city"] = str(val.city)
        if hasattr(val, "region") and val.region:
            addr["region"] = str(val.region)
        if hasattr(val, "code") and val.code:
            addr["postalCode"] = str(val.code)
        if hasattr(val, "country") and val.country:
            addr["country"] = str(val.country)

        # Type parameter
        type_param = getattr(adr, "type_paramvals", None) or getattr(adr, "TYPE_paramvals", None)
        if type_param and isinstance(type_param, list | tuple):
            addr["type"] = str(type_param[0]).lower()

        if addr:
            # Build formattedValue for display (Google People API compatibility)
            format_parts = []
            if addr.get("streetAddress"):
                format_parts.append(addr["streetAddress"])
            if addr.get("city"):
                format_parts.append(addr["city"])
            if addr.get("region"):
                format_parts.append(addr["region"])
            if addr.get("postalCode"):
                format_parts.append(addr["postalCode"])
            if addr.get("country"):
                format_parts.append(addr["country"])
            if format_parts:
                addr["formattedValue"] = ", ".join(format_parts)
            addresses.append(addr)

    return addresses


def _get_value(vcard: Any, prop_name: str) -> Any:
    """Safely get a property value from a vCard."""
    prop = getattr(vcard, prop_name, None)
    if prop is not None:
        return prop.value if hasattr(prop, "value") else prop
    return None


def _parse_birthday(bday: Any) -> dict[str, int] | None:
    """
    Parse a vCard birthday value into Google People API format.

    vCard BDAY can be:
    - datetime.date object (vobject auto-parses valid dates)
    - string like "1990-05-15", "19900515", "--05-15" (no year)

    Returns:
        Dict with year/month/day keys matching Google People API format,
        or None if parsing fails.
    """
    from datetime import date as date_type

    if isinstance(bday, date_type):
        return {"year": bday.year, "month": bday.month, "day": bday.day}

    bday_str = str(bday).strip()
    if not bday_str:
        return None

    try:
        # Handle "--MM-DD" (no year, vCard 4.0 convention)
        if bday_str.startswith("--"):
            parts = bday_str[2:].split("-")
            if len(parts) == 2:
                return {"month": int(parts[0]), "day": int(parts[1])}
            return None

        # Handle "YYYY-MM-DD" or "YYYYMMDD"
        if "-" in bday_str:
            parts = bday_str.split("-")
            if len(parts) == 3:
                return {"year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])}
        elif len(bday_str) == 8 and bday_str.isdigit():
            return {
                "year": int(bday_str[:4]),
                "month": int(bday_str[4:6]),
                "day": int(bday_str[6:8]),
            }
    except (ValueError, IndexError):
        logger.debug("birthday_parse_error", raw_value=bday_str)

    return None


def _replace_or_add(card: Any, prop_name: str, value: str) -> None:
    """Replace the first occurrence of a property or add it."""
    list_attr = f"{prop_name}_list"
    items = getattr(card, list_attr, [])
    if items:
        items[0].value = value
    else:
        card.add(prop_name).value = value
