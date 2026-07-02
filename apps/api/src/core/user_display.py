"""User display-name resolution shared across domains.

Single source of truth for turning profile data into a friendly first name
(briefing greetings, email signatures, LLM sender context). Kept free of any
ORM dependency so it can be called with raw values from any layer.
"""

from __future__ import annotations


def resolve_user_display_name(
    full_name: str | None,
    email: str | None,
    fallback: str = "",
) -> str:
    """Resolve a friendly first name from profile data.

    Fallback chain: first word of ``full_name`` → email local part →
    ``fallback``.

    Args:
        full_name: The user's full name from their profile (may be None/empty).
        email: The user's email address (may be None/empty).
        fallback: Value returned when neither source yields a name.

    Returns:
        The resolved first name, or ``fallback`` when nothing is available.
    """
    if full_name:
        stripped = full_name.strip()
        if stripped:
            return stripped.split()[0]
    if email:
        local_part = email.split("@", 1)[0]
        if local_part:
            return local_part
    return fallback
