"""The Cloudflare Turnstile bot check at the password doors (ADR-364).

A sign-up, a password sign-in and a password-reset request each carry the
token the browser's Turnstile widget produced, in ``TURNSTILE_TOKEN_HEADER``;
the server asks Cloudflare about it before anything else runs. The widget alone
protects nothing: a script posting to the API never runs it, which is exactly
the 2026-10-23 attack.

Owner decision 2026-10-24 — when Cloudflare cannot answer, ONLY the sign-in
proceeds: a person must always be able to reach their account, while a new
account and a reset e-mail can wait. A token Cloudflare REFUSED is refused at
every door, the sign-in included: that answer is about the visitor, an outage
is not. An outage usually reaches the browser too — the widget cannot load and
the sign-in arrives WITHOUT a token, like a script's. Only the server's own view
tells them apart: such a sign-in proceeds only while Cloudflare does not answer
THIS server either (``_without_token``).

The check is read at call time (``TURNSTILE_ENABLED``) and is the operator's
own widget: off, nothing here runs. Cloudflare's TESTING keys decide only
outside production (to try the chain end to end); in production their answer is
no usable answer — a testing secret there voids the check, and like a mistyped
secret it must never lock the sign-in.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import NoReturn
from urllib.parse import urlsplit

import structlog
from fastapi import Request, status

from src.core.client_ip import UNKNOWN_CLIENT_IP, resolve_client_ip
from src.core.config import settings
from src.core.constants import (
    TURNSTILE_FAILED_ERROR_CODE,
    TURNSTILE_REACHABILITY_TTL_SECONDS,
    TURNSTILE_TOKEN_HEADER,
    TURNSTILE_TOKEN_MAX_LENGTH,
    TURNSTILE_UNAVAILABLE_ERROR_CODE,
)
from src.core.exceptions import AuthorizationError, BaseAPIException
from src.infrastructure.external.turnstile_client import SiteverifyAnswer, TurnstileClient
from src.infrastructure.observability.metrics_auth import turnstile_verifications_total
from src.infrastructure.utils.single_flight import run_single_flight

logger = structlog.get_logger(__name__)


class TurnstileAction(StrEnum):
    """The door a token was produced for — the widget's ``action``, checked on return."""

    LOGIN = "login"
    REGISTER = "register"
    PASSWORD_RESET = "password_reset"


class TurnstileOutcome(StrEnum):
    """What one check concluded — the ``outcome`` of ``turnstile_verifications_total``."""

    PASSED = "passed"
    MISSING = "missing"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


#: The doors that open when Cloudflare cannot answer (owner decision 2026-10-24).
PROCEEDS_WHEN_UNAVAILABLE: frozenset[TurnstileAction] = frozenset({TurnstileAction.LOGIN})

# Every series exists from the start, at zero: `increase()` then sees the first
# outage, and a panel reads a healthy 0 rather than « No data ».
for _action in TurnstileAction:
    for _outcome in TurnstileOutcome:
        turnstile_verifications_total.labels(action=_action.value, outcome=_outcome.value)


@dataclass(slots=True)
class Reachability:
    """Whether Cloudflare answered this worker lately, as every call observed it.

    Not per-request state: it is the one fact a request without a token cannot
    prove for itself, so it is shared by every check of the worker.
    """

    answered: bool | None = None
    at: float = 0.0

    def current(self, now: float) -> bool | None:
        """The verdict while it stands (``TURNSTILE_REACHABILITY_TTL_SECONDS``), else None."""
        if self.answered is None or now - self.at > TURNSTILE_REACHABILITY_TTL_SECONDS:
            return None
        return self.answered

    def record(self, answered: bool, now: float) -> None:
        """Keep what the latest call to Cloudflare saw."""
        self.answered = answered
        self.at = now


_reachability = Reachability()
_PROBE_KEY = ("turnstile", "reachability")


class TurnstileUnavailableError(BaseAPIException):
    """Cloudflare could not answer, and this door does not open without it — 503.

    A class of its own rather than a 403: the visitor did nothing wrong, and the
    interface says « try again in a moment », not « verification failed ».
    """

    def __init__(self, action: TurnstileAction) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": TURNSTILE_UNAVAILABLE_ERROR_CODE},
            log_level="warning",
            log_event="turnstile_unavailable_refusal",
            action=action.value,
        )


