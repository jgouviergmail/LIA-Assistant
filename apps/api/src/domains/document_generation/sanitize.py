"""Sanitization helpers for generated documents (ADR-226).

``neutralize_formula`` closes the spreadsheet formula-injection surface proven
by the 2026-08-17 probe: openpyxl stores any string starting with ``=`` as a
real formula, and Excel/Calc also evaluate ``+``/``-``/``@`` starters from CSV
cells. Plain signed numbers are exempt — they are data, and defacing every
negative value in a table would be a rendering defect.

``sanitize_filename_stem`` keeps human-meaningful names (accents allowed —
Starlette emits RFC 5987 ``filename*``) while stripping anything path-shaped
or forbidden on Windows filesystems. The on-disk name remains a UUID (the
attachments anti-traversal convention); this stem only feeds the download
filename shown to the user.
"""

from __future__ import annotations

import re

_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")

# A plain signed numeric literal ("-5", "+3.14", "-1e6", "-5,2") is data, not
# a formula: neutralizing it would deface every negative number in a table.
_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+([.,]\d+)?|[.,]\d+)([eE][+-]?\d+)?$")

# Path separators, control chars, characters invalid on Windows filesystems.
_FILENAME_FORBIDDEN = re.compile(r'[\\/\x00-\x1f<>:"|?*]+')
_WHITESPACE_RUN = re.compile(r"\s+")

FILENAME_STEM_MAX_LENGTH = 80


def neutralize_formula(value: str) -> str:
    """Prefix spreadsheet-active values with a quote so they stay text.

    Plain signed numbers are exempt; everything else starting with an active
    prefix (``= + - @`` and tab/CR) is prefixed with ``'`` (OWASP CSV-injection
    mitigation; the quote is visible on those rare values — an accepted
    trade-off for a uniform, auditable rule).

    Args:
        value: Raw cell value.

    Returns:
        The value, prefixed with ``'`` when it would be parsed as a formula.
    """
    if value.startswith(_FORMULA_PREFIXES) and not _PLAIN_NUMBER.match(value):
        return f"'{value}"
    return value


def sanitize_filename_stem(stem: str, fallback: str = "document") -> str:
    """Make an LLM- or user-suggested filename stem safe for downloads.

    Args:
        stem: Suggested filename without extension.
        fallback: Stem used when nothing survives sanitization.

    Returns:
        A non-empty stem with no separators/control characters, no leading or
        trailing dots, collapsed whitespace, capped at
        ``FILENAME_STEM_MAX_LENGTH``.
    """
    cleaned = _FILENAME_FORBIDDEN.sub("_", stem)
    cleaned = _WHITESPACE_RUN.sub(" ", cleaned).strip().lstrip(".").strip()
    if not cleaned:
        return fallback
    return cleaned[:FILENAME_STEM_MAX_LENGTH].rstrip(" .") or fallback
