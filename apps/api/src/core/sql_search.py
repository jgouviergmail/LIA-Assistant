"""What a person typed, turned into a literal SQL search needle.

``LIKE``'s two metacharacters are ordinary text to whoever typed them: ``_``
is what a person writes in a snake_case title, ``%`` what they write in a rate.
Measured on a real PostgreSQL server (ADR-276 cold review, 2026-09-10): a board
search for ``_`` returned EVERY ticket, and ``100%`` matched « Budget 1000
euros ».

In ``core`` rather than in ``domains/shared`` for one reason, and it is not
taste: ``shared`` already imports ``conversations`` (the provenance
repository), so a conversations module importing back would close a runtime
cycle the F009 ratchet counts. This is a primitive with no domain — every layer
may import ``core``, and ``core`` imports no domain — which is exactly what a
helper four domains need has to be.
"""

from __future__ import annotations

#: The character ``LIKE`` escapes with. It must be passed to the comparison as
#: ``escape=`` alongside every term prepared here: a pattern escaped with one
#: character and matched with another means nothing at all.
LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Turn a search term into a literal ``LIKE`` needle.

    The escape character is escaped FIRST, or a backslash the person typed
    would escape the character after it and hand the wildcard back.

    Args:
        term: What the person typed.

    Returns:
        The term with every ``LIKE`` metacharacter escaped. The caller must
        pass ``escape=LIKE_ESCAPE`` to the comparison.
    """
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


__all__ = ["LIKE_ESCAPE", "escape_like"]
