"""A multipart/form-data body whose file is read off the event loop (audit AC-035).

httpx reads a synchronous file handed to ``files=`` chunk by chunk ON the event
loop: every chunk of a meeting's audio held the worker's other requests — the SSE
streams included — for as long as the storage took to hand it over. This body
frames exactly the bytes httpx frames for the same form (a test holds the two
equal, byte for byte, escaped names included) and reads a file through
:class:`~src.infrastructure.file_transfer.LocalFileRead`, whose every read runs in
a worker thread and whose close waits for a read still in flight. The file stays
its opener's to close: a body never outlives the request that sends it.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

from src.infrastructure.file_transfer import LocalFileRead

# The WHATWG escaping of a name or filename inside a Content-Disposition, as httpx
# applies it: a quote, a backslash and every control character but ESC.
_PARAM_ESCAPES = {'"': "%22", "\\": "\\\\"} | {
    chr(code): f"%{code:02X}" for code in range(0x20) if code != 0x1B
}
_PARAM_ESCAPE = re.compile("|".join(re.escape(character) for character in _PARAM_ESCAPES))


@dataclass(frozen=True)
class FormFile:
    """The form's one file part: the field it is sent under, its filename and its type."""

    field: str
    filename: str
    content_type: str


@dataclass(frozen=True)
class MultipartUpload:
    """What httpx is handed in place of ``files=``: the framing headers and the body."""

    headers: dict[str, str]
    content: AsyncIterator[bytes]


def multipart_upload(
    fields: Mapping[str, str], file: FormFile, content: bytes | LocalFileRead
) -> MultipartUpload:
    """Frame ``fields`` then ``file`` as httpx would, with a declared length.

    Args:
        fields: The text fields, sent before the file in their mapping order.
        file: How the file part is named and typed.
        content: The file's bytes already in memory, or an opened reader whose
            size at its opening is the size declared and sent.

    Returns:
        The ``Content-Type`` (with a boundary drawn for this upload) and
        ``Content-Length`` headers, and the body to pass as ``content=``.
    """
    boundary = secrets.token_hex(16).encode("ascii")
    head = b"".join(
        b"--%s\r\nContent-Disposition: form-data; %s\r\n\r\n%s\r\n"
        % (boundary, _param("name", name), value.encode())
        for name, value in fields.items()
    )
    disposition = _param("name", file.field)
    if file.filename:
        disposition += b"; " + _param("filename", file.filename)
    head += b"--%s\r\nContent-Disposition: form-data; %s\r\nContent-Type: %s\r\n\r\n" % (
        boundary,
        disposition,
        file.content_type.encode(),
    )
    tail = b"\r\n--%s--\r\n" % boundary
    size = len(content) if isinstance(content, bytes) else content.file_size_bytes
    return MultipartUpload(
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary.decode('ascii')}",
            "Content-Length": str(len(head) + size + len(tail)),
        },
        content=_body(head, content, tail),
    )


def _param(name: str, value: str) -> bytes:
    escaped = _PARAM_ESCAPE.sub(lambda match: _PARAM_ESCAPES[match.group(0)], value)
    return f'{name}="{escaped}"'.encode()


async def _body(head: bytes, content: bytes | LocalFileRead, tail: bytes) -> AsyncIterator[bytes]:
    yield head
    if isinstance(content, bytes):
        yield content
    else:
        async for chunk in _declared_bytes(content):
            yield chunk
    yield tail


async def _declared_bytes(reader: LocalFileRead) -> AsyncIterator[bytes]:
    """Exactly the size the reader declared at its opening: the length the headers announced.

    Raises:
        OSError: The file grew or shrank since it was opened.
    """
    remaining = reader.file_size_bytes
    while True:
        chunk = await reader.read_chunk()
        if len(chunk) > remaining or (not chunk and remaining):
            raise OSError("The file changed while it was being uploaded")
        if not chunk:
            return
        remaining -= len(chunk)
        yield chunk
