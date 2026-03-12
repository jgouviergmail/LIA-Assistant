"""
Unit tests for PII filtering in structured logs.

Tests cover:
- Email detection and pseudonymization
- Phone number detection and masking
- Credit card number detection and masking
- Sensitive field redaction
- Nested structure sanitization
- Token/API key detection
"""

from src.infrastructure.observability.pii_filter import (
    add_pii_filter,
    mask_credit_card,
    mask_phone,
    pseudonymize_email,
    sanitize_dict,
    sanitize_string,
)


class TestEmailPseudonymization:
    """Test email address pseudonymization."""

    def test_pseudonymize_email_generates_hash(self) -> None:
        """Test that email is converted to SHA-256 hash."""
        email = "user@example.com"
        result = pseudonymize_email(email)

        assert result.startswith("email_hash_")
        assert len(result) == 27  # "email_hash_" (11) + 16 hex chars

    def test_pseudonymize_email_is_consistent(self) -> None:
        """Test that same email produces same hash (for correlation)."""
        email = "user@example.com"
        result1 = pseudonymize_email(email)
        result2 = pseudonymize_email(email)

        assert result1 == result2

    def test_pseudonymize_email_different_for_different_emails(self) -> None:
        """Test that different emails produce different hashes."""
        email1 = "user1@example.com"
        email2 = "user2@example.com"
        result1 = pseudonymize_email(email1)
        result2 = pseudonymize_email(email2)

        assert result1 != result2


class TestPhoneMasking:
    """Test phone number masking."""

    def test_mask_phone_with_us_format(self) -> None:
        """Test masking US phone number."""
        phone = "+1 (555) 123-4567"
        result = mask_phone(phone)

        assert result == "***-***-4567"
        assert "555" not in result
        assert "123" not in result

    def test_mask_phone_with_international_format(self) -> None:
        """Test masking international phone number."""
        phone = "+33 6 12 34 56 78"
        result = mask_phone(phone)

        assert result == "***-***-5678"

    def test_mask_phone_with_short_number(self) -> None:
        """Test masking short phone number."""
        phone = "123"
        result = mask_phone(phone)

        assert result == "***-***-****"


class TestCreditCardMasking:
    """Test credit card number masking."""

    def test_mask_credit_card_visa(self) -> None:
        """Test masking Visa card number."""
        card = "4532 1234 5678 9010"
        result = mask_credit_card(card)

        assert result == "****-****-****-9010"
        assert "4532" not in result
        assert "1234" not in result
        assert "5678" not in result

    def test_mask_credit_card_amex(self) -> None:
        """Test masking American Express card number."""
        card = "3782 822463 10005"
        result = mask_credit_card(card)

        assert result.endswith("0005")
        assert "3782" not in result

    def test_mask_credit_card_no_spaces(self) -> None:
        """Test masking card number without spaces."""
        card = "4532123456789010"
        result = mask_credit_card(card)

        assert result == "****-****-****-9010"


class TestStringSanitization:
    """Test string PII sanitization."""

    def test_sanitize_string_with_email(self) -> None:
        """Test email detection in string."""
        text = "Contact user@example.com for support"
        result = sanitize_string(text)

        assert "user@example.com" not in result
        assert "email_hash_" in result

    def test_sanitize_string_with_phone(self) -> None:
        """Test phone number detection in string."""
        text = "Call us at +1-555-123-4567"
        result = sanitize_string(text)

        assert "+1-555-123-4567" not in result
        assert "***-***-4567" in result

    def test_sanitize_string_with_credit_card(self) -> None:
        """Test credit card detection in string."""
        text = "Card ending in 4532 1234 5678 9010"
        result = sanitize_string(text)

        assert "4532 1234 5678 9010" not in result
        assert "****-****-****-9010" in result

    def test_sanitize_string_with_token(self) -> None:
        """Test generic token detection in string."""
        text = "API key: sk_test_4eC39HqLyjWDarjtT1zdp7dc1234567890abcdef"
        result = sanitize_string(text)

        assert "sk_test_4eC39HqLyjWDarjtT1zdp7dc1234567890abcdef" not in result
        assert "[REDACTED_TOKEN]" in result

    def test_sanitize_string_with_multiple_pii(self) -> None:
        """Test detection of multiple PII types in same string."""
        text = "Email: user@test.com, Phone: +1-555-123-4567"
        result = sanitize_string(text)

        assert "user@test.com" not in result
        assert "+1-555-123-4567" not in result
        assert "email_hash_" in result
        assert "***-***-4567" in result


