"""
Contacts normalizer: vCard → dict format Google People API, and back.

Converts vCard strings (CardDAV) to the dict structure
expected by google_contacts_tools.py (same format as GooglePeopleClient).

A value's KIND reads as the other providers name it (``home``, ``work``,
``mobile``…): ``INTERNET``, ``PREF`` and ``VOICE`` describe a line, not a
kind, and ``CELL`` is ``mobile``. Writing back (ADR-369, D4), the EMAIL, TEL
and ADR lines are rewritten list by list — a line the person did not change
is kept as it was read, its group and parameters included — and every other
line of the card survives untouched.
"""

from collections.abc import Callable
from typing import Any, Final

import structlog
import vobject

from src.domains.connectors.clients.contact_details import NO_YEAR, ContactDetails
from src.domains.connectors.clients.normalizers.contact_group_cards import group_facts
from src.domains.connectors.clients.normalizers.contact_values import (
    TypedAddress,
    TypedValue,
    desired_addresses,
    desired_values,
    kept_or_built,
    same_kind,
)

logger = structlog.get_logger(__name__)

#: What tells Apple the year of a birthday is none.
_OMIT_YEAR: Final = "X-APPLE-OMIT-YEAR"

#: TYPE values that describe a line rather than what it is for.
_NOT_A_KIND: Final = frozenset({"internet", "pref", "voice", "x400"})
#: vCard's names for a kind the other providers spell differently.
_KIND_READ: Final = {"cell": "mobile"}
_KIND_WRITTEN: Final = {"mobile": "CELL"}
#: An ADR value's parts, under the names the People shape gives them.
_ADR_PARTS: Final = (
    ("streetAddress", "street"),
    ("city", "city"),
    ("region", "region"),
    ("postalCode", "code"),
    ("country", "country"),
)


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
        # The parser's text quotes the card's lines: its type alone (ADR-317).
        logger.warning(
            "vcard_parse_error", error_type=type(e).__name__, resource_name=resource_name
        )
        return {
            "resourceName": resource_name,
            "names": [{"displayName": "Unknown"}],
            "_provider": "apple",
        }

    result: dict[str, Any] = {"resourceName": resource_name, "_provider": "apple"}

    # Names
    names = _extract_names(vcard)
    if names:
        result["names"] = [names]

    # Email addresses and phone numbers, each with its kind
    emails = _typed_values(vcard, "email")
    if emails:
        result["emailAddresses"] = emails
    phones = _typed_values(vcard, "tel")
    if phones:
        result["phoneNumbers"] = phones

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

    # Websites
    if urls := _websites(vcard):
        result["urls"] = urls

    result.update(group_facts(vcard))

    return result


def _websites(vcard: Any) -> list[dict[str, str]]:
    """A card's websites, in the vocabulary the three providers share."""
    return [{"value": str(line.value)} for line in vcard.contents.get("url", []) if line.value]


def build_vcard(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    *,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
    details: ContactDetails | None = None,
) -> str:
    """
    Build a vCard string from individual parameters.

    Args:
        name: Full name (required).
        email: Email address.
        phone: Phone number.
        organization: Organization name.
        notes: Notes.
        emails: Every e-mail, typed (not with ``email``).
        phones: Every phone, typed (not with ``phone``).
        addresses: Every postal address, typed.
        details: Its name's parts, job title, website and birthday.

    Returns:
        Serialized vCard string (3.0 format for iCloud compatibility).
    """
    return vcard_component(
        name,
        email,
        phone,
        organization,
        notes,
        emails=emails,
        phones=phones,
        addresses=addresses,
        details=details,
    ).serialize()


def vcard_component(
    name: str,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    *,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
    details: ContactDetails | None = None,
) -> Any:
    """The card ``build_vcard`` serializes, for who has more to add to it."""
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

    _write_values(card, email=email, phone=phone, emails=emails, phones=phones)
    _rewrite(card, "adr", addresses or None, same=_same_address, build=_address_line(card))

    if organization:
        o = card.add("org")
        o.value = [organization]

    if notes:
        card.add("note").value = notes

    _write_details(card, details)
    return card


def _joined(given: Any, family: Any) -> str:
    """A name's parts as one name; vobject holds a part as a text or a list of them."""
    parts = (" ".join(item) if isinstance(item, list) else item for item in (given, family))
    return " ".join(part for part in parts if part)


def _set_line(card: Any, prop: str, value: str) -> None:
    """Write a property's first line; an empty value takes that line off, the others stay."""
    lines = card.contents.get(prop) or []
    if lines and value:
        lines[0].value = value
    elif lines:
        lines.pop(0)
        if not lines:
            del card.contents[prop]
    elif value:
        card.add(prop).value = value


