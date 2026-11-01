"""A provider id as ONE segment of a URL path — never a reshaped path (ADR-369).

An id reaches a client from a browser or a model. Interpolated raw, ``a/../b``,
``x?y`` or ``x#y`` aim the person's own token at another endpoint of their
account. Quoted, a segment of exactly ``.`` or ``..`` would still be folded
away by the HTTP client's dot-segment removal (httpx applies RFC 3986 §5.2.4 —
measured: ``/me/contacts/..`` leaves as ``/me``), and an empty one names the
collection instead of an item. No provider mints such an id, so it is refused
like an id that names nothing: a 404, before any request.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.models import ConnectorType

#: Segments that do not survive as themselves in a URL path.
_FOLDED: Final = frozenset({"", ".", ".."})


def path_segment(value: str, *, connector_type: ConnectorType, safe: str = "") -> str:
    """``value`` quoted as one path segment.

    Args:
        value: A provider id (a task list, a task, a contact…).
        connector_type: The provider asked, named in the refusal.
        safe: Characters kept as they are (``@`` for Google's ``@default`` —
            a path character that cannot reshape a path).

    Returns:
        The segment, every reserved character percent-encoded.

    Raises:
        ConnectorAPIError: 404, the value names nothing (never quoted back).
    """
    if value in _FOLDED:
        raise ConnectorAPIError(
            connector_type=connector_type.value,
            status_code=404,
            detail=f"{connector_type.value} API error: no such item",
        )
    return quote(value, safe=safe)
