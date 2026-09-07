"""The briefing's half of the consultation vocabulary.

The register displays a consultation as its DOMAIN, resolved from the
capability name. Tool names resolve through their manifest; the briefing has no
tools, so its nine sections need an explicit, BOUNDED name — free text here
would put user-shaped strings into a label set that must stay closed.

The names themselves are declared with every other direct-read surface, in
:mod:`src.domains.shared.consultation_surfaces`, because keeping them here and
transcribing them into the register produced two dead tables, thirty-one
duplicated entries and a boot guard blind to all of them. What this module
owns is the CORRESPONDENCE to the briefing's own section keys, which
``test_briefing_consultations`` asserts in both directions against
``SECTION_NAMES``.
"""

from __future__ import annotations

from typing import Final

from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

#: This surface's key, shared with ``CONSULTATION_RECORDERS``.
SURFACE: Final[str] = "briefing"

_SURFACE = CONSULTATION_SURFACES[SURFACE]

#: What every briefing capability name starts with, so the register can tell
#: them apart from tool names without matching each one.
CONSULTATION_PREFIX: Final[str] = _SURFACE.prefix

#: Each section, and the taxonomy noun it reads as.
SECTION_DOMAINS: Final[dict[str, str]] = dict(_SURFACE.domains)


def consultation_capability(section: str) -> str:
    """The register name of one briefing section.

    Args:
        section: Section key, from ``briefing.constants``.

    Returns:
        The bounded capability name, e.g. ``briefing:mails``.
    """
    return _SURFACE.capability(section)


__all__ = [
    "CONSULTATION_PREFIX",
    "SECTION_DOMAINS",
    "SURFACE",
    "consultation_capability",
]
