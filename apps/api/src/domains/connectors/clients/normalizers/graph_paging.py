"""A Graph page token the client rebuilds itself (ADR-369).

Graph pages with ``@odata.nextLink``, a full URL. Handing it to the browser and
following what comes back would let a caller choose where the server sends the
person's token (SSRF). The page token therefore carries only the VALUE of the
skip parameter the link names (``$skip`` or ``$skiptoken``); the client sends
its own request, on its own base URL, with its own parameters plus that value.
A link naming neither cannot be continued and publishes no token.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import parse_qs, urlsplit

#: The skip parameters Graph's listings continue with.
_SKIP_PARAMETERS: Final = ("$skiptoken", "$skip")
#: What a skip value may be made of (Graph's tokens are base64-ish), bounded.
_SKIP_VALUE: Final = re.compile(r"[A-Za-z0-9._~%+/=-]{1,2048}")


def graph_page_token(next_link: str | None) -> str | None:
    """The token of the page after this one, or None when there is none to continue.

    Args:
        next_link: The ``@odata.nextLink`` Graph answered, if any.

    Returns:
        ``"$skip=<value>"`` or ``"$skiptoken=<value>"``; None for no link, or a
        link that continues with neither.
    """
    if not next_link:
        return None
    query = parse_qs(urlsplit(next_link).query)
    for name in _SKIP_PARAMETERS:
        values = query.get(name)
        if values and _SKIP_VALUE.fullmatch(values[0]):
            return f"{name}={values[0]}"
    return None


def graph_page_params(page_token: str | None) -> dict[str, str]:
    """The query parameter a page token names, checked.

    Args:
        page_token: A token :func:`graph_page_token` produced, or None.

    Returns:
        ``{}`` for the first page, ``{"$skip": …}`` or ``{"$skiptoken": …}`` otherwise.

    Raises:
        ValueError: The token is not one this listing produced.
    """
    if not page_token:
        return {}
    name, separator, value = page_token.partition("=")
    if not separator or name not in _SKIP_PARAMETERS or not _SKIP_VALUE.fullmatch(value):
        raise ValueError("Not a page token of this listing: list it again from its first page.")
    return {name: value}


__all__ = ["graph_page_params", "graph_page_token"]
