"""
Unit tests for unified exception handling.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 27.1
Created: 2025-11-21
Target: 31% → 80%+ coverage
Module: core/exceptions.py (150 statements)

Security-Critical Module:
- Custom exceptions with automatic logging
- Prometheus metrics integration
- OWASP enumeration prevention
- i18n support for error messages
"""

import uuid
from unittest.mock import patch

import pytest

from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BaseAPIException,
    ExternalServiceError,
    ResourceConflictError,
    ResourceNotFoundError,
    ValidationError,
    raise_admin_required,
    raise_connector_already_exists,
    raise_connector_not_found,
    raise_conversation_not_found,
    raise_email_already_exists,
    raise_google_api_error,
    raise_invalid_credentials,
    raise_invalid_input,
    raise_llm_service_error,
    raise_message_not_found,
    raise_not_found_or_unauthorized,
    raise_oauth_flow_failed,
    raise_oauth_state_mismatch,
    raise_permission_denied,
    raise_session_invalid,
    raise_token_invalid,
    raise_user_inactive,
    raise_user_not_authenticated,
    raise_user_not_found,
    raise_user_not_verified,
)


class TestBaseAPIException:
    """Tests for BaseAPIException with logging and metrics."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_base_exception_401_logs_and_tracks_metrics(
        self, mock_logger, mock_http_errors, mock_client_errors
    ):
        """Test 401 exception logs and tracks client error metrics (Lines 67-94)."""
        # Create 401 exception
        exception = BaseAPIException(
            status_code=401,
            detail="Test authentication error",
            log_level="warning",
            log_event="test_auth_failed",
            user_id="test_user_123",
        )

        # Verify HTTPException properties
        assert exception.status_code == 401
        assert exception.detail == "Test authentication error"

        # Verify logging called
        mock_logger.warning.assert_called_once()

        # Verify metrics tracked
        mock_http_errors.labels.assert_called_once()
        mock_client_errors.labels.assert_called_once_with(error_type="authentication_failed")

    @patch("src.infrastructure.observability.metrics_errors.http_server_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_base_exception_503_tracks_server_error_metrics(
        self, mock_logger, mock_http_errors, mock_server_errors
    ):
        """Test 503 exception tracks server error metrics (Lines 96-99)."""
        # Create 503 exception
        BaseAPIException(
            status_code=503,
            detail="Service unavailable",
            log_level="error",
            log_event="google_api_service_error",
        )

        # Verify metrics tracked
        mock_server_errors.labels.assert_called_once_with(error_type="external_service_error")

    def test_classify_client_error_401_returns_authentication_failed(self):
        """Test 401 classified as authentication_failed (Line 115)."""
        result = BaseAPIException._classify_client_error(401, None)
        assert result == "authentication_failed"

    def test_classify_client_error_403_returns_authorization_failed(self):
        """Test 403 classified as authorization_failed (Line 117)."""
        result = BaseAPIException._classify_client_error(403, None)
        assert result == "authorization_failed"

    def test_classify_client_error_404_returns_resource_not_found(self):
        """Test 404 classified as resource_not_found (Line 119)."""
        result = BaseAPIException._classify_client_error(404, None)
        assert result == "resource_not_found"

    def test_classify_client_error_409_returns_resource_conflict(self):
        """Test 409 classified as resource_conflict (Line 121)."""
        result = BaseAPIException._classify_client_error(409, None)
        assert result == "resource_conflict"

    def test_classify_client_error_429_returns_rate_limit_exceeded(self):
        """Test 429 classified as rate_limit_exceeded (Line 123)."""
        result = BaseAPIException._classify_client_error(429, None)
        assert result == "rate_limit_exceeded"

    def test_classify_client_error_400_returns_validation_failed(self):
        """Test 400 classified as validation_failed (Line 125)."""
        result = BaseAPIException._classify_client_error(400, None)
        assert result == "validation_failed"

    def test_classify_client_error_422_returns_validation_failed(self):
        """Test 422 classified as validation_failed (Line 125)."""
        result = BaseAPIException._classify_client_error(422, None)
        assert result == "validation_failed"

    def test_classify_client_error_other_returns_client_error_other(self):
        """Test other 4xx codes classified as client_error_other (Line 127)."""
        result = BaseAPIException._classify_client_error(418, None)  # I'm a teapot
        assert result == "client_error_other"

    def test_classify_server_error_503_with_service_error_log_event(self):
        """Test 503 with service_error log event (Lines 142-144)."""
        result = BaseAPIException._classify_server_error(503, "google_api_service_error")
        assert result == "external_service_error"

    def test_classify_server_error_503_without_service_error_returns_unavailable(self):
        """Test 503 without service_error returns service_unavailable (Line 145)."""
        result = BaseAPIException._classify_server_error(503, None)
        assert result == "service_unavailable"

    def test_classify_server_error_504_returns_timeout_error(self):
        """Test 504 classified as timeout_error (Line 147)."""
        result = BaseAPIException._classify_server_error(504, None)
        assert result == "timeout_error"

    def test_classify_server_error_500_with_database_log_event(self):
        """Test 500 with database in log_event (Lines 151-152)."""
        result = BaseAPIException._classify_server_error(500, "database_connection_error")
        assert result == "database_error"

    def test_classify_server_error_500_with_llm_log_event(self):
        """Test 500 with llm in log_event (Lines 153-154)."""
        result = BaseAPIException._classify_server_error(500, "llm_api_timeout")
        assert result == "llm_service_error"

    def test_classify_server_error_500_other_returns_internal_server_error(self):
        """Test 500 other returns internal_server_error (Line 155)."""
        result = BaseAPIException._classify_server_error(500, "unknown_error")
        assert result == "internal_server_error"

    def test_classify_server_error_other_returns_server_error_other(self):
        """Test other 5xx codes (Line 157)."""
        result = BaseAPIException._classify_server_error(502, None)
        assert result == "server_error_other"


class TestAuthenticationError:
    """Tests for AuthenticationError (401)."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_authentication_error_defaults(self, mock_logger, mock_http_errors, mock_client_errors):
        """Test AuthenticationError with default message (Lines 163-170)."""
        exc = AuthenticationError()

        assert exc.status_code == 401
        assert exc.detail == "Invalid credentials"

    def test_raise_invalid_credentials_no_email(self):
        """Test raise_invalid_credentials without email (Lines 330-343)."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise_invalid_credentials()

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"

    def test_raise_invalid_credentials_with_email(self):
        """Test raise_invalid_credentials with email for logging."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise_invalid_credentials(email="user@example.com")

        assert exc_info.value.status_code == 401

    def test_raise_token_invalid(self):
        """Test raise_token_invalid (Lines 346-359)."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise_token_invalid("access")

        assert exc_info.value.status_code == 401
        assert "access" in exc_info.value.detail

    def test_raise_session_invalid(self):
        """Test raise_session_invalid (Lines 362-369)."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise_session_invalid()

        assert exc_info.value.status_code == 401
        assert "session" in exc_info.value.detail.lower()

    def test_raise_user_not_authenticated(self):
        """Test raise_user_not_authenticated (Lines 372-379)."""
        with pytest.raises(AuthenticationError) as exc_info:
            raise_user_not_authenticated()

        assert exc_info.value.status_code == 401
        assert "authentication" in exc_info.value.detail.lower()


