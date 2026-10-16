"""What every Fish Audio request shares: its headers, and how a refusal is read.

A refusal is ``{"message", "status"}`` with, on some, an ``x-fish-error-code``
header (``invalid_api_key``, measured 2026-10-13). The message may quote the
request — the text of a line, the name of a voice — so it never travels: a
refusal is read through the voice clients' one rule (:mod:`~src.domains.voice.vendor_refusal`),
the header naming its code.
"""

from __future__ import annotations

from typing import Final

import httpx

from src.domains.voice.vendor_refusal import Refusal, bounded_code

#: The header naming a refusal's cause, when the vendor names one.
VENDOR_CODE_HEADER: Final[str] = "x-fish-error-code"


def auth_headers(api_key: str, *, model: str | None = None) -> dict[str, str]:
    """The headers a request is authenticated with, and the engine it names.

    Args:
        api_key: The account's key.
        model: The engine the ``model`` header selects — a missing or unknown
            one is served AND billed as the vendor's default (measured), so a
            caller that means a model always names it.

    Returns:
        The headers.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    if model is not None:
        headers["model"] = model
    return headers


def refusal_of(response: httpx.Response, *, body_code: object = None) -> Refusal:
    """The facts of ``response``: its status and the vendor's code.

    Args:
        response: The refused response.
        body_code: The ``code`` its JSON body carried, when the caller read one
            (the speech-to-text errors carry it there); the header wins.

    Returns:
        The refusal's facts — never its message.
    """
    code = bounded_code(response.headers.get(VENDOR_CODE_HEADER)) or bounded_code(body_code)
    return Refusal(status=response.status_code, vendor_code=code)


__all__ = ["VENDOR_CODE_HEADER", "auth_headers", "refusal_of"]
