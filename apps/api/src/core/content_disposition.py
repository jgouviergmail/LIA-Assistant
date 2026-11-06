"""A ``Content-Disposition`` for a downloaded file whose name nobody vetted (RFC 6266, 5987).

A document's display name can be a subject line a third party wrote (ADR-262);
an attachment's name is its sender's (ADR-369). The quoted ASCII half
therefore drops control characters — CR/LF would be a header injection,
refused downstream as a 500 at best — and the two characters that can end the
quoted string (a double quote and a backslash), and is length-bounded; the
UTF-8 half is percent-encoded whole, path separators included.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import quote

_UNSAFE_HEADER_CHARS: Final = re.compile(r'[\x00-\x1f\x7f-\x9f"\\]')
#: The quoted ASCII half's length (the UTF-8 half carries the whole name).
_ASCII_NAME_MAX_CHARS: Final = 200
#: What a declared type must look like to be served as one (RFC 6838 names).
_MEDIA_TYPE: Final = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")
#: What a download is served as when its declared type is not one.
OPAQUE_MEDIA_TYPE: Final = "application/octet-stream"
#: A picture that is also a page: it runs scripts where it is opened.
SVG_MEDIA_TYPE: Final = "image/svg+xml"


def served_media_type(declared: str) -> str:
    """The type a download is served as: the declared one when well formed.

    Args:
        declared: The type as the sender wrote it — untrusted.

    Returns:
        ``declared``, or ``application/octet-stream``.
    """
    return declared if _MEDIA_TYPE.fullmatch(declared) else OPAQUE_MEDIA_TYPE


def attachment_disposition(filename: str, fallback: str) -> str:
    """The header naming a download, in ASCII and in UTF-8.

    Args:
        filename: The name as received — untrusted.
        fallback: The ASCII name used when nothing ASCII survives.

    Returns:
        ``attachment; filename="…"; filename*=UTF-8''…``.
    """
    ascii_name = filename.encode("ascii", "ignore").decode()
    ascii_name = _UNSAFE_HEADER_CHARS.sub("", ascii_name).strip()[:_ASCII_NAME_MAX_CHARS]
    return (
        f'attachment; filename="{ascii_name or fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