class TestAuthorizationError:
    """Tests for AuthorizationError (403)."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_authorization_error_defaults(self, mock_logger, mock_http_errors, mock_client_errors):
        """Test AuthorizationError with default message (Lines 176-187)."""
        exc = AuthorizationError()

        assert exc.status_code == 403
        assert "not authorized" in exc.detail.lower()

    def test_raise_permission_denied_basic(self):
        """Test raise_permission_denied basic (Lines 382-415)."""
        with pytest.raises(AuthorizationError) as exc_info:
            raise_permission_denied()

        assert exc_info.value.status_code == 403

    def test_raise_permission_denied_with_action_and_resource(self):
        """Test raise_permission_denied with action and resource (Lines 402-403)."""
        with pytest.raises(AuthorizationError) as exc_info:
            raise_permission_denied(action="delete", resource_type="connector")

        assert exc_info.value.status_code == 403
        assert "delete" in exc_info.value.detail
        assert "connector" in exc_info.value.detail

    def test_raise_permission_denied_with_all_params(self):
        """Test raise_permission_denied with audit logging (Lines 406-413)."""
        user_id = uuid.uuid4()
        resource_id = uuid.uuid4()

        with pytest.raises(AuthorizationError) as exc_info:
            raise_permission_denied(
                action="read",
                resource_type="conversation",
                user_id=user_id,
                resource_id=resource_id,
            )

        assert exc_info.value.status_code == 403

    def test_raise_admin_required(self):
        """Test raise_admin_required (Lines 418-429)."""
        user_id = uuid.uuid4()

        with pytest.raises(AuthorizationError) as exc_info:
            raise_admin_required(user_id)

        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    def test_raise_user_inactive(self):
        """Test raise_user_inactive (Lines 432-445)."""
        user_id = uuid.uuid4()

        with pytest.raises(AuthorizationError) as exc_info:
            raise_user_inactive(user_id)

        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    def test_raise_user_not_verified(self):
        """Test raise_user_not_verified (Lines 448-461)."""
        user_id = uuid.uuid4()

        with pytest.raises(AuthorizationError) as exc_info:
            raise_user_not_verified(user_id)

        assert exc_info.value.status_code == 403
        assert "verification" in exc_info.value.detail.lower()


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError (404)."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_resource_not_found_error_with_id(
        self, mock_logger, mock_http_errors, mock_client_errors
    ):
        """Test ResourceNotFoundError with resource_id (Lines 193-211)."""
        resource_id = uuid.uuid4()
        exc = ResourceNotFoundError("user", resource_id)

        assert exc.status_code == 404
        assert "user" in exc.detail.lower()

    def test_raise_user_not_found(self):
        """Test raise_user_not_found (Lines 469-482)."""
        user_id = uuid.uuid4()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise_user_not_found(user_id)

        assert exc_info.value.status_code == 404
        assert "user" in exc_info.value.detail.lower()

    def test_raise_connector_not_found(self):
        """Test raise_connector_not_found (Lines 485-498)."""
        connector_id = uuid.uuid4()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise_connector_not_found(connector_id)

        assert exc_info.value.status_code == 404
        assert "connector" in exc_info.value.detail.lower()

    def test_raise_conversation_not_found(self):
        """Test raise_conversation_not_found (Lines 501-514)."""
        conversation_id = uuid.uuid4()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise_conversation_not_found(conversation_id)

        assert exc_info.value.status_code == 404
        assert "conversation" in exc_info.value.detail.lower()

    def test_raise_message_not_found(self):
        """Test raise_message_not_found (Lines 517-530)."""
        message_id = uuid.uuid4()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise_message_not_found(message_id)

        assert exc_info.value.status_code == 404
        assert "message" in exc_info.value.detail.lower()

    def test_raise_not_found_or_unauthorized_owasp(self):
        """Test raise_not_found_or_unauthorized OWASP pattern (Lines 690-725)."""
        resource_id = uuid.uuid4()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            raise_not_found_or_unauthorized("connector", resource_id)

        # Verify same error for both "not found" and "not authorized"
        assert exc_info.value.status_code == 404
        assert "connector" in exc_info.value.detail.lower()


class TestResourceConflictError:
    """Tests for ResourceConflictError (409)."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_resource_conflict_error_default_detail(
        self, mock_logger, mock_http_errors, mock_client_errors
    ):
        """Test ResourceConflictError with default detail (Lines 217-232)."""
        exc = ResourceConflictError("user")

        assert exc.status_code == 409
        assert "user" in exc.detail.lower()
        assert "already exists" in exc.detail

    def test_raise_email_already_exists(self):
        """Test raise_email_already_exists (Lines 538-552)."""
        with pytest.raises(ResourceConflictError) as exc_info:
            raise_email_already_exists("test@example.com")

        assert exc_info.value.status_code == 409
        assert "email" in exc_info.value.detail.lower()

    def test_raise_connector_already_exists(self):
        """Test raise_connector_already_exists (Lines 555-574)."""
        user_id = uuid.uuid4()

        with pytest.raises(ResourceConflictError) as exc_info:
            raise_connector_already_exists(user_id, "emails")

        assert exc_info.value.status_code == 409
        assert "emails" in exc_info.value.detail.lower()


