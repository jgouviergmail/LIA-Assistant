"""What the bytes of a text file say — one door for every reader.

A text file names no encoding. Three writers reach LIA: UTF-8 (nearly
everything), UTF-16 behind its byte-order mark (a Windows « Unicode » export),
and Windows' own letters — what a spreadsheet on a Western Windows desktop
writes when it exports a CSV. Read as UTF-8 with replacement, that last one
lost every accent to U+FFFD.

The rule, in order:

1. a UTF-16 mark is believed;
2. bytes that ARE UTF-8 are UTF-8 (a UTF-8 mark is no letter);
3. bytes that are not are told apart by what they mostly are: a UTF-8 text with
   a damaged byte keeps its letters and loses that byte alone, while a text
   whose accents are all single bytes is read in Windows' letters. Reading a
   UTF-8 text in Windows' letters would turn each of its accents into two wrong
   ones — one damaged byte must never cost the whole text.

No other legacy encoding is guessed: nothing in the bytes tells one from
another, and a wrong guess reads no better than the replacement it replaces.
"""

from __future__ import annotations

import codecs
from typing import Final

#: Windows' own letters, what a Western Windows desktop exports a CSV in.
WINDOWS_LETTERS: Final = "cp1252"
_UTF8: Final = "utf-8-sig"
_UTF16_MARKS: Final = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
_REPLACEMENT: Final = "�"


def decode_text(data: bytes, *, cut: bool = False) -> str:
    """The text a file's bytes say.

    Args:
        data: The file's bytes, or their beginning.
        cut: Whether ``data`` stops at a byte bound rather than at the file's
            end. A letter the bound cut in two is then withheld, and is never a
            reason to read the text otherwise.

    Returns:
        The text. A byte that is no letter in the encoding the text is read in
        becomes U+FFFD; nothing raises.
    """
    whole = not cut
    if data.startswith(_UTF16_MARKS):
        return codecs.getincrementaldecoder("utf-16")("replace").decode(data, final=whole)
    try:
        return codecs.getincrementaldecoder(_UTF8)("strict").decode(data, final=whole)
    except UnicodeDecodeError:
        as_utf8 = codecs.getincrementaldecoder(_UTF8)("replace").decode(data, final=whole)
    if _is_mostly_utf8(as_utf8):
        return as_utf8
    return data.decode(WINDOWS_LETTERS, errors="replace")


def _is_mostly_utf8(as_utf8: str) -> bool:
    """Whether a text read as UTF-8 with replacement was UTF-8 with damage.

    In a UTF-8 text nearly every non-ASCII letter decodes; in a text of
    single-byte accents nearly none does, each one becoming a replacement.

    Args:
        as_utf8: The bytes decoded as UTF-8, undecodable ones replaced.

    Returns:
        True when more non-ASCII letters were read than bytes were replaced.
    """
    damaged = as_utf8.count(_REPLACEMENT)
    beyond_ascii = len(as_utf8) - len(as_utf8.encode("ascii", errors="ignore"))
    return beyond_ascii - damaged > damaged
