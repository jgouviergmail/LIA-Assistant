"""Removing a run's real keys from what its output repeats (point 6, ADR-298).

The sandbox holds a per-run token and the proxy swaps it for the person's real
key on the wire. But the service on the other side may QUOTE what it received
— an error body, a debug echo — and the script prints what it got back. That
text reaches the model, the registers and the answer. Both doors of a network
run pass their output here: a script's run and a skill's command.

Known limit, written: a key inside a compressed or otherwise encoded binary is
not found.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote, quote_plus

#: Shorter than this, a value is not a key: replacing it would eat every word
#: that contains it.
_MIN_SECRET_CHARS = 8
SCRUBBED = "[REDACTED]"


def _written_forms(secrets: Iterable[str]) -> list[str]:
    """Every form a key is written in — as is and URL-encoded — longest first.

    Args:
        secrets: The run's real keys.

    Returns:
        The forms to remove, so that no form is left half-replaced by a shorter one.
    """
    forms: set[str] = set()
    for secret in secrets:
        if len(secret) >= _MIN_SECRET_CHARS:
            forms.update({secret, quote(secret, safe=""), quote_plus(secret)})
    return sorted(forms, key=len, reverse=True)


def scrub_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace every real key ``text`` quotes.

    Args:
        text: What the run printed.
        secrets: The run's real keys.

    Returns:
        The text, each key written ``[REDACTED]``.
    """
    for form in _written_forms(secrets):
        text = text.replace(form, SCRUBBED)
    return text


def scrub_secret_bytes(data: bytes, secrets: Iterable[str]) -> bytes:
    """Mask every real key a file carries, IN PLACE.

    The mask keeps the length, so that a binary's offsets stay where they were
    (a PDF's cross-reference table, typically).

    Args:
        data: A file the run wrote.
        secrets: The run's real keys.

    Returns:
        The bytes, each key overwritten with asterisks.
    """
    for form in _written_forms(secrets):
        encoded = form.encode()
        data = data.replace(encoded, b"*" * len(encoded))
    return data