class TestValidationError:
    """Tests for ValidationError (400)."""

    @patch("src.infrastructure.observability.metrics_errors.http_client_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_validation_error(self, mock_logger, mock_http_errors, mock_client_errors):
        """Test ValidationError (Lines 238-245)."""
        exc = ValidationError("Invalid email format")

        assert exc.status_code == 400
        assert "invalid" in exc.detail.lower()

    def test_raise_invalid_input(self):
        """Test raise_invalid_input (Lines 582-593)."""
        with pytest.raises(ValidationError) as exc_info:
            raise_invalid_input("Field 'email' is required")

        assert exc_info.value.status_code == 400

    def test_raise_oauth_state_mismatch(self):
        """Test raise_oauth_state_mismatch (Lines 596-614)."""
        user_id = uuid.uuid4()

        with pytest.raises(ValidationError) as exc_info:
            raise_oauth_state_mismatch(user_id, "emails")

        assert exc_info.value.status_code == 400
        assert "state" in exc_info.value.detail.lower()

    def test_raise_oauth_flow_failed(self):
        """Test raise_oauth_flow_failed (Lines 617-635)."""
        with pytest.raises(ValidationError) as exc_info:
            raise_oauth_flow_failed("emails", "invalid_grant")

        assert exc_info.value.status_code == 400
        assert "oauth" in exc_info.value.detail.lower()


class TestExternalServiceError:
    """Tests for ExternalServiceError (503)."""

    @patch("src.infrastructure.observability.metrics_errors.external_service_timeouts_total")
    @patch("src.infrastructure.observability.metrics_errors.external_service_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_server_errors_total")
    @patch("src.infrastructure.observability.metrics_errors.http_errors_total")
    @patch("src.core.exceptions.logger")
    def test_external_service_error_with_timeout(
        self,
        mock_logger,
        mock_http_errors,
        mock_server_errors,
        mock_service_errors,
        mock_timeouts,
    ):
        """Test ExternalServiceError with timeout tracking (Lines 251-281)."""
        exc = ExternalServiceError(
            service_name="google_api",
            detail="Connection timeout",
            error_type="timeout",
        )

        assert exc.status_code == 503

        # Verify service error metrics tracked
        mock_service_errors.labels.assert_called_once_with(
            service_name="google_api", error_type="timeout"
        )

        # Verify timeout metrics tracked separately
        mock_timeouts.labels.assert_called_once_with(service_name="google_api")

    def test_infer_error_type_timeout(self):
        """Test _infer_error_type with timeout (Lines 307-308)."""
        result = ExternalServiceError._infer_error_type("Connection timeout")
        assert result == "timeout"

    def test_infer_error_type_timed_out(self):
        """Test _infer_error_type with timed out (Line 307)."""
        result = ExternalServiceError._infer_error_type("Request timed out")
        assert result == "timeout"

    def test_infer_error_type_unauthorized(self):
        """Test _infer_error_type with unauthorized (Lines 309-310)."""
        result = ExternalServiceError._infer_error_type("Unauthorized access")
        assert result == "unauthorized"

    def test_infer_error_type_forbidden(self):
        """Test _infer_error_type with forbidden (Line 309)."""
        result = ExternalServiceError._infer_error_type("Forbidden")
        assert result == "unauthorized"

    def test_infer_error_type_rate_limit(self):
        """Test _infer_error_type with rate limit (Lines 311-312)."""
        result = ExternalServiceError._infer_error_type("Rate limit exceeded")
        assert result == "rate_limit"

    def test_infer_error_type_too_many_requests(self):
        """Test _infer_error_type with too many requests (Line 311)."""
        result = ExternalServiceError._infer_error_type("Too many requests")
        assert result == "rate_limit"

    def test_infer_error_type_not_found(self):
        """Test _infer_error_type with not found (Lines 313-314)."""
        result = ExternalServiceError._infer_error_type("Resource not found")
        assert result == "not_found"

    def test_infer_error_type_api_error(self):
        """Test _infer_error_type with api error (Lines 315-320)."""
        result = ExternalServiceError._infer_error_type("API error occurred")
        assert result == "api_error"

    def test_infer_error_type_server_error(self):
        """Test _infer_error_type with server error (Line 317)."""
        result = ExternalServiceError._infer_error_type("Internal server error")
        assert result == "api_error"

    def test_infer_error_type_service_unavailable(self):
        """Test _infer_error_type with service unavailable (Line 318)."""
        result = ExternalServiceError._infer_error_type("Service unavailable")
        assert result == "api_error"

    def test_infer_error_type_unknown(self):
        """Test _infer_error_type with unknown error (Lines 302-303, 322)."""
        result = ExternalServiceError._infer_error_type(None)
        assert result == "unknown"

        result = ExternalServiceError._infer_error_type("Unknown error")
        assert result == "unknown"

    def test_raise_google_api_error(self):
        """Test raise_google_api_error (Lines 643-661)."""
        with pytest.raises(ExternalServiceError) as exc_info:
            raise_google_api_error("api_error", "Quota exceeded")

        assert exc_info.value.status_code == 503

    def test_raise_llm_service_error(self):
        """Test raise_llm_service_error (Lines 664-682)."""
        with pytest.raises(ExternalServiceError) as exc_info:
            raise_llm_service_error("gpt-4.1-mini", "Model overloaded")

        assert exc_info.value.status_code == 503
        assert "llm" in exc_info.value.detail.lower()