def _write_name_parts(card: Any, details: ContactDetails, *, name_follows: bool) -> None:
    """A card's name parts, the whole name following when it was made of them."""
    if not hasattr(card, "n"):
        card.add("n").value = vobject.vcard.Name()
    name = card.n.value
    followed = name_follows and card.fn.value == _joined(name.given, name.family)
    card.n.value = vobject.vcard.Name(
        family=name.family if details.family_name is None else details.family_name,
        given=name.given if details.given_name is None else details.given_name,
        additional=name.additional,
        prefix=name.prefix,
        suffix=name.suffix,
    )
    if followed and (whole := _joined(card.n.value.given, card.n.value.family)):
        card.fn.value = whole


def _write_details(
    card: Any, details: ContactDetails | None, *, name_follows: bool = False
) -> None:
    """Write what ``details`` names on a card; every other line stays.

    Args:
        card: The card.
        details: What changes.
        name_follows: A change named no whole name: one made of the parts follows them, as
            Google's and Graph's do.
    """
    if details is None:
        return
    if details.given_name is not None or details.family_name is not None:
        _write_name_parts(card, details, name_follows=name_follows)
    if details.job_title is not None:
        _set_line(card, "title", details.job_title)
    if details.website is not None:
        _set_line(card, "url", details.website)
    if details.birthday is not None:
        _set_line(card, "bday", details.birthday.isoformat())
        card.bday.params.pop(_OMIT_YEAR, None)
        if details.birthday.year == NO_YEAR:
            card.bday.params[_OMIT_YEAR] = [str(NO_YEAR)]
    elif details.clear_birthday:
        _set_line(card, "bday", "")


def merge_vcard_fields(
    existing_vcard: str,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    organization: str | None = None,
    notes: str | None = None,
    address: str | None = None,
    *,
    emails: list[TypedValue] | None = None,
    phones: list[TypedValue] | None = None,
    addresses: list[TypedAddress] | None = None,
    details: ContactDetails | None = None,
) -> str:
    """
    Merge updated fields into an existing vCard.

    Only non-None fields are updated; existing fields are preserved. A single
    e-mail, phone or address replaces the PRIMARY one (its line's parameters
    kept) and keeps the others; a list replaces that list.

    Args:
        existing_vcard: Raw vCard string to update.
        name: New full name (updates FN and N).
        email: New primary email.
        phone: New primary phone.
        organization: New organization.
        notes: New notes.
        address: New primary address (free-form string, stored as ADR street).
        emails: Every e-mail, typed.
        phones: Every phone, typed.
        addresses: Every postal address, typed.
        details: What changes of its name's parts, job, website and birthday.

    Returns:
        Updated serialized vCard string.

    Raises:
        ValueError: The existing card cannot be read — a card rebuilt from the
            update alone would overwrite every field of the real contact.
    """
    try:
        card = vobject.readOne(existing_vcard)
    except Exception as e:
        logger.warning("vcard_merge_parse_error", error_type=type(e).__name__)
        raise ValueError("The contact's card cannot be read; it was not overwritten.") from e

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

    _write_values(card, email=email, phone=phone, emails=emails, phones=phones)
    _rewrite(
        card,
        "adr",
        desired_addresses(address, addresses, _typed_addresses(card)),
        same=_same_address,
        build=_address_line(card),
    )

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

    _write_details(card, details, name_follows=name is None and hasattr(card, "fn"))
    return card.serialize()


def _write_values(
    card: Any,
    *,
    email: str | None,
    phone: str | None,
    emails: list[TypedValue] | None,
    phones: list[TypedValue] | None,
) -> None:
    """Rewrite the EMAIL and TEL lines an update or a new card asks for."""
    for prop, single, given in (("email", email, emails), ("tel", phone, phones)):
        _rewrite(
            card,
            prop,
            desired_values(single, given, _typed_values(card, prop)),
            same=_same_value,
            build=_value_line(card, prop),
        )


def _rewrite(
    card: Any,
    prop: str,
    wanted: list[Any] | None,
    *,
    same: Callable[[Any, Any], bool],
    build: Callable[[Any, Any], Any],
) -> None:
    """Replace one property's lines with ``wanted`` — kept lines untouched; None leaves them."""
    if wanted is None:
        return
    lines = list(card.contents.get(prop, []))
    written = kept_or_built(lines, wanted, same=same, build=build)
    if written:
        card.contents[prop] = written
    else:
        card.contents.pop(prop, None)


