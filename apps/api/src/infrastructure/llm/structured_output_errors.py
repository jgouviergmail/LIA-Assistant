"""What a structured-output call raises (ADR-220, ADR-275).

Extracted from ``structured_output.py`` (file-size ratchet), the way
``strict_schema`` was: the error taxonomy is self-contained, and every caller
keeps importing it from ``structured_output``, which re-exports it.

The classes share one hierarchy: callers of ``StructuredOutputError`` keep
handling every failure, while a retry owner can distinguish an unusable answer
from a truncated answer or a deterministic provider refusal.
"""

from __future__ import annotations

import httpx


class StructuredOutputError(Exception):
    """Raised when structured output generation or parsing fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        schema_name: str,
        raw_output: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.schema_name = schema_name
        self.raw_output = raw_output
        self.original_error = original_error


class StructuredOutputTruncatedError(StructuredOutputError):
    """The provider stopped at its output budget (ADR-275).

    The payload is incomplete by the provider's own account, and the same
    prompt cannot complete it — so nothing retries this one, and no rescue may
    close it into a shorter, valid-looking object.
    """


class StructuredOutputRefusedError(StructuredOutputError):
    """The provider refused a request that cannot succeed unchanged."""

    def __init__(
        self, *, status_code: int, provider: str, schema_name: str, original_error: Exception
    ) -> None:
        super().__init__(
            f"{provider} refused structured output with HTTP {status_code}",
            provider=provider,
            schema_name=schema_name,
            original_error=original_error,
        )
        self.status_code = status_code


def _provider_status(error: BaseException) -> tuple[int | None, str | None]:
    """The HTTP status and retry hint the provider attached to the failure, if any.

    Walks ``__cause__`` because langchain re-raises a provider failure wrapped
    (``ChatGoogleGenerativeAIError`` around google-genai's ``ClientError``, whose
    status is its ``code``): the outermost status found decides, as in
    ``embedding_retry_reason``.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        if isinstance(response, httpx.Response):
            return response.status_code, response.headers.get("x-should-retry")
        for attribute in ("status_code", "code"):
            status = getattr(current, attribute, None)
            if isinstance(status, int) and not isinstance(status, bool):
                return status, None
        current = current.__cause__
    return None, None


def raise_if_provider_refused(error: Exception, provider: str, schema_name: str) -> None:
    """Preserve deterministic HTTP failures before a fallback can erase them.

    SDKs expose a status and response, so no provider message is parsed; the
    status is read through the wrappers langchain adds (``_provider_status``).
    Honor the provider's explicit retry hint, and retain timeout, conflict,
    early-data and rate-limit responses as retryable rather than treating every
    4xx alike.
    """
    status, hint = _provider_status(error)
    if status is None or hint == "true":
        return
    if hint != "false" and (not 400 <= status < 500 or status in {408, 409, 425, 429}):
        return
    raise StructuredOutputRefusedError(
        status_code=status, provider=provider, schema_name=schema_name, original_error=error
    ) from error
