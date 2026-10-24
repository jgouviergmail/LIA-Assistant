"""Optional Cloudflare Turnstile keys (ADR-364): closed names and env-safe values."""

from __future__ import annotations

import re
from collections.abc import Mapping

TURNSTILE_ENV_KEYS = ("TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY")
TURNSTILE_SWITCH = "TURNSTILE_ENABLED"

# Cloudflare's documented testing keys start this way (always pass, always block, a
# forced challenge). In production one voids the check — anyone may send the dummy
# token (ADR-364) — so an installer never emits one, as it never emits DEMO_MAP_ID.
_TESTING_KEY_PREFIXES = ("1x0000", "2x0000", "3x0000")


def valid_turnstile_value(value: str) -> bool:
    """A bounded single-line key that is not a testing key, not a claim Cloudflare accepts it."""
    return re.fullmatch(r"[A-Za-z0-9_.-]{1,512}", value) is not None and not value.startswith(
        _TESTING_KEY_PREFIXES
    )


def validate_turnstile_settings(values: Mapping[str, str]) -> dict[str, str]:
    """Accept a skipped check, or a complete, injection-safe pair (the keys only).

    The switch is never part of the result: what this returns is registered as a secret
    to redact, and a redacted ``true`` would blank every switch in the install log.
    """
    if not values:
        return {}
    if set(values) != set(TURNSTILE_ENV_KEYS):
        raise ValueError("incomplete_turnstile_configuration")
    site_key, secret_key = (values[name] for name in TURNSTILE_ENV_KEYS)
    if not site_key and not secret_key:
        return {}
    if not site_key or not secret_key:
        raise ValueError("incomplete_turnstile_configuration")
    if not valid_turnstile_value(site_key) or not valid_turnstile_value(secret_key):
        raise ValueError("invalid_turnstile_configuration")
    return dict(values)
