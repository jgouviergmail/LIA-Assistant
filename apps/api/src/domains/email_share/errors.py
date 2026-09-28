"""How sending by e-mail can be refused (ADR-321).

Every refusal names itself with a stable code (``detail.code``) the web app
translates in the person's language; a number the reader needs (the largest
file a road accepts) travels beside it. Built on the central taxonomy (rule
#18: never a raw ``HTTPException``) and kept in the domain, like the
bookmarks' and the attachments' raisers, because ``core/exceptions.py`` is
size-frozen. Each refusal is counted where it is raised, so no path can refuse
without the operator seeing it.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Final, NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException
from src.infrastructure.observability.metrics_email_share import email_shares_total

#: The file is not one of the person's live generated files (any more).
FILE_GONE: Final = "email_share_file_gone"
#: The file is larger than the road it would take accepts.
TOO_LARGE: Final = "email_share_too_large"
#: A mailbox send names no recipient.
NO_RECIPIENT: Final = "email_share_no_recipient"
#: LIA's relay only writes to the account's own verified address.
RECIPIENTS_LOCKED: Final = "email_share_recipients_locked"
#: No mailbox is connected and the account's address is not verified.
UNAVAILABLE: Final = "email_share_unavailable"
#: The mailbox refused its credentials: it must be reconnected.
RECONNECT: Final = "email_share_mailbox_reconnect"
#: The mailbox or the relay answered, and refused the message.
REFUSED: Final = "email_share_refused"
#: The mailbox or the relay could not be reached.
FAILED: Final = "email_share_failed"

#: What each refusal answers, and under which outcome it is counted.
_REFUSALS: Final[dict[str, tuple[int, str]]] = {
    FILE_GONE: (status.HTTP_404_NOT_FOUND, "file_gone"),
    TOO_LARGE: (status.HTTP_413_CONTENT_TOO_LARGE, "too_large"),
    NO_RECIPIENT: (status.HTTP_400_BAD_REQUEST, "no_recipient"),
    RECIPIENTS_LOCKED: (status.HTTP_409_CONFLICT, "recipients_locked"),
    UNAVAILABLE: (status.HTTP_409_CONFLICT, "unavailable"),
    RECONNECT: (status.HTTP_409_CONFLICT, "reconnect"),
    REFUSED: (status.HTTP_502_BAD_GATEWAY, "refused"),
    FAILED: (status.HTTP_503_SERVICE_UNAVAILABLE, "failed"),
}


def count(route: str, outcome: str) -> None:
    """Count one send attempt; a metric never decides a send.

    Args:
        route: ``mailbox``, ``relay`` or ``none``.
        outcome: What happened (see the counter's documented values).
    """
    # Best-effort: a registry hiccup must not turn a sent e-mail into an error.
    with suppress(Exception):
        email_shares_total.labels(route=route, outcome=outcome).inc()


def refuse(code: str, *, route: str, **detail: Any) -> NoReturn:
    """Refuse a send with its stable code, counted.

    Args:
        code: One of this module's codes.
        route: The road the send would have taken (``none`` before one is known).
        **detail: Facts the reader needs beside the code (``max_bytes``).

    Raises:
        BaseAPIException: With ``detail = {"code": code, **detail}``.
    """
    status_code, outcome = _REFUSALS[code]
    count(route, outcome)
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code, **detail},
        log_level="info" if status_code < 500 else "warning",
        log_event="email_share_refused",
        refusal=code,
        route=route,
    )
