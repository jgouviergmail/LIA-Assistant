"""Serving a document that is too large to hold in memory (ADR-273).

The five register extractions render their file as they read it, so what
reaches the client is a stream of text chunks rather than one string. This
module is the last step of all five: it turns those chunks into an attachment,
and compresses them on the way out when the client says it can decompress.

Compression is not an optimisation here, it is what makes a complete
extraction usable. LIA is self-hosted, typically behind a domestic uplink, and
these files are pure text — JSON Lines, CSV, Markdown — which gzip reduces by
roughly an order of magnitude. The compressor is incremental: it holds one
window (32 KiB), never the document, so it composes with the cursor upstream
rather than undoing it.

Two decisions worth stating:

- **the file NAME does not change.** ``Content-Encoding`` is a transport
  concern: the browser decompresses and saves ``lia-actions-20260907.jsonl``,
  exactly the file the header describes. A ``.gz`` artefact would be a
  different contract, and the reader who attaches an extraction to a complaint
  should not have to explain an extra extension.
- **it is negotiated, never imposed.** A client that does not offer gzip — or
  refuses it with ``q=0`` — gets the plain text it asked for, and ``Vary``
  says the answer depends on that header so no cache confuses the two.
"""

from __future__ import annotations

import zlib
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from src.core.constants import EXPORT_GZIP_COMPRESSION_LEVEL

#: ``zlib`` speaks deflate by default; 16 + MAX_WBITS asks it for a gzip
#: wrapper, which is what ``Content-Encoding: gzip`` names.
_GZIP_WBITS = 16 + zlib.MAX_WBITS


def accepts_gzip(accept_encoding: str | None) -> bool:
    """Whether the client offered to decompress gzip.

    Args:
        accept_encoding: The request's ``Accept-Encoding`` header, or None.

    Returns:
        True when gzip is offered and not explicitly refused. ``q=0`` is a
        refusal, and reading the header as a substring search would take it
        for an offer.
    """
    if not accept_encoding:
        return False
    for part in accept_encoding.split(","):
        token, _, parameters = part.strip().partition(";")
        if token.strip().lower() not in ("gzip", "*"):
            continue
        quality = parameters.strip().lower()
        if quality.startswith("q=") and _is_zero(quality[2:]):
            continue
        return True
    return False


def _is_zero(value: str) -> bool:
    """Whether a quality value refuses the encoding outright."""
    try:
        return float(value) == 0.0
    except ValueError:
        return False


async def _as_bytes(chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Encode the rendered text, chunk by chunk."""
    async for chunk in chunks:
        yield chunk.encode("utf-8")


async def _gzipped(chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Compress the rendered text as it is produced.

    Args:
        chunks: The renderer's output.

    Yields:
        Compressed blocks. The compressor decides when it has enough to emit,
        so a chunk in does not mean a block out; the final flush closes the
        gzip member.
    """
    compressor = zlib.compressobj(EXPORT_GZIP_COMPRESSION_LEVEL, zlib.DEFLATED, _GZIP_WBITS)
    async for chunk in chunks:
        block = compressor.compress(chunk.encode("utf-8"))
        if block:
            yield block
    tail = compressor.flush()
    if tail:
        yield tail


def attachment_stream(
    chunks: AsyncIterator[str],
    *,
    filename: str,
    media_type: str,
    accept_encoding: str | None,
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Serve rendered text as a downloadable attachment, compressed if possible.

    Args:
        chunks: The document, rendered progressively.
        filename: The name the reader's browser saves it under.
        media_type: The document's own type — never ``application/gzip``:
            compression here is transport, and the file stays what it is.
        accept_encoding: The request's ``Accept-Encoding`` header.
        extra_headers: Headers the caller publishes alongside, such as the
            exact row count.

    Returns:
        The streaming response.
    """
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Vary": "Accept-Encoding",
        **(extra_headers or {}),
    }
    if accepts_gzip(accept_encoding):
        headers["Content-Encoding"] = "gzip"
        return StreamingResponse(_gzipped(chunks), media_type=media_type, headers=headers)
    return StreamingResponse(_as_bytes(chunks), media_type=media_type, headers=headers)


__all__ = ["accepts_gzip", "attachment_stream"]
