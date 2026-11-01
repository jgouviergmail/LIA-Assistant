"""How the workbench refuses (ADR-369).

Every refusal names itself with a stable code (``detail.code``) the web app
tells in the reader's language; a number the reader needs (a bound, a wait)
travels beside it. Built on the central taxonomy (rule #18: never a raw
``HTTPException``) and kept in the domain, like the radio's and the e-mail
share's raisers, because ``core/exceptions.py`` is size-frozen.

A provider failure becomes a refusal by its TYPE and its status code, never by
the words of its message (ADR-303). The classification knows whether the failed
call was an ACT: a send whose answer was lost may have left, so it is « outcome
unknown » — never « unavailable, try again », which would invite the second
send ADR-221 forbids. Whether a failure could have reached the provider is
decided by ``infrastructure/utils/request_outcome``, the one definition the
model and connector retry policies already share.
"""

from __future__ import annotations

import math
from typing import Any, Final, NoReturn

import httpx
from fastapi import status

from src.core.exceptions import (
    AuthenticationError,
    BaseAPIException,
    ConnectorAPIError,
    ConnectorTokenExpiredError,
    RateLimitError,
)
from src.domains.connectors.clients.apple_imap import ImapMessageNotFoundError
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentNotFoundError,
    EmailAttachmentTooLargeError,
)
from src.domains.connectors.clients.mail_folders import (
    MailFolderAmbiguousError,
    MailFolderLookupError,
)
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
    MailboxOperationUnavailableError,
)
from src.domains.connectors.clients.normalizers.contact_values import ContactValuesRefused
from src.domains.connectors.errors import ConnectorRevokedError
from src.infrastructure.resilience import CircuitBreakerError
from src.infrastructure.utils.request_outcome import never_reached_the_server, outcome_unknown

#: The tool's category has no active provider (D6: drawn in « To connect »).
NOT_CONNECTED: Final = "not_connected"
#: The provider's authorisation must be given again.
RECONNECT_REQUIRED: Final = "reconnect_required"
#: The provider, or our own throttle, asks to wait (``retry_after`` beside it).
PROVIDER_RATE_LIMITED: Final = "provider_rate_limited"
#: The provider could not be reached, or did not answer usefully.
PROVIDER_UNAVAILABLE: Final = "provider_unavailable"
#: The item no longer exists (deleted, moved, sent) since it was listed.
ITEM_GONE: Final = "item_gone"
#: An id the provider minted for one reading only has expired (re-list).
STALE_HANDLE: Final = "stale_handle"
#: The item changed since it was read (an etag, a draft revision).
CONFLICT: Final = "conflict"
#: A name the provider already holds: a label has no revision, so a 409 on its
#: write means nothing else.
NAME_TAKEN: Final = "name_taken"
#: Larger than what is served or carried (``max_bytes`` beside it).
TOO_LARGE: Final = "too_large"
#: A recipient address cannot be read (``index`` beside it).
INVALID_RECIPIENT: Final = "invalid_recipient"
#: This submission was already made (``outcome``: done | pending | unknown).
ALREADY_SUBMITTED: Final = "already_submitted"
#: The act may have happened: its answer was lost (never sent again by itself).
OUTCOME_UNKNOWN: Final = "outcome_unknown"
#: The active provider has no such operation (the descriptor says so too).
NOT_SUPPORTED_BY_PROVIDER: Final = "not_supported_by_provider"
#: The provider answered and refused the request (a permission, a limit, a value).
PROVIDER_REFUSED: Final = "provider_refused"
#: The request could not be carried out as given (refused before any call).
INVALID_REQUEST: Final = "invalid_request"

