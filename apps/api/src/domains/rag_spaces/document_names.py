"""One sanitiser for every display name somebody else wrote.

Until the mail source (ADR-262), ``original_filename`` came from the account
owner (an upload) or from LIA itself (meeting minutes). A Gmail subject is
written by a third party, a kept answer's name quotes the person's own request
— and both travel into a ``Content-Disposition`` header, a zip member and the
interface. Two sanitisers would drift on the next hostile character, so every
producer of a display name comes through here.
"""

from __future__ import annotations

import re

from src.core.constants import RAG_DOCUMENT_NAME_MAX_CHARS

#: Control characters and path separators never reach a stored display name
#: (the file on disk is a UUID; the name travels into headers, archives and
#: the interface).
_UNSAFE_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f/\\]+")


def sanitize_document_name(raw: str, *, fallback: str, extension: str) -> str:
    """A bounded, control-character-free display name with its extension.

    Args:
        raw: The candidate name, as written by whoever wrote it.
        fallback: Identity used when nothing safe remains (a thread id, a
            date) — never an empty name.
        extension: Extension appended after the cap, dot included.

    Returns:
        The stored display name.
    """
    base = _UNSAFE_NAME_CHARS.sub(" ", raw or "").strip() or fallback
    return f"{base[:RAG_DOCUMENT_NAME_MAX_CHARS]}{extension}"


__all__ = ["sanitize_document_name"]
