"""Collecting a streamed register read, for the integration tests (ADR-273).

The repositories return an asynchronous stream since the ceiling was removed.
These tests assert on the SET a query matches — which rows, in which order —
so they collect it. The collection is deliberate and local: what production
does instead is hand each row to a renderer and forget it, which is the whole
point and is exactly what the memory property below measures.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


async def collected(rows: AsyncIterator[Any]) -> list[Any]:
    """Every row a streamed read produced, in order.

    Args:
        rows: What a repository's ``stream_for_export`` returned.

    Returns:
        The rows.
    """
    return [row async for row in rows]


__all__ = ["collected"]