#: What each refusal answers — and the one vocabulary the web app translates.
_STATUSES: Final[dict[str, int]] = {
    NOT_CONNECTED: status.HTTP_409_CONFLICT,
    RECONNECT_REQUIRED: status.HTTP_409_CONFLICT,
    PROVIDER_RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    PROVIDER_UNAVAILABLE: status.HTTP_502_BAD_GATEWAY,
    ITEM_GONE: status.HTTP_404_NOT_FOUND,
    STALE_HANDLE: status.HTTP_409_CONFLICT,
    CONFLICT: status.HTTP_409_CONFLICT,
    NAME_TAKEN: status.HTTP_409_CONFLICT,
    TOO_LARGE: status.HTTP_413_CONTENT_TOO_LARGE,
    INVALID_RECIPIENT: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ALREADY_SUBMITTED: status.HTTP_409_CONFLICT,
    OUTCOME_UNKNOWN: status.HTTP_504_GATEWAY_TIMEOUT,
    NOT_SUPPORTED_BY_PROVIDER: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PROVIDER_REFUSED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_CONTENT,
}
WORKBENCH_CODES: Final[frozenset[str]] = frozenset(_STATUSES)

#: Client failures that name what happened by their type.
_TYPED: Final[tuple[tuple[type[BaseException], str], ...]] = (
    # A connector revoked meanwhile (the Hue remote refresh finds it gone): it
    # is no longer connected — never « reconnect », ADR-134 never nags a revoke.
    (ConnectorRevokedError, NOT_CONNECTED),
    (ConnectorTokenExpiredError, RECONNECT_REQUIRED),
    (AuthenticationError, RECONNECT_REQUIRED),
    (MailboxDraftNotFoundError, ITEM_GONE),
    (MailboxDraftChangedError, CONFLICT),
    (MailboxFolderUnavailableError, NOT_SUPPORTED_BY_PROVIDER),
    (MailboxOperationUnavailableError, NOT_SUPPORTED_BY_PROVIDER),
    (EmailAttachmentNotFoundError, ITEM_GONE),
    # An iCloud id naming no message (Gmail and Graph answer 404 for the same).
    (ImapMessageNotFoundError, ITEM_GONE),
    (EmailAttachmentAmbiguousError, STALE_HANDLE),
    # A folder of the pane: two now answering to its name, or gone since.
    (MailFolderAmbiguousError, CONFLICT),
    (MailFolderLookupError, ITEM_GONE),
)


def refuse(code: str, **detail: Any) -> NoReturn:
    """Refuse with a stable code.

    Args:
        code: One of this module's codes.
        **detail: Facts the reader needs beside the code (``retry_after``,
            ``max_bytes``, ``outcome``, ``index``); ``retry_after`` also becomes
            the RFC ``Retry-After`` header.

    Raises:
        BaseAPIException: With ``detail = {"code": code, **detail}``.
    """
    raise _refusal(code, detail)


def refusal_for(error: BaseException, *, act: bool) -> tuple[str, dict[str, Any]]:
    """The refusal a provider failure amounts to.

    Args:
        error: What the client raised.
        act: Whether the failed call could change something at the provider
            (a send, a create, a write) — then a lost answer is an unknown
            outcome rather than an unavailability.

    Returns:
        The code and the facts that travel beside it.
    """
    already = refusal_code_of(error)
    if already is not None and isinstance(error, BaseAPIException):
        # Classified once, where the call was made: never re-read.
        facts: dict[str, Any] = dict(error.detail) if isinstance(error.detail, dict) else {}
        facts.pop("code", None)
        return already, facts
    named = _named_refusal(error)
    if named is not None:
        return named
    if act and _may_have_acted(error):
        # A lost answer, or a failure nothing classifies: the act may have
        # happened, and saying otherwise would invite a second one.
        return OUTCOME_UNKNOWN, {}
    retry_after = _retry_after_of(error)
    return PROVIDER_UNAVAILABLE, {"retry_after": retry_after} if retry_after else {}


def _named_refusal(error: BaseException) -> tuple[str, dict[str, Any]] | None:
    """The refusal a failure names by its TYPE or its answered status, if it does."""
    for kind, code in _TYPED:
        if isinstance(error, kind):
            return code, {}
    if isinstance(error, EmailAttachmentTooLargeError):
        return TOO_LARGE, {"max_bytes": error.max_bytes}
    if isinstance(error, ContactValuesRefused):
        # A list the provider cannot hold, refused whole: the page says its bound.
        return NOT_SUPPORTED_BY_PROVIDER, {"bound": error.bound, "field": error.field}
    if isinstance(error, RateLimitError):
        return PROVIDER_RATE_LIMITED, {"retry_after": error.retry_after}
    if isinstance(error, ConnectorAPIError):
        return _answered(error.upstream_status_code), {}
    if isinstance(error, httpx.HTTPStatusError):
        # A client that raises httpx's own errors (the Hue bridge): it answered.
        return _http_answer(error.response)
    if isinstance(error, CircuitBreakerError):
        # The breaker refused before anything was sent: never an unknown outcome.
        wait = math.ceil(error.retry_after) if error.retry_after else None
        return PROVIDER_UNAVAILABLE, {"retry_after": wait} if wait else {}
    if isinstance(error, ValueError):
        # Refused by the client before any call (an unreadable value).
        return INVALID_REQUEST, {}
    return None


