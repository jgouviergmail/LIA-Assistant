"""What an outgoing e-mail's recipients and content must be before a draft is shown.

Moved out of ``emails_tools`` unchanged (lot 19, its logical size cap): plain or
RFC 5322 « Name <address> » recipients, each address checked, subject and body required.
"""

from __future__ import annotations

from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages, SupportedLanguage
from src.core.validators import validate_email
from src.domains.agents.tools.exceptions import EmailValidationError


def extract_email_from_address(address: str) -> str:
    """
    Extract email from address string.

    Handles formats:
    - "email@example.com" → "email@example.com"
    - "Name <email@example.com>" → "email@example.com"

    Args:
        address: Email address (plain or RFC 5322 format)

    Returns:
        Extracted email address
    """
    import re

    address = address.strip()
    # Match "Name <email>" format (RFC 5322)
    match = re.match(r".*<([^>]+)>", address)
    if match:
        return match.group(1).strip()
    return address


def validate_email_addresses(
    addresses: str,
    field_name: str,
    language: SupportedLanguage | None = None,
) -> None:
    """
    Validate comma-separated email addresses.

    Supports both plain emails and RFC 5322 format "Name <email>".

    Args:
        addresses: Comma-separated email addresses
        field_name: Field name for error messages (to, cc, bcc)
        language: User language for error messages

    Raises:
        EmailValidationError: If any email has invalid format
    """
    for email_addr in addresses.split(","):
        email_addr = email_addr.strip()
        if email_addr:
            # Extract email from "Name <email>" format if needed
            extracted = extract_email_from_address(email_addr)
            if not validate_email(extracted):
                raise EmailValidationError(
                    APIMessages.email_invalid_format(email_addr, resolve_language(language)),
                    field=field_name,
                )


def validate_send_email_inputs(
    to: str | None,
    subject: str | None,
    body: str | None,
    cc: str | None = None,
    bcc: str | None = None,
    language: SupportedLanguage | None = None,
) -> None:
    """
    Validate send_email inputs (centralized validation).

    Args:
        to: Recipient email(s)
        subject: Email subject
        body: Email body
        cc: CC recipients (optional)
        bcc: BCC recipients (optional)
        language: User language for error messages

    Raises:
        EmailValidationError: If validation fails
    """
    language = resolve_language(language)
    # Required fields
    if not to:
        raise EmailValidationError(
            APIMessages.email_field_required("to", language),
            field="to",
        )
    if not subject or not body:
        raise EmailValidationError(
            APIMessages.email_fields_required(["subject", "body"], language),
            field="subject,body",
        )

    # Email format validation
    validate_email_addresses(to, "to", language)
    if cc:
        validate_email_addresses(cc, "cc", language)
    if bcc:
        validate_email_addresses(bcc, "bcc", language)


__all__ = [
    "extract_email_from_address",
    "validate_email_addresses",
    "validate_send_email_inputs",
]
