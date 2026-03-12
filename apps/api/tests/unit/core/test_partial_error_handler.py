"""
Tests unitaires pour PartialErrorHandler.

Ces tests vérifient :
- Classification des erreurs
- Génération de messages utilisateur
- Suggestions de récupération
- Gestion des erreurs partielles

Phase: Multi-Domain Architecture v1.0
"""

import pytest

from src.core.partial_error_handler import (
    DomainErrorContext,
    ErrorCategory,
    ErrorSeverity,
    PartialErrorHandler,
    RecoveryAction,
    create_default_error_handler,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def handler():
    """Create a PartialErrorHandler instance."""
    return PartialErrorHandler()


# =============================================================================
# TESTS - ERROR CLASSIFICATION
# =============================================================================


class TestErrorClassification:
    """Tests for error classification."""

    def test_classify_authentication_error(self, handler):
        """Test classifying authentication errors."""
        error = Exception("token expired")

        context = handler.handle_error("emails", error)

        assert context.category == ErrorCategory.AUTHENTICATION
        assert context.severity == ErrorSeverity.HIGH
        assert context.recovery_action == RecoveryAction.REAUTHENTICATE

    def test_classify_rate_limit_error(self, handler):
        """Test classifying rate limit errors."""
        error = Exception("rate limit exceeded")

        context = handler.handle_error("contacts", error)

        assert context.category == ErrorCategory.RATE_LIMIT
        assert context.recovery_action == RecoveryAction.WAIT

    def test_classify_timeout_error(self, handler):
        """Test classifying timeout errors."""
        error = Exception("connection timeout")

        context = handler.handle_error("calendar", error)

        assert context.category == ErrorCategory.TIMEOUT
        assert context.recovery_action == RecoveryAction.RETRY

    def test_classify_network_error(self, handler):
        """Test classifying network errors."""
        error = Exception("connection refused")

        context = handler.handle_error("drive", error)

        assert context.category == ErrorCategory.NETWORK
        assert context.recovery_action == RecoveryAction.RETRY

    def test_classify_permission_error(self, handler):
        """Test classifying permission errors."""
        error = Exception("403 forbidden")

        context = handler.handle_error("tasks", error)

        assert context.category == ErrorCategory.PERMISSION
        assert context.severity == ErrorSeverity.HIGH
        assert context.recovery_action == RecoveryAction.CONTACT_ADMIN

    def test_classify_not_found_error(self, handler):
        """Test classifying not found errors."""
        error = Exception("resource not found")

        context = handler.handle_error("emails", error)

        assert context.category == ErrorCategory.NOT_FOUND
        assert context.severity == ErrorSeverity.LOW
        assert context.recovery_action == RecoveryAction.MODIFY_QUERY

    def test_classify_validation_error(self, handler):
        """Test classifying validation errors."""
        error = Exception("invalid parameter value")

        context = handler.handle_error("contacts", error)

        assert context.category == ErrorCategory.VALIDATION
        assert context.recovery_action == RecoveryAction.MODIFY_QUERY

    def test_classify_unknown_error(self, handler):
        """Test classifying unknown errors."""
        error = Exception("something completely different")

        context = handler.handle_error("emails", error)

        assert context.category == ErrorCategory.INTERNAL
        assert context.recovery_action == RecoveryAction.RETRY

    def test_classify_by_http_code(self, handler):
        """Test classifying by HTTP status code."""
        # 401 Unauthorized
        context = handler.handle_error("emails", Exception("401"))
        assert context.category == ErrorCategory.AUTHENTICATION

        # 429 Too Many Requests
        context = handler.handle_error("emails", Exception("429"))
        assert context.category == ErrorCategory.RATE_LIMIT

        # 404 Not Found
        context = handler.handle_error("emails", Exception("404"))
        assert context.category == ErrorCategory.NOT_FOUND


# =============================================================================
# TESTS - USER MESSAGES
# =============================================================================


class TestUserMessages:
    """Tests for user message generation."""

    def test_message_contains_domain(self, handler):
        """Test that message contains domain name."""
        error = Exception("error")

        context = handler.handle_error("emails", error)

        assert "Emails" in context.user_message

    def test_message_authentication(self, handler):
        """Test authentication error message."""
        error = Exception("unauthorized")

        context = handler.handle_error("contacts", error)

        assert (
            "connexion" in context.user_message.lower()
            or "reconnect" in context.user_message.lower()
        )

    def test_message_rate_limit(self, handler):
        """Test rate limit error message."""
        error = Exception("rate limit")

        context = handler.handle_error("emails", error)

        assert "limite" in context.user_message.lower()

    def test_message_network(self, handler):
        """Test network error message."""
        error = Exception("connection error")

        context = handler.handle_error("calendar", error)

        assert (
            "connexion" in context.user_message.lower()
            or "contacter" in context.user_message.lower()
        )


# =============================================================================
# TESTS - FORMAT ERROR MESSAGE
# =============================================================================


class TestFormatErrorMessage:
    """Tests for format_error_message method."""

    def test_format_basic_message(self, handler):
        """Test basic message formatting."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="Test error",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=RecoveryAction.RETRY,
            user_message="Test message",
        )

        result = handler.format_error_message(context)

        assert "Test message" in result

    def test_format_with_recovery_action(self, handler):
        """Test message includes recovery suggestion."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="Rate limit",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=RecoveryAction.WAIT,
            retry_after_seconds=60,
            user_message="Limite atteinte",
        )

        result = handler.format_error_message(context, include_recovery=True)

        assert "60" in result or "réessay" in result.lower()

    def test_format_without_recovery(self, handler):
        """Test message without recovery suggestion."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="Test error",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=RecoveryAction.WAIT,
            user_message="Test message",
        )

        result = handler.format_error_message(context, include_recovery=False)

        assert "Test message" in result

    def test_format_with_partial_data(self, handler):
        """Test message mentions partial data availability."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="Test error",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=RecoveryAction.RETRY,
            partial_data_available=True,
            user_message="Test message",
        )

        result = handler.format_error_message(context)

        assert "partiel" in result.lower()