def _kind(line: Any) -> str:
    """A line's kind, as the other providers name it (``other`` when it says none)."""
    for value in line.params.get("TYPE", []):
        kind = str(value).casefold()
        if kind not in _NOT_A_KIND:
            return _KIND_READ.get(kind, kind)
    return "other"


def _typed_values(card: Any, prop: str) -> list[TypedValue]:
    return [
        {"value": str(line.value), "type": _kind(line)}
        for line in card.contents.get(prop, [])
        if line.value
    ]


def _typed_addresses(card: Any) -> list[TypedAddress]:
    return [
        {"formatted": _formatted_address(line.value), "type": _kind(line)}
        for line in card.contents.get("adr", [])
        if line.value and _formatted_address(line.value)
    ]


def _same_value(line: Any, wanted: TypedValue) -> bool:
    return str(line.value).casefold() == wanted["value"].casefold() and same_kind(
        _kind(line), wanted["type"]
    )


def _same_address(line: Any, wanted: TypedAddress) -> bool:
    return _formatted_address(line.value) == wanted["formatted"] and same_kind(
        _kind(line), wanted["type"]
    )


def _new_line(card: Any, prop: str, kind: str | None, replaced: Any) -> Any:
    """A new line, wearing the parameters and group of the one it replaces when same-kind."""
    line = card.add(prop)
    if replaced is not None and same_kind(_kind(replaced), kind):
        line.params = {name: list(values) for name, values in replaced.params.items()}
        line.group = replaced.group
    elif kind and not same_kind(kind, None):
        line.params["TYPE"] = [_KIND_WRITTEN.get(kind.casefold(), kind.upper())]
    return line


def _value_line(card: Any, prop: str) -> Callable[[TypedValue, Any], Any]:
    def build(wanted: TypedValue, replaced: Any) -> Any:
        line = _new_line(card, prop, wanted["type"], replaced)
        line.value = wanted["value"]
        return line

    return build


def _address_line(card: Any) -> Callable[[TypedAddress, Any], Any]:
    def build(wanted: TypedAddress, replaced: Any) -> Any:
        line = _new_line(card, "adr", wanted["type"], replaced)
        # Free-form: the one line goes in the street, never beside a stale city.
        line.value = vobject.vcard.Address(street=wanted["formatted"])
        return line

    return build


def _formatted_address(value: Any) -> str:
    """An ADR value on one line, as the read side shows it."""
    parts = (getattr(value, part, "") for _key, part in _ADR_PARTS)
    return ", ".join(str(part) for part in parts if part)


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
    """Extract addresses from vCard, each with its kind and its one-line form."""
    addresses: list[dict[str, str]] = []
    for adr in getattr(vcard, "adr_list", []):
        val = adr.value if hasattr(adr, "value") else adr
        if not val:
            continue
        addr = {key: str(getattr(val, part)) for key, part in _ADR_PARTS if getattr(val, part, "")}
        if addr:
            addr["type"] = _kind(adr)
            addr["formattedValue"] = _formatted_address(val)
            addresses.append(addr)
    return addresses


def _get_value(vcard: Any, prop_name: str) -> Any:
    """Safely get a property value from a vCard."""
    prop = getattr(vcard, prop_name, None)
    if prop is not None:
        return prop.value if hasattr(prop, "value") else prop
    return None


def _kept_year(day: dict[str, int]) -> dict[str, int]:
    """A date as read, without the year that says there is none."""
    return (
        {key: value for key, value in day.items() if key != "year"}
        if (day["year"] == NO_YEAR)
        else day
    )


def _parse_birthday(bday: Any) -> dict[str, int] | None:
    """
    Parse a vCard birthday value into Google People API format.

    vCard BDAY can be:
    - datetime.date object (vobject auto-parses valid dates)
    - string like "1990-05-15", "19900515", "--05-15" (no year)

    Returns:
        Dict with year/month/day keys matching Google People API format,
        or None if parsing fails. Apple writes a birthday with no year in 1604.
    """
    from datetime import date as date_type

    if isinstance(bday, date_type):
        return _kept_year({"year": bday.year, "month": bday.month, "day": bday.day})

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
                return _kept_year(
                    {"year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])}
                )
        elif len(bday_str) == 8 and bday_str.isdigit():
            return _kept_year(
                {"year": int(bday_str[:4]), "month": int(bday_str[4:6]), "day": int(bday_str[6:8])}
            )
    except ValueError, IndexError:
        logger.debug("birthday_parse_error", raw_value=bday_str)

    return None
