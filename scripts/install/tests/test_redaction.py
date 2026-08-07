"""Secret redaction contract (B13).

Canaries carry regex punctuation, URL encoding, JSON escaping, and
base64-looking bodies; redaction replaces longest secrets first and also
covers URL-encoded and JSON-escaped occurrences.
"""

from __future__ import annotations

import json
import urllib.parse

from scripts.install.redaction import REDACTED, redact

CANARIES = (
    'pw-CANARY-!$&{}[]().*+?"\\',
    "sk-proj-AbC123+/=base64ish",
    "short",
    "sk-proj-AbC123+/=base64ish-and-longer-suffix",
)


def test_every_raw_canary_is_removed() -> None:
    text = " | ".join(f"before {c} after" for c in CANARIES)
    cleaned = redact(text, CANARIES)
    for canary in CANARIES:
        assert canary not in cleaned
    assert REDACTED in cleaned


def test_longest_secret_wins_over_its_own_prefix() -> None:
    long = "sk-proj-AbC123+/=base64ish-and-longer-suffix"
    short = "sk-proj-AbC123+/=base64ish"
    cleaned = redact(f"x {long} y", (short, long))
    assert cleaned == f"x {REDACTED} y", "prefix redaction must not split the long secret"


def test_url_encoded_and_json_escaped_forms_are_covered() -> None:
    secret = 'pw-CANARY-!$&{}[]().*+?"\\'
    url_form = urllib.parse.quote(secret, safe="")
    json_form = json.dumps(secret)[1:-1]
    cleaned = redact(f"a={url_form}&b={json_form}", (secret,))
    assert url_form not in cleaned
    assert json_form not in cleaned


def test_regex_punctuation_in_secrets_is_literal() -> None:
    # A secret full of regex metacharacters must not corrupt neighbours.
    cleaned = redact("keep .* keep", (".*",))
    assert cleaned == f"keep {REDACTED} keep"


def test_empty_and_missing_secrets_are_no_ops() -> None:
    assert redact("unchanged", ()) == "unchanged"
    assert redact("unchanged", ("",)) == "unchanged"
