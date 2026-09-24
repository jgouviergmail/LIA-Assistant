"""Read a streamed HTTP body under a byte ceiling, aborting mid-transfer.

``response.content`` buffers whatever the remote sends. A host we trust not to be
malicious is not a host we trust to be finite, so every server-side download of a
body sized by someone else streams through this one reader.
"""

from __future__ import annotations

import httpx


class BodyTooLargeError(Exception):
    """The body exceeded the caller's ceiling; the transfer was abandoned.

    Attributes:
        max_bytes: The ceiling that was exceeded.
    """

    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"Response body exceeds {max_bytes} bytes")
        self.max_bytes = max_bytes


async def read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream ``response``'s body, refusing to hold more than ``max_bytes``.

    Args:
        response: An open streaming response.
        max_bytes: Hard ceiling on the received size.

    Returns:
        The complete body.

    Raises:
        BodyTooLargeError: As soon as the received size exceeds ``max_bytes``.
    """
    chunks: list[bytes] = []
    received = 0
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > max_bytes:
            raise BodyTooLargeError(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)
