"""Keep a mail display header separate from the mailbox used by other tools."""

from collections.abc import Mapping, MutableMapping
from email.utils import parseaddr

from src.core.validators import validate_email


def _header_value(payload: object, name: str) -> str:
    """Read one raw Gmail header without assuming its untrusted structure."""
    if not isinstance(payload, Mapping):
        return ""
    headers = payload.get("headers")
    if not isinstance(headers, list):
        return ""
    for header in headers:
        if not isinstance(header, Mapping):
            continue
        key, value = header.get("name"), header.get("value")
        if isinstance(key, str) and key.casefold() == name and isinstance(value, str):
            return value
    return ""


def project_email_headers(email: MutableMapping[str, object]) -> None:
    """Promote display headers and expose a validated, nullable sender mailbox.

    Calendar attendees and explicit MCP email-format inputs require a plain
    mailbox. The RFC 5322 name-addr remains intact for display and inspection;
    a missing or malformed sender provides no interchangeable address.
    """
    email.setdefault("subject", _header_value(email.get("payload"), "subject"))
    email.setdefault("from", _header_value(email.get("payload"), "from"))
    sender = email.get("from")
    address = parseaddr(sender)[1] if isinstance(sender, str) else ""
    email["from_email"] = address if validate_email(address) else None
