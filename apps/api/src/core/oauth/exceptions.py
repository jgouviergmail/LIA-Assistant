"""OAuth-specific exceptions."""

from typing import Any


class OAuthFlowError(Exception):
    """
    Exception raised during OAuth flow execution.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code
        original_error: Original exception if wrapped
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "oauth_error"
        self.original_error = original_error

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (caused by: {self.original_error})"
        return self.message


class OAuthStateValidationError(OAuthFlowError):
    """Raised when OAuth state token validation fails."""

    def __init__(self, message: str = "Invalid or expired OAuth state token") -> None:
        super().__init__(message, error_code="invalid_state")


class OAuthTokenExchangeError(OAuthFlowError):
    """Raised when token exchange fails."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message, error_code="token_exchange_failed", original_error=original_error)


class OAuthProviderError(OAuthFlowError):
    """Raised when OAuth provider returns an error."""

    def __init__(self, message: str, provider_response: dict[str, Any] | None = None) -> None:
        super().__init__(message, error_code="provider_error")
        self.provider_response = provider_response