def classify(
    answer: SiteverifyAnswer | None,
    *,
    action: TurnstileAction,
    expected_hostnames: frozenset[str],
    honour_testing_keys: bool,
) -> TurnstileOutcome:
    """What Cloudflare's answer means for this door.

    A passed token must also have been produced for THIS door and on THIS
    instance's pages, as Cloudflare recommends checking. An answer given under
    Cloudflare's testing keys carries neither, so only its verdict can be read —
    and only where testing keys may decide.

    Args:
        answer: Cloudflare's answer, or None when it could not answer.
        action: The door being crossed.
        expected_hostnames: The hosts of the instance's own pages (lowercase).
        honour_testing_keys: Whether a testing-key answer may decide (outside
            production); otherwise it is no usable answer.

    Returns:
        The outcome.
    """
    if answer is None:
        return TurnstileOutcome.UNAVAILABLE
    if answer.testing_key:
        if not honour_testing_keys:
            return TurnstileOutcome.UNAVAILABLE
        return TurnstileOutcome.PASSED if answer.success else TurnstileOutcome.REJECTED
    if not answer.success or answer.action != action.value:
        return TurnstileOutcome.REJECTED
    if expected_hostnames and (answer.hostname or "").lower() not in expected_hostnames:
        return TurnstileOutcome.REJECTED
    return TurnstileOutcome.PASSED


def _host_of(url: str) -> str | None:
    # An origin nobody can parse names no page of ours; it must not fail the door.
    with suppress(ValueError):
        host = urlsplit(url).hostname
        return host.lower() if host else None
    return None


def _expected_hostnames() -> frozenset[str]:
    """The hosts of the instance's own pages: ``FRONTEND_URL`` and every browser
    origin allowed to call the API with its cookie (``CORS_ORIGINS``)."""
    origins = settings.cors_origins
    urls = [settings.frontend_url, *(origins if isinstance(origins, list) else [origins])]
    return frozenset(host for host in map(_host_of, urls) if host)


def _client() -> TurnstileClient:
    return TurnstileClient(
        secret=settings.turnstile_secret_key,
        timeout=settings.turnstile_verify_timeout_seconds,
    )


async def _probe() -> bool:
    """Ask Cloudflare about an EMPTY token: it answers ``missing-input-response``
    when it is up (measured 2026-10-24), and nothing when it is not."""
    answered = await _client().verify("", remote_ip=None) is not None
    _reachability.record(answered, monotonic())
    return answered


async def _without_token(action: TurnstileAction) -> TurnstileOutcome:
    """A request that never ran the widget: refused — unless it is a sign-in and
    Cloudflare does not answer this server either, the outage its browser met.

    A verdict younger than ``TURNSTILE_REACHABILITY_TTL_SECONDS`` stands (any
    call to Cloudflare refreshes it); otherwise one question is asked, shared by
    every concurrent caller.
    """
    if action not in PROCEEDS_WHEN_UNAVAILABLE:
        return TurnstileOutcome.MISSING
    answered = _reachability.current(monotonic())
    if answered is None:
        answered = (await run_single_flight(_PROBE_KEY, _probe)).value
    return TurnstileOutcome.MISSING if answered else TurnstileOutcome.UNAVAILABLE


async def _check(request: Request, action: TurnstileAction) -> TurnstileOutcome:
    token = request.headers.get(TURNSTILE_TOKEN_HEADER, "").strip()
    if not token:
        return await _without_token(action)
    if len(token) > TURNSTILE_TOKEN_MAX_LENGTH:
        return TurnstileOutcome.REJECTED
    client_ip = resolve_client_ip(request)
    answer = await _client().verify(
        token, remote_ip=None if client_ip == UNKNOWN_CLIENT_IP else client_ip
    )
    _reachability.record(answer is not None, monotonic())
    honour_testing_keys = not settings.is_production
    outcome = classify(
        answer,
        action=action,
        expected_hostnames=_expected_hostnames(),
        honour_testing_keys=honour_testing_keys,
    )
    if answer is not None and answer.testing_key and not honour_testing_keys:
        logger.error("turnstile_testing_key_in_production", action=action.value)
    if outcome is TurnstileOutcome.REJECTED and answer is not None:
        logger.info(
            "turnstile_rejected",
            action=action.value,
            error_codes=list(answer.error_codes),
            action_matches=answer.action == action.value,
        )
    return outcome


def _refuse(action: TurnstileAction, outcome: TurnstileOutcome) -> NoReturn:
    if outcome is TurnstileOutcome.UNAVAILABLE:
        raise TurnstileUnavailableError(action)
    raise AuthorizationError(
        detail={"error": TURNSTILE_FAILED_ERROR_CODE},
        action=action.value,
        outcome=outcome.value,
    )


def require_turnstile(action: TurnstileAction) -> Callable[[Request], Awaitable[None]]:
    """The FastAPI dependency checking one door's token.

    Args:
        action: The door it guards.

    Returns:
        A dependency that returns when the request may proceed and raises a
        typed refusal otherwise (403 ``turnstile_failed``, 503
        ``turnstile_unavailable``).
    """

    async def _dependency(request: Request) -> None:
        if not settings.turnstile_enabled:
            return
        outcome = await _check(request, action)
        turnstile_verifications_total.labels(action=action.value, outcome=outcome.value).inc()
        if outcome is TurnstileOutcome.PASSED:
            return
        if outcome is TurnstileOutcome.UNAVAILABLE and action in PROCEEDS_WHEN_UNAVAILABLE:
            logger.warning("turnstile_unavailable_sign_in_proceeds", action=action.value)
            return
        _refuse(action, outcome)

    return _dependency
