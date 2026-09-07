"""Turning a streamed extraction back into a document, for the tests (ADR-273).

Since the ceiling was removed, every renderer produces an asynchronous stream
of chunks rather than one string. A test that asserts on the DOCUMENT still
wants the document, so it collects the stream here — in one place, so a change
in how the chunks are cut never has to be reflected in fifty assertions.

Deliberately NOT a fixture: the tests that need it call it inside an assertion,
often twice in one test (a masked rendering and an unmasked one), and a fixture
would only add indirection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any


async def rows_of(rows: Iterable[Any]) -> AsyncIterator[Any]:
    """Feed a plain list to a renderer that expects a stream.

    Args:
        rows: The rows a repository would have produced.

    Yields:
        Each row, in order.
    """
    for row in rows:
        yield row


async def rendered(chunks: AsyncIterator[str]) -> str:
    """Collect a rendered stream into the document it describes.

    Args:
        chunks: What a streaming renderer yields.

    Returns:
        The whole document.
    """
    return "".join([chunk async for chunk in chunks])


async def body_of(response: Any) -> str:
    """Read a streaming response's body, decompressing it when it says so.

    Args:
        response: A ``StreamingResponse`` a route returned.

    Returns:
        The document the client would have saved. Compression is transport, so
        a test asserting on CONTENT must see through it — and one asserting on
        the compression itself reads ``response.headers`` instead.
    """
    import gzip

    payload = b"".join([chunk async for chunk in response.body_iterator])
    if response.headers.get("content-encoding") == "gzip":
        payload = gzip.decompress(payload)
    return payload.decode("utf-8")


__all__ = ["body_of", "rendered", "rows_of"]
