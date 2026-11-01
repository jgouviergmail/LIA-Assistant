"""The HTML body of a message: one rule for every mail provider (ADR-369, D3).

Display only: the model reads the clean text, never markup (ADR-287). A
message's HTML is every ``text/html`` part of its body, in document order,
joined — a mail client that splits its body around an inline image writes
several — except a part that carries a file name (an attachment, an ``.html``
page someone sent) and anything inside a message forwarded as an attachment
(``message/rfc822``), which is another message. Each provider walks its own
shape of the part tree under this rule; the parity tests pin them equal.
"""

from __future__ import annotations

from typing import Final

HTML_TYPE: Final = "text/html"
#: A message attached to this one: its parts are another message's.
ATTACHED_MESSAGE_TYPE: Final = "message/rfc822"
DEFAULT_CHARSET: Final = "utf-8"


def decode_text(data: bytes, charset: str | None) -> str:
    """Bytes read in their charset; one Python does not know reads as UTF-8.

    Never raises: an undecodable byte becomes U+FFFD.
    """
    try:
        return data.decode(charset or DEFAULT_CHARSET, errors="replace")
    except LookupError:
        return data.decode(DEFAULT_CHARSET, errors="replace")
