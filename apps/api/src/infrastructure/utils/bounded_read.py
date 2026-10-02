"""Read a streamed HTTP body under a byte ceiling that holds during decompression.

``response.content`` buffers whatever the remote sends, and a ceiling counted on
DECODED chunks fires too late: httpx 0.28 inflates a whole raw chunk before anyone
can count it — measured, a 6 KiB zstd body allocated 400 MiB and a 200 KiB gzip one
142 MiB under a 1 MiB ceiling. A host we trust not to be malicious is not a host we
trust to be finite: every fetch of a URL somebody else chose reads its body here
(``pinned_stream``'s callers, held by a guard), and so do the vendor downloads that
adopted it (avatars, generated images, the typed-choice client). This reader takes
the RAW bytes and decodes them itself: no decoded piece is ever larger than what is
left of the ceiling, plus one byte.

It decodes what httpx advertises in this deployment (``ACCEPTED_ENCODINGS``, held
equal by a test; ``x-gzip`` read as ``gzip``, as RFC 9110 asks) and refuses anything
else — or two encodings stacked — before a byte is decoded. A refusal, a corrupt body and a body cut before its compressed
stream ended are all ``httpx.DecodingError``: every caller already handles a
transport failure, and that is what such a body is. What follows the end of a gzip
or deflate stream is ignored, as httpx ignores it — and no longer read at all.
"""

from __future__ import annotations

import zlib
from compression import zstd
from typing import Final, Protocol

import httpx

#: The content codings this reader decodes under its ceiling, in the order they
#: are offered. ``identity`` is implicit.
ACCEPTED_ENCODINGS: Final = ("gzip", "deflate", "zstd")
#: The ``Accept-Encoding`` value a request whose body this reader takes sends,
#: so an honest server never answers in a coding the reader refuses.
ACCEPT_ENCODING_HEADER: Final = ", ".join(ACCEPTED_ENCODINGS)


class BodyTooLargeError(Exception):
    """The body exceeded the caller's ceiling; the transfer was abandoned.

    Attributes:
        max_bytes: The ceiling that was exceeded.
    """

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"Response body exceeds {max_bytes} bytes")
        self.max_bytes = max_bytes


class UnsupportedEncodingError(httpx.DecodingError):
    """The body is encoded in a way this reader cannot decode under a ceiling.

    Attributes:
        encoding: The ``Content-Encoding`` that was refused, normalised.
    """

    def __init__(self, encoding: str, *, request: httpx.Request) -> None:
        super().__init__(f"Unsupported content encoding: {encoding}", request=request)
        self.encoding = encoding


class _Decoder(Protocol):
    """Decodes a coding incrementally, never producing more than it is asked for."""

    @property
    def done(self) -> bool:
        """Whether the stream has ended: whatever follows it decodes to nothing."""

    def push(self, data: bytes) -> None:
        """Hand over the next raw bytes."""

    def pull(self, limit: int) -> bytes:
        """Return at most ``limit`` decoded bytes; ``b""`` when it needs more input."""

    def finish(self) -> None:
        """Raise ``httpx.DecodingError`` when the raw body ended mid-stream."""


class _Identity:
    done = False

    def __init__(self) -> None:
        self._pending = b""

    def push(self, data: bytes) -> None:
        self._pending += data

    def pull(self, limit: int) -> bytes:
        piece, self._pending = self._pending[:limit], self._pending[limit:]
        return piece

    def finish(self) -> None:
        """An identity body cannot end mid-stream."""


class _Zlib:
    """gzip, or deflate — zlib-wrapped, else raw, decided on its first bytes as httpx does.

    Only the first compressed stream is read, as httpx does; what follows its end
    is ignored.
    """

    def __init__(self, wbits: int, *, raw_fallback: bool) -> None:
        self._inflater = zlib.decompressobj(wbits)
        self._raw_fallback = raw_fallback
        self._pending = b""
        self._started = False

    @property
    def done(self) -> bool:
        return self._inflater.eof

    def push(self, data: bytes) -> None:
        self._pending += data
        self._started = self._started or bool(data)

    def pull(self, limit: int) -> bytes:
        if self._inflater.eof or not self._pending:
            return b""
        data, self._pending = self._pending, b""
        try:
            piece = self._inflater.decompress(data, limit)
        except zlib.error as exc:
            if not self._raw_fallback:
                raise httpx.DecodingError(f"corrupt compressed body: {exc}") from exc
            # A server that says « deflate » may send it raw (RFC 1951) rather
            # than zlib-wrapped: httpx accepts both, and so does this reader.
            self._raw_fallback = False
            self._inflater = zlib.decompressobj(-zlib.MAX_WBITS)
            return self._retry(data, limit)
        self._raw_fallback = False
        self._pending = self._inflater.unconsumed_tail
        return piece

    def _retry(self, data: bytes, limit: int) -> bytes:
        try:
            piece = self._inflater.decompress(data, limit)
        except zlib.error as exc:
            raise httpx.DecodingError(f"corrupt compressed body: {exc}") from exc
        self._pending = self._inflater.unconsumed_tail
        return piece

    def finish(self) -> None:
        if self._started and not self._inflater.eof:
            raise httpx.DecodingError("the body ended before its compressed stream did")


