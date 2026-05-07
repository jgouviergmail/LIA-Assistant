"""Exceptions for the STT abstraction layer."""

from __future__ import annotations


class STTProviderError(Exception):
    """Raised when a remote STT provider call fails.

    Carries a stable error code so the WebSocket handler can map it to the
    matching close code / frontend i18n key without parsing the message.

    Recognised codes (kept in sync with the WebSocket handler):
    - ``elevenlabs_api_key_missing``: factory cannot find the provider key.
    - ``provider_timeout``: HTTP timeout while calling the provider.
    - ``provider_rate_limited``: HTTP 429 from the provider; ``retry_after``
      may carry the seconds suggested by the ``Retry-After`` header.
    - ``provider_http_error``: any other 4xx/5xx response.
    - ``provider_invalid_response``: 200 OK but the body did not match the
      expected schema.
    """

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        retry_after_seconds: float | None = None,
        details: object | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.retry_after_seconds = retry_after_seconds
        self.details = details
