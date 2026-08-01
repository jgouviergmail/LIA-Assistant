"""Peer discovery helpers — exact-match search primitives (spec §5.1, A6).

Kept separate from the lifecycle service so each file holds one concern
(size/CC ratchets). ``mask_email`` is the A6 homonym discriminator: enough to
tell two "Jean Dupont" apart, never enough to reconstruct the address.
``looks_like_email`` is the single authority routing one search box between
the name branch and the address branch (Bloc B).
"""

from __future__ import annotations


def looks_like_email(value: str) -> bool:
    """Tell whether a search string is an address rather than a name.

    ONE search box takes both, so something must route — and that something
    lives here, once. A heuristic duplicated in the frontend would eventually
    disagree with this one about the same string, and the user would get a
    branch neither layer intended.

    An address is: no inner whitespace, exactly one ``@``, a non-empty local
    part and a non-empty domain. A dot is NOT required — a self-hosted
    instance legitimately holds ``admin@localhost``. Deliberately looser than
    RFC validation: this only picks a branch, and an address that matches
    nothing yields an honest "no result", never an error.

    Args:
        value: Raw search input.

    Returns:
        True when the input should be searched as an address.
    """
    candidate = value.strip()
    if not candidate or any(char.isspace() for char in candidate):
        return False
    local, separator, domain = candidate.partition("@")
    return bool(separator) and bool(local) and bool(domain) and "@" not in domain


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