class TestDictSanitization:
    """Test dictionary sanitization."""

    def test_sanitize_dict_with_sensitive_field_names(self) -> None:
        """Test redaction of known sensitive field names."""
        data = {
            "user_id": "123",
            "email": "user@example.com",
            "password": "secret123",
            "api_key": "sk_test_abc123",
        }
        result = sanitize_dict(data)

        assert result["user_id"] == "123"  # Not sensitive
        assert "user@example.com" not in str(result["email"])  # Pseudonymized
        assert result["password"] == "[REDACTED]"  # Redacted
        assert result["api_key"] == "[REDACTED]"  # Redacted

    def test_sanitize_dict_with_nested_dict(self) -> None:
        """Test sanitization of nested dictionaries."""
        data = {
            "user": {
                "email": "user@example.com",
                "password": "secret",
            }
        }
        result = sanitize_dict(data)

        assert "user@example.com" not in str(result["user"]["email"])
        assert result["user"]["password"] == "[REDACTED]"

    def test_sanitize_dict_with_list(self) -> None:
        """Test sanitization of lists containing dictionaries."""
        data = {
            "users": [
                {"email": "user1@example.com", "password": "secret1"},
                {"email": "user2@example.com", "password": "secret2"},
            ]
        }
        result = sanitize_dict(data)

        for user in result["users"]:
            assert "example.com" not in str(user["email"])
            assert user["password"] == "[REDACTED]"

    def test_sanitize_dict_preserves_non_pii(self) -> None:
        """Test that non-PII data is preserved."""
        data = {
            "user_id": "123",
            "username": "johndoe",
            "created_at": "2025-01-01T00:00:00Z",
            "is_active": True,
            "count": 42,
        }
        result = sanitize_dict(data)

        assert result["user_id"] == "123"
        assert result["username"] == "johndoe"
        assert result["created_at"] == "2025-01-01T00:00:00Z"
        assert result["is_active"] is True
        assert result["count"] == 42


class TestStructlogProcessor:
    """Test structlog processor integration."""

    def test_add_pii_filter_processor(self) -> None:
        """Test PII filter as structlog processor."""
        event_dict = {
            "event": "user_login",
            "email": "admin@example.com",
            "password": "super_secret",
            "ip_address": "192.168.1.1",
        }

        result = add_pii_filter(None, "info", event_dict)

        assert result["event"] == "user_login"
        assert "admin@example.com" not in str(result["email"])
        assert "email_hash_" in result["email"]
        assert result["password"] == "[REDACTED]"
        assert result["ip_address"] == "192.168.1.1"  # Not PII in this context

    def test_add_pii_filter_with_exception_info(self) -> None:
        """Test PII filter handles exception info correctly."""
        event_dict = {
            "event": "authentication_failed",
            "email": "user@example.com",
            "exception": "Invalid password",
            "trace_id": "abc123",
        }

        result = add_pii_filter(None, "error", event_dict)

        assert "user@example.com" not in str(result["email"])
        assert result["exception"] == "Invalid password"
        assert result["trace_id"] == "abc123"


class TestCaseSensitivity:
    """Test case-insensitive field name matching."""

    def test_sensitive_field_case_insensitive(self) -> None:
        """Test that field names are matched case-insensitively."""
        data = {
            "PASSWORD": "secret1",
            "Password": "secret2",
            "password": "secret3",
            "API_KEY": "key123",
        }
        result = sanitize_dict(data)

        assert result["PASSWORD"] == "[REDACTED]"
        assert result["Password"] == "[REDACTED]"
        assert result["password"] == "[REDACTED]"
        assert result["API_KEY"] == "[REDACTED]"


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self) -> None:
        """Test sanitization of empty string."""
        result = sanitize_string("")
        assert result == ""

    def test_empty_dict(self) -> None:
        """Test sanitization of empty dictionary."""
        result = sanitize_dict({})
        assert result == {}

    def test_none_values(self) -> None:
        """Test handling of None values."""
        data = {"email": None, "password": None}
        result = sanitize_dict(data)

        # None should be preserved for non-sensitive fields, redacted for sensitive
        assert result["password"] == "[REDACTED]"

    def test_numeric_values(self) -> None:
        """Test that numeric values are preserved."""
        data = {"count": 123, "price": 45.67}
        result = sanitize_dict(data)

        assert result["count"] == 123
        assert result["price"] == 45.67
