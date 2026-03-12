"""
Unit tests for OAuth callback error handlers.

Tests for:
- OAuthCallbackErrorCode enum
- classify_oauth_callback_error() function
- handle_oauth_callback_error_redirect() function

Phase: Robustesse & Gestion d'Erreurs
Created: 2025-12-24
"""

from unittest.mock import patch

from fastapi.responses import RedirectResponse

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.core.oauth.exceptions import (
    OAuthFlowError,
    OAuthProviderError,
    OAuthStateValidationError,
    OAuthTokenExchangeError,
)
from src.domains.connectors.error_handlers import (
    OAuthCallbackErrorCode,
    classify_oauth_callback_error,
    handle_oauth_callback_error_redirect,
)


class TestOAuthCallbackErrorCode:
    """Tests for OAuthCallbackErrorCode enum."""

    def test_enum_values_are_strings(self):
        """Test all enum values are valid string error codes."""
        assert OAuthCallbackErrorCode.OAUTH_FAILED == "oauth_failed"
        assert OAuthCallbackErrorCode.INVALID_STATE == "invalid_state"
        assert OAuthCallbackErrorCode.USER_NOT_FOUND == "user_not_found"
        assert OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED == "token_exchange_failed"
        assert OAuthCallbackErrorCode.CONNECTOR_DISABLED == "connector_disabled"
        assert OAuthCallbackErrorCode.USER_INACTIVE == "user_inactive"

    def test_enum_has_all_expected_values(self):
        """Test enum has all expected error codes."""
        expected_codes = {
            "oauth_failed",
            "invalid_state",
            "user_not_found",
            "token_exchange_failed",
            "connector_disabled",
            "user_inactive",
        }
        actual_codes = {code.value for code in OAuthCallbackErrorCode}
        assert actual_codes == expected_codes


class TestClassifyOAuthCallbackError:
    """Tests for classify_oauth_callback_error() function."""

    def test_classifies_state_validation_error(self):
        """Test OAuthStateValidationError returns INVALID_STATE."""
        error = OAuthStateValidationError("Invalid CSRF token")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.INVALID_STATE

    def test_classifies_token_exchange_error(self):
        """Test OAuthTokenExchangeError returns TOKEN_EXCHANGE_FAILED."""
        error = OAuthTokenExchangeError("Failed to exchange code for tokens")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED

    def test_classifies_provider_error(self):
        """Test OAuthProviderError returns TOKEN_EXCHANGE_FAILED."""
        error = OAuthProviderError("Google API error")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED

    def test_classifies_user_not_found_resource_error(self):
        """Test ResourceNotFoundError with resource_type='user' returns USER_NOT_FOUND."""
        error = ResourceNotFoundError("User not found")
        error.resource_type = "user"
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.USER_NOT_FOUND

    def test_classifies_other_resource_not_found(self):
        """Test ResourceNotFoundError without user type returns OAUTH_FAILED."""
        error = ResourceNotFoundError("Connector not found")
        # No resource_type attribute
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.OAUTH_FAILED

    def test_classifies_authorization_error(self):
        """Test AuthorizationError returns USER_INACTIVE."""
        error = AuthorizationError("User is inactive")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.USER_INACTIVE

    def test_classifies_generic_oauth_flow_error(self):
        """Test generic OAuthFlowError returns OAUTH_FAILED."""
        error = OAuthFlowError("Something went wrong")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.OAUTH_FAILED

    def test_classifies_oauth_flow_error_with_invalid_state_code(self):
        """Test OAuthFlowError with error_code='invalid_state' returns INVALID_STATE."""
        error = OAuthFlowError("State mismatch")
        error.error_code = "invalid_state"
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.INVALID_STATE

    def test_classifies_oauth_flow_error_with_token_exchange_code(self):
        """Test OAuthFlowError with error_code='token_exchange_failed' returns TOKEN_EXCHANGE_FAILED."""
        error = OAuthFlowError("Token exchange failed")
        error.error_code = "token_exchange_failed"
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.TOKEN_EXCHANGE_FAILED

    def test_classifies_generic_exception(self):
        """Test generic Exception returns OAUTH_FAILED."""
        error = Exception("Something unexpected happened")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.OAUTH_FAILED

    def test_classifies_value_error(self):
        """Test ValueError returns OAUTH_FAILED."""
        error = ValueError("Invalid value")
        result = classify_oauth_callback_error(error)
        assert result == OAuthCallbackErrorCode.OAUTH_FAILED


