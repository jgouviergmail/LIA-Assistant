"""Secret redaction (B13).

Longest secrets are replaced first (a shorter secret that is a prefix of a
longer one must not split it), and URL-encoded plus JSON-escaped forms are
covered — a secret that leaked into a query string or a JSON document is
still a secret. All matching is LITERAL: regex metacharacters inside a
secret never corrupt neighbouring text.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterable

REDACTED = "***"


def _forms(secret: str) -> list[str]:
    forms = [secret]
    url_form = urllib.parse.quote(secret, safe="")
    if url_form != secret:
        forms.append(url_form)
    json_form = json.dumps(secret)[1:-1]
    if json_form != secret:
        forms.append(json_form)
    return forms


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every registered secret (and its encoded forms) in ``text``."""
    needles = sorted(
        {form for secret in secrets if secret for form in _forms(secret)},
        key=len,
        reverse=True,
    )
    for needle in needles:
        text = text.replace(needle, REDACTED)
    return text
