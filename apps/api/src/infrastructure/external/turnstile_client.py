"""Client for Cloudflare Turnstile's siteverify, from the server's side (ADR-364).

Two failures must never be confused, because the sign-in treats them
differently: Cloudflare ANSWERED that a token is bad — the visitor's problem,
always a refusal — and Cloudflare could NOT answer — an outage, which only the
sign-in rides through. So this client never raises: it returns the answer, or
``None`` when no answer came (a transport error, a timeout, a 5xx, Cloudflare's
own ``internal-error``, an unreadable body), after the attempts Cloudflare
recommends under ONE idempotency key.

A vendor's refusal leaves by its facts (ADR-345): the error codes are kept from
Cloudflare's documented set, anything else reads ``other`` — never a body.

An answer given under Cloudflare's TESTING keys says so (``testing_key``): it
carries no ``action`` and names ``example.com`` whatever the page (measured
2026-10-24), so only the gate can decide what it is worth.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from src.core.constants import TURNSTILE_SITEVERIFY_URL, TURNSTILE_VERIFY_ATTEMPTS
from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.utils.retry import retry_async

logger = structlog.get_logger(__name__)

#: Cloudflare's documented siteverify error codes; anything else reads ``other``.
KNOWN_ERROR_CODES = frozenset(
    {
        "missing-input-secret",
        "invalid-input-secret",
        "missing-input-response",
        "invalid-input-response",
        "bad-request",
        "timeout-or-duplicate",
        "internal-error",
    }
)
_RETRYABLE_ERROR_CODE = "internal-error"
#: Codes that blame the SERVER's request, never the visitor's token: read as
#: « no usable answer », or one mistyped secret would refuse every sign-in.
OPERATOR_ERROR_CODES = frozenset({"missing-input-secret", "invalid-input-secret", "bad-request"})
#: The marker Cloudflare puts on an answer given under one of its testing keys.
_TESTING_KEY_MARKER = "result_with_testing_key"


@dataclass(frozen=True, slots=True)
class SiteverifyAnswer:
    """What Cloudflare answered about one token."""

    success: bool
    error_codes: tuple[str, ...]
    hostname: str | None
    action: str | None
    testing_key: bool = False


class _NoAnswer(Exception):
    """Cloudflare did not answer this attempt (retried, then read as an outage)."""


class _OperatorRefused(Exception):
    """Cloudflare refused the server's own request (secret, format): not retried."""


def _bounded_codes(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        code if isinstance(code, str) and code in KNOWN_ERROR_CODES else "other" for code in raw
    )


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _answered_under_testing_key(metadata: Any) -> bool:
    return isinstance(metadata, dict) and metadata.get(_TESTING_KEY_MARKER) is True


class TurnstileClient:
    """Ask Cloudflare whether a Turnstile token is valid."""

    def __init__(
        self,
        *,
        secret: str,
        timeout: float,
        attempts: int = TURNSTILE_VERIFY_ATTEMPTS,
        retry_wait_seconds: float = 0.25,
        url: str = TURNSTILE_SITEVERIFY_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            secret: The operator's Turnstile secret key (never logged).
            timeout: Bound of one whole attempt, in seconds (httpx alone bounds
                each phase apart: connect, write, read).
            attempts: Total attempts, including the first.
            retry_wait_seconds: Wait between two attempts.
            url: The siteverify endpoint.
            transport: Injected transport, for tests.
        """
        self._secret = secret
        self._timeout = timeout
        self._attempts = attempts
        self._retry_wait = retry_wait_seconds
        self._url = url
        self._transport = transport

    async def verify(self, token: str, *, remote_ip: str | None) -> SiteverifyAnswer | None:
        """Validate one token.

        Args:
            token: The widget's response token, as the browser sent it.
            remote_ip: The visitor's address, when known.

        Returns:
            Cloudflare's answer, or None when Cloudflare could not answer.
            Never raises.
        """
        payload: dict[str, str] = {
            "secret": self._secret,
            "response": token,
            "idempotency_key": str(uuid.uuid4()),
        }
        if remote_ip:
            payload["remoteip"] = remote_ip
        try:
            return await retry_async(
                lambda: self._attempt(payload),
                max_retries=self._attempts,
                retryable_exceptions=(_NoAnswer,),
                operation_name="turnstile_siteverify",
                delay_for=lambda _error, _attempt: self._retry_wait,
            )
        except MaxRetriesExceededError as exhausted:
            logger.warning(
                "turnstile_siteverify_unanswered",
                attempts=self._attempts,
                reason=str(exhausted.last_error) if exhausted.last_error else None,
            )
            return None
        except _OperatorRefused as refused:
            logger.error("turnstile_siteverify_refused_the_server", error_codes=str(refused))
            return None

    async def _attempt(self, payload: dict[str, str]) -> SiteverifyAnswer:
        try:
            async with (
                asyncio.timeout(self._timeout),
                httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client,
            ):
                response = await client.post(self._url, json=payload)
        except (httpx.HTTPError, TimeoutError) as error:
            raise _NoAnswer(type(error).__name__) from error
        if response.status_code >= 500:
            raise _NoAnswer(f"status_{response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise _NoAnswer("unreadable_body") from error
        if not isinstance(body, dict):
            raise _NoAnswer("unreadable_body")
        codes = _bounded_codes(body.get("error-codes"))
        if _RETRYABLE_ERROR_CODE in codes:
            raise _NoAnswer(_RETRYABLE_ERROR_CODE)
        if OPERATOR_ERROR_CODES.intersection(codes):
            raise _OperatorRefused(",".join(sorted(OPERATOR_ERROR_CODES.intersection(codes))))
        return SiteverifyAnswer(
            success=body.get("success") is True,
            error_codes=codes,
            hostname=_text_or_none(body.get("hostname")),
            action=_text_or_none(body.get("action")),
            testing_key=_answered_under_testing_key(body.get("metadata")),
        )