# =============================================================================
# TESTS - PARTIAL RESULTS HEADER
# =============================================================================


class TestPartialResultsHeader:
    """Tests for format_partial_results_header method."""

    def test_format_no_failures(self, handler):
        """Test formatting when no domains failed."""
        result = handler.format_partial_results_header(
            successful_domains=["contacts", "emails"],
            failed_domains=[],
        )

        assert result == ""

    def test_format_with_failures(self, handler):
        """Test formatting with failed domains."""
        result = handler.format_partial_results_header(
            successful_domains=["contacts"],
            failed_domains=["emails"],
        )

        assert "Contacts" in result
        assert "Emails" in result
        assert "Réussi" in result
        assert "Échoué" in result

    def test_format_multiple_failures(self, handler):
        """Test formatting with multiple failures."""
        result = handler.format_partial_results_header(
            successful_domains=["contacts"],
            failed_domains=["emails", "calendar"],
        )

        assert "Emails" in result
        assert "Calendar" in result


# =============================================================================
# TESTS - SHOULD RETRY
# =============================================================================


class TestShouldRetry:
    """Tests for should_retry method."""

    def test_should_retry_for_retry_action(self, handler):
        """Test should_retry returns True for RETRY action."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="timeout",
            recovery_action=RecoveryAction.RETRY,
        )

        assert handler.should_retry(context) is True

    def test_should_retry_for_wait_action(self, handler):
        """Test should_retry returns True for WAIT action."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="rate limit",
            recovery_action=RecoveryAction.WAIT,
        )

        assert handler.should_retry(context) is True

    def test_should_not_retry_for_reauthenticate(self, handler):
        """Test should_retry returns False for REAUTHENTICATE action."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="unauthorized",
            recovery_action=RecoveryAction.REAUTHENTICATE,
        )

        assert handler.should_retry(context) is False

    def test_should_not_retry_for_none(self, handler):
        """Test should_retry returns False for NONE action."""
        context = DomainErrorContext(
            domain="emails",
            error_type="Exception",
            error_message="error",
            recovery_action=RecoveryAction.NONE,
        )

        assert handler.should_retry(context) is False


# =============================================================================
# TESTS - HANDLE ERROR WITH PARTIAL DATA
# =============================================================================


class TestHandleErrorWithPartialData:
    """Tests for handle_error with partial data."""

    def test_handle_with_partial_data(self, handler):
        """Test handling error with partial data available."""
        error = Exception("API error")
        partial_data = {"contacts": [{"name": "Test"}]}

        context = handler.handle_error("emails", error, partial_data)

        assert context.partial_data_available is True

    def test_handle_without_partial_data(self, handler):
        """Test handling error without partial data."""
        error = Exception("API error")

        context = handler.handle_error("emails", error)

        assert context.partial_data_available is False

    def test_handle_with_empty_partial_data(self, handler):
        """Test handling error with empty partial data."""
        error = Exception("API error")
        partial_data = {}

        context = handler.handle_error("emails", error, partial_data)

        assert context.partial_data_available is False


# =============================================================================
# TESTS - RETRY AFTER EXTRACTION
# =============================================================================


class TestRetryAfterExtraction:
    """Tests for retry_after_seconds extraction."""

    def test_default_retry_for_rate_limit(self, handler):
        """Test default retry time for rate limit."""
        error = Exception("rate limit exceeded")

        context = handler.handle_error("emails", error)

        assert context.retry_after_seconds == 60

    def test_no_retry_for_other_errors(self, handler):
        """Test no retry time for non-rate-limit errors."""
        error = Exception("not found")

        context = handler.handle_error("emails", error)

        assert context.retry_after_seconds is None


# =============================================================================
# TESTS - FACTORY FUNCTION
# =============================================================================


class TestCreateDefaultErrorHandler:
    """Tests for create_default_error_handler function."""

    def test_creates_handler(self):
        """Test that factory creates handler."""
        handler = create_default_error_handler()

        assert isinstance(handler, PartialErrorHandler)


# =============================================================================
# TESTS - ERROR CONTEXT MODEL
# =============================================================================


class TestDomainErrorContext:
    """Tests for DomainErrorContext model."""

    def test_create_context(self):
        """Test creating error context."""
        context = DomainErrorContext(
            domain="emails",
            error_type="ValueError",
            error_message="Test error",
        )

        assert context.domain == "emails"
        assert context.error_type == "ValueError"
        assert context.category == ErrorCategory.UNKNOWN
        assert context.severity == ErrorSeverity.MEDIUM
        assert context.timestamp  # Should have default

    def test_context_with_all_fields(self):
        """Test creating context with all fields."""
        context = DomainErrorContext(
            domain="contacts",
            error_type="APIError",
            error_message="API failed",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.HIGH,
            recovery_action=RecoveryAction.WAIT,
            retry_after_seconds=30,
            partial_data_available=True,
            user_message="Please wait",
            technical_details={"code": 429},
        )

        assert context.retry_after_seconds == 30
        assert context.partial_data_available is True
        assert context.technical_details["code"] == 429


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TestErrorClassification",
    "TestUserMessages",
    "TestFormatErrorMessage",
    "TestPartialResultsHeader",
    "TestShouldRetry",
    "TestHandleErrorWithPartialData",
    "TestRetryAfterExtraction",
    "TestCreateDefaultErrorHandler",
    "TestDomainErrorContext",
]