class _Zstd:
    """zstd, every frame of it in turn, as httpx reads it."""

    #: Another frame may always follow.
    done = False

    def __init__(self) -> None:
        self._decompressor = zstd.ZstdDecompressor()
        self._pending = b""
        self._started = False

    def push(self, data: bytes) -> None:
        self._pending += data
        self._started = self._started or bool(data)

    def pull(self, limit: int) -> bytes:
        while True:
            if self._decompressor.eof:
                rest = self._decompressor.unused_data + self._pending
                if not rest:
                    return b""
                self._decompressor = zstd.ZstdDecompressor()
                self._pending = rest
            if not self._pending and self._decompressor.needs_input:
                return b""
            data, self._pending = self._pending, b""
            try:
                piece = self._decompressor.decompress(data, limit)
            except zstd.ZstdError as exc:
                raise httpx.DecodingError(f"corrupt compressed body: {exc}") from exc
            if piece:
                return piece
            if not self._decompressor.eof:
                return b""

    def finish(self) -> None:
        if self._started and not self._decompressor.eof:
            raise httpx.DecodingError("the body ended before its compressed stream did")


def _decoder_for(response: httpx.Response) -> _Decoder:
    """The decoder for ``response``'s ``Content-Encoding``, refusing what it cannot bound."""
    codings = [
        value.strip().lower()
        for value in response.headers.get_list("content-encoding", split_commas=True)
    ]
    codings = [coding for coding in codings if coding and coding != "identity"]
    if not codings:
        return _Identity()
    if len(codings) > 1:
        raise UnsupportedEncodingError(",".join(codings), request=response.request)
    coding = codings[0]
    # RFC 9110 §8.4.1.3: a recipient SHOULD read "x-gzip" as "gzip".
    if coding in ("gzip", "x-gzip"):
        return _Zlib(zlib.MAX_WBITS | 16, raw_fallback=False)
    if coding == "deflate":
        return _Zlib(zlib.MAX_WBITS, raw_fallback=True)
    if coding == "zstd":
        return _Zstd()
    raise UnsupportedEncodingError(coding, request=response.request)


async def read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream ``response``'s body, decoding it without ever holding more than the ceiling.

    Args:
        response: An open streaming response. One whose body was already read
            — built in memory, as a test transport does — is decoded already,
            so only the ceiling's verdict is left to give.
        max_bytes: Hard ceiling on the DECODED size.

    Returns:
        The complete, decoded body.

    Raises:
        BodyTooLargeError: As soon as the decoded size exceeds ``max_bytes``.
        UnsupportedEncodingError: The ``Content-Encoding`` is neither one of
            ``ACCEPTED_ENCODINGS`` nor ``x-gzip``, or names more than one;
            nothing was decoded.
        httpx.DecodingError: The compressed body is corrupt, or ended before
            its stream did.
    """
    decoder = _decoder_for(response)
    if response.is_stream_consumed:
        # httpx read and decoded it whole already; a stream consumed WITHOUT
        # being read raises ``httpx.ResponseNotRead`` here, a caller's bug.
        content = response.content
        if len(content) > max_bytes:
            raise BodyTooLargeError(max_bytes)
        return content
    body = bytearray()
    async for raw in response.aiter_raw():
        decoder.push(raw)
        while piece := decoder.pull(max_bytes - len(body) + 1):
            body += piece
            if len(body) > max_bytes:
                raise BodyTooLargeError(max_bytes)
        if decoder.done:
            # What follows the compressed stream decodes to nothing — httpx
            # ignores it too — and is never held: a sender that keeps sending
            # is not read any further (the caller's response closes the rest).
            break
    decoder.finish()
    return bytes(body)