class TestHandleOAuthCallbackErrorRedirect:
    """Tests for handle_oauth_callback_error_redirect() function."""

    @patch("src.domains.connectors.error_handlers.settings")
    def test_returns_redirect_response(self, mock_settings):
        """Test returns a RedirectResponse object."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = OAuthStateValidationError("Invalid state")

        result = handle_oauth_callback_error_redirect(error, "gmail")

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @patch("src.domains.connectors.error_handlers.settings")
    def test_redirect_url_contains_error_code(self, mock_settings):
        """Test redirect URL contains the error code."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = OAuthStateValidationError("Invalid state")

        result = handle_oauth_callback_error_redirect(error, "gmail")

        # Check redirect URL contains error parameter
        location = result.headers.get("location", "")
        assert "connector_error=invalid_state" in location

    @patch("src.domains.connectors.error_handlers.settings")
    def test_redirect_to_settings_page(self, mock_settings):
        """Test redirects to dashboard settings page."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = Exception("Error")

        result = handle_oauth_callback_error_redirect(error, "google_calendar")

        location = result.headers.get("location", "")
        assert "http://localhost:3000/dashboard/settings" in location

    @patch("src.domains.connectors.error_handlers.settings")
    def test_uses_provided_error_code(self, mock_settings):
        """Test uses provided error_code when specified."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = Exception("Some error")

        result = handle_oauth_callback_error_redirect(
            error,
            "gmail",
            error_code=OAuthCallbackErrorCode.CONNECTOR_DISABLED,
        )

        location = result.headers.get("location", "")
        assert "connector_error=connector_disabled" in location

    @patch("src.domains.connectors.error_handlers.settings")
    def test_classifies_error_when_code_not_provided(self, mock_settings):
        """Test classifies error when error_code is None."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = OAuthTokenExchangeError("Token exchange failed")

        result = handle_oauth_callback_error_redirect(error, "gmail")

        location = result.headers.get("location", "")
        assert "connector_error=token_exchange_failed" in location

    @patch("src.domains.connectors.error_handlers.settings")
    @patch("src.domains.connectors.error_handlers.logger")
    def test_logs_error_with_context(self, mock_logger, mock_settings):
        """Test logs error with full context."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = OAuthStateValidationError("Invalid CSRF token")

        handle_oauth_callback_error_redirect(error, "google_contacts")

        # Verify logging was called with correct context
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args.kwargs
        assert call_kwargs["error_type"] == "OAuthStateValidationError"
        assert call_kwargs["error_code"] == "invalid_state"

    @patch("src.domains.connectors.error_handlers.settings")
    def test_handles_different_connector_types(self, mock_settings):
        """Test handles various connector type names."""
        mock_settings.frontend_url = "http://localhost:3000"
        error = Exception("Error")

        for connector_type in ["gmail", "google_contacts", "google_calendar", "google_drive"]:
            result = handle_oauth_callback_error_redirect(error, connector_type)
            assert isinstance(result, RedirectResponse)


class TestClassifyHttpError:
    """Tests for classify_http_error() function."""

    def test_classifies_401_as_oauth(self):
        """Test 401 returns oauth category."""
        from src.domains.connectors.error_handlers import classify_http_error

        result = classify_http_error(401)
        assert result["error_category"] == "oauth"
        assert result["retryable"] is False
        assert result["requires_user_action"] is True
        assert result["suggested_action"] == "reconnect_oauth"

    def test_classifies_403_rate_limit(self):
        """Test 403 with rate limit error code returns rate_limit category."""
        from src.domains.connectors.error_handlers import classify_http_error

        result = classify_http_error(403, {"error": {"code": "userRateLimitExceeded"}})
        assert result["error_category"] == "rate_limit"
        assert result["retryable"] is True

    def test_classifies_403_permission(self):
        """Test 403 without rate limit returns permission category."""
        from src.domains.connectors.error_handlers import classify_http_error

        result = classify_http_error(403, {"error": {"code": "insufficientPermissions"}})
        assert result["error_category"] == "permission"
        assert result["retryable"] is False
        assert result["suggested_action"] == "request_additional_scopes"

    def test_classifies_429_as_rate_limit(self):
        """Test 429 returns rate_limit category."""
        from src.domains.connectors.error_handlers import classify_http_error

        result = classify_http_error(429)
        assert result["error_category"] == "rate_limit"
        assert result["retryable"] is True
        assert result["suggested_action"] == "wait_and_retry"

    def test_classifies_5xx_as_server(self):
        """Test 5xx returns server category."""
        from src.domains.connectors.error_handlers import classify_http_error

        for status_code in [500, 502, 503, 504]:
            result = classify_http_error(status_code)
            assert result["error_category"] == "server"
            assert result["retryable"] is True
            assert result["suggested_action"] == "retry_with_backoff"

    def test_classifies_4xx_as_client(self):
        """Test other 4xx returns client category."""
        from src.domains.connectors.error_handlers import classify_http_error

        for status_code in [400, 404, 405, 409]:
            result = classify_http_error(status_code)
            assert result["error_category"] == "client"
            assert result["retryable"] is False

    def test_classifies_unknown_as_unknown(self):
        """Test unknown status codes return unknown category."""
        from src.domains.connectors.error_handlers import classify_http_error

        result = classify_http_error(100)  # Informational - unusual
        assert result["error_category"] == "unknown"
        assert result["suggested_action"] == "contact_support"