def _http_answer(response: httpx.Response) -> tuple[str, dict[str, Any]]:
    """The refusal an answered HTTP status amounts to; a throttle keeps its wait."""
    code = _answered(response.status_code)
    wait = _seconds(response.headers.get("Retry-After"))
    return code, {"retry_after": wait} if code == PROVIDER_RATE_LIMITED and wait else {}


def refusal_code_of(error: BaseException) -> str | None:
    """The workbench code an exception already carries, if it is one of ours."""
    detail = getattr(error, "detail", None) if isinstance(error, BaseAPIException) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and code in WORKBENCH_CODES else None


def refuse_provider_failure(error: BaseException, *, act: bool) -> NoReturn:
    """Raise the refusal ``error`` amounts to, chained to it.

    Args:
        error: What the client raised.
        act: See :func:`refusal_for`.

    Raises:
        BaseAPIException: The classified refusal.
    """
    code, detail = refusal_for(error, act=act)
    raise _refusal(code, detail, cause=type(error).__name__) from error


def _refusal(code: str, detail: dict[str, Any], *, cause: str | None = None) -> BaseAPIException:
    status_code = _STATUSES[code]
    retry_after = detail.get("retry_after")
    return BaseAPIException(
        status_code=status_code,
        detail={"code": code, **detail},
        log_level="info" if status_code < 500 else "warning",
        log_event="workbench_refused",
        headers={"Retry-After": str(int(retry_after))} if retry_after else None,
        refusal=code,
        error_type=cause,
    )


def _answered(status_code: int) -> str:
    """The refusal an answered provider status amounts to."""
    if status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_410_GONE):
        return ITEM_GONE
    if status_code in (status.HTTP_409_CONFLICT, status.HTTP_412_PRECONDITION_FAILED):
        return CONFLICT
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return RECONNECT_REQUIRED
    if status_code == status.HTTP_413_CONTENT_TOO_LARGE:
        return TOO_LARGE
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return PROVIDER_RATE_LIMITED
    if status.HTTP_400_BAD_REQUEST <= status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
        return PROVIDER_REFUSED
    return PROVIDER_UNAVAILABLE


def _may_have_acted(error: BaseException) -> bool:
    """Whether the provider may have carried out the act despite the failure.

    No for a request that never left; yes for a lost answer; no for a failure
    the client reported as an answer or a refusal of its own (an exhausted
    5xx loop, an open breaker); yes for anything nothing classifies.
    """
    if never_reached_the_server(error):
        return False
    if outcome_unknown(error):
        return True
    return not isinstance(error, BaseAPIException)


def _retry_after_of(error: BaseException) -> int | None:
    headers = getattr(error, "headers", None) or {}
    return _seconds(headers.get("Retry-After") if isinstance(headers, dict) else None)


def _seconds(value: object) -> int | None:
    """A ``Retry-After`` given in seconds; None for anything else (an HTTP date included)."""
    return int(value) if isinstance(value, str) and value.isdigit() else None


__all__ = [
    "ALREADY_SUBMITTED",
    "CONFLICT",
    "INVALID_RECIPIENT",
    "INVALID_REQUEST",
    "ITEM_GONE",
    "NOT_CONNECTED",
    "NOT_SUPPORTED_BY_PROVIDER",
    "OUTCOME_UNKNOWN",
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_REFUSED",
    "PROVIDER_UNAVAILABLE",
    "RECONNECT_REQUIRED",
    "STALE_HANDLE",
    "TOO_LARGE",
    "WORKBENCH_CODES",
    "refusal_for",
    "refuse",
    "refuse_provider_failure",
]
