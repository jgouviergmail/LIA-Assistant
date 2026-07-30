"""Peer discovery helpers — exact-match search primitives (spec §5.1, A6).

Kept separate from the lifecycle service so each file holds one concern
(size/CC ratchets). ``mask_email`` is the A6 homonym discriminator: enough to
tell two "Jean Dupont" apart, never enough to reconstruct the address.
"""

from __future__ import annotations


def mask_email(email: str) -> str:
    """Mask an email to its A6 hint form (``jerome@gmail.com`` → ``j…@g….com``).

    First character of the local part, first character of the domain, and the
    final dot-suffix when the domain has one. Single-character parts degrade
    gracefully; a missing part masks to ``*``.

    Args:
        email: The address to mask.

    Returns:
        The masked hint.
    """
    local, _, domain = email.partition("@")
    lead = local[:1] or "*"
    if "." in domain:
        base, _, suffix = domain.rpartition(".")
        return f"{lead}…@{base[:1]}….{suffix}"
    return f"{lead}…@{domain[:1]}…"
