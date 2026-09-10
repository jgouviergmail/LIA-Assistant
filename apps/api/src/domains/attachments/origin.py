"""Where a file came from, and what follows from it (ADR-279).

Every file the assistant produced — an image, a document, a browser screenshot —
was stored as an ``Attachment`` indistinguishable from something the person
uploaded. It lived in the conversation that produced it and nowhere else:
nothing listed them, nothing let a person download one back a day later, and a
conversation reset deleted the lot.

``Attachment.origin`` names the producer, and three rules follow from it:

- **The vocabulary is CLOSED and every value is decided.** ``upload`` plus
  :data:`GENERATED_ORIGINS` partition the enum, checked by a test, so a fourth
  producer cannot arrive as an unlabelled row that no surface lists.
- **A file LIA produced survives the conversation it was produced in** (owner
  arbitration, 2026-09-10). The reset removes what the PERSON put in and
  nothing else; the TTL still expires everything, generated files included.
- **An unrecognised value is never read as generated.** The gallery shows what
  is declared, not what is merely unfamiliar — the conservative side here is
  the one that does not accumulate strangers.

The backfill lives here too, next to the vocabulary it fills: the column did
not exist when the existing rows were written, so it reads the SHAPE each
producer stamped (``generated_`` from the image tool, ``browser_`` from the
streaming layer) and refuses to guess beyond it. Documents carry no marker of
their own — the generator names them after the person's request — so they are
recognised from the message metadata that points at them, in the migration,
never from a filename.
"""

from __future__ import annotations

from src.domains.attachments.models import AttachmentContentType, AttachmentOrigin

__all__ = [
    "GENERATED_ORIGINS",
    "backfilled_origin",
    "content_type_of",
    "is_generated",
]

#: Everything the assistant produced. With ``UPLOAD`` these partition the enum.
GENERATED_ORIGINS: frozenset[AttachmentOrigin] = frozenset(
    {
        AttachmentOrigin.GENERATED_IMAGE,
        AttachmentOrigin.GENERATED_DOCUMENT,
        AttachmentOrigin.BROWSER_SCREENSHOT,
    }
)

#: What each generated origin produces. An upload may be either, so it declares
#: nothing rather than a default that would be wrong half the time.
_CONTENT_TYPE: dict[AttachmentOrigin, str] = {
    AttachmentOrigin.GENERATED_IMAGE: AttachmentContentType.IMAGE,
    AttachmentOrigin.BROWSER_SCREENSHOT: AttachmentContentType.IMAGE,
    AttachmentOrigin.GENERATED_DOCUMENT: AttachmentContentType.DOCUMENT,
}

#: Stored-filename prefixes the producers stamped BEFORE the column existed.
#: Read only for the migration's backfill, and only for images: a document's
#: name comes from the person's request and proves nothing.
_IMAGE_PREFIXES: tuple[tuple[str, AttachmentOrigin], ...] = (
    ("generated_", AttachmentOrigin.GENERATED_IMAGE),
    ("browser_", AttachmentOrigin.BROWSER_SCREENSHOT),
)


def is_generated(origin: AttachmentOrigin | str | None) -> bool:
    """Whether the assistant produced this file.

    Args:
        origin: The row's ``origin`` column, as an enum member or as the raw
            string the column stores.

    Returns:
        True for a file LIA produced; False for an upload, for None, and for
        any value nobody declared.
    """
    if origin is None:
        return False
    value = origin.value if isinstance(origin, AttachmentOrigin) else origin
    return any(member.value == value for member in GENERATED_ORIGINS)


def content_type_of(origin: AttachmentOrigin) -> str | None:
    """What this origin produces.

    Args:
        origin: The producer.

    Returns:
        The content category it always produces, or None for an upload — which
        may be either, so it declares nothing rather than a wrong default.
    """
    return _CONTENT_TYPE.get(origin)


def backfilled_origin(stored_filename: str, content_type: str) -> AttachmentOrigin:
    """The origin of a row written before the column existed.

    Args:
        stored_filename: The UUID-based name on disk, whose PREFIX is the only
            marker the producers left.
        content_type: ``image`` or ``document``.

    Returns:
        The producer the shape proves, or ``UPLOAD`` — which is what the row
        always was, and the answer whenever the shape proves nothing. A prefix
        anywhere but at the start proves nothing either.
    """
    if content_type == AttachmentContentType.IMAGE:
        for prefix, origin in _IMAGE_PREFIXES:
            if stored_filename.startswith(prefix):
                return origin
    return AttachmentOrigin.UPLOAD
