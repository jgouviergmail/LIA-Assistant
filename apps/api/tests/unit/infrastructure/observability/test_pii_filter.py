"""
Unit tests for PII (Personally Identifiable Information) filtering module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 24
Created: 2025-11-20
Target: 68.4% → 80%+ coverage
Module: infrastructure/observability/pii_filter.py (57 statements)

Missing Lines to Cover:
- Lines 134-135: pseudonymize_email() - SHA-256 hashing
- Lines 153-156: mask_phone() - Phone masking logic
- Lines 173-176: mask_credit_card() - Credit card masking logic
- Line 189: redact_value() - Redaction logic
- Lines 251-252: sanitize_dict() - Sensitive field redaction
- Lines 256-257: sanitize_dict() - PII field pseudonymization
- Lines 261-262: sanitize_dict() - Phone field masking
- Line 266: sanitize_dict() - Nested dict recursion

Security-Critical Module:
- GDPR compliance (Article 5: Data minimization)
- OWASP Logging best practices
- PII protection for structured logs
"""

import hashlib

from src.infrastructure.observability.pii_filter import (
    add_pii_filter,
    mask_credit_card,
    mask_phone,
    pseudonymize_email,
    redact_value,
    sanitize_dict,
    sanitize_string,
)


class TestPseudonymizeEmail:
    """Tests for email pseudonymization using SHA-256 hash."""

    def test_pseudonymize_email_returns_hash(self):
        """Test that email is hashed with SHA-256 (Lines 134-135)."""
        email = "user@example.com"

        # Lines 134-135 executed: SHA-256 hash + first 16 chars
        result = pseudonymize_email(email)

        # Verify format: "email_hash_" + 16 hex chars
        assert result.startswith("email_hash_")
        assert len(result) == len("email_hash_") + 16

        # Verify hash consistency (same email = same hash)
        result2 = pseudonymize_email(email)
        assert result == result2

        # Verify actual hash value
        expected_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        assert result == f"email_hash_{expected_hash}"

    def test_pseudonymize_email_different_emails_different_hashes(self):
        """Test that different emails produce different hashes."""
        email1 = "alice@example.com"
        email2 = "bob@example.com"

        hash1 = pseudonymize_email(email1)
        hash2 = pseudonymize_email(email2)

        assert hash1 != hash2
        assert hash1.startswith("email_hash_")
        assert hash2.startswith("email_hash_")

    def test_pseudonymize_email_unicode_handling(self):
        """Test email with unicode characters."""
        email = "user@日本.jp"

        result = pseudonymize_email(email)

        assert result.startswith("email_hash_")
        assert len(result) == len("email_hash_") + 16


class TestMaskPhone:
    """Tests for phone number masking."""

    def test_mask_phone_keeps_last_4_digits(self):
        """Test that phone is masked keeping last 4 digits (Lines 153-156)."""
        phone = "+1 (555) 123-4567"

        # Lines 153-156 executed: Extract digits, keep last 4
        result = mask_phone(phone)

        assert result == "***-***-4567"

    def test_mask_phone_handles_short_numbers(self):
        """Test phone masking with fewer than 4 digits (Line 156)."""
        phone = "+1 12"  # Only 3 digits

        # Line 156 executed: Fallback to full mask
        result = mask_phone(phone)

        assert result == "***-***-****"

    def test_mask_phone_international_format(self):
        """Test phone masking with international format."""
        phone = "+33 6 12 34 56 78"

        result = mask_phone(phone)

        # Last 4 digits: 5678
        assert result == "***-***-5678"

    def test_mask_phone_no_formatting(self):
        """Test phone masking with plain digits."""
        phone = "15551234567"

        result = mask_phone(phone)

        assert result == "***-***-4567"


class TestMaskCreditCard:
    """Tests for credit card number masking."""

    def test_mask_credit_card_keeps_last_4_digits(self):
        """Test that credit card is masked keeping last 4 digits (Lines 173-176)."""
        card = "4532 1234 5678 9010"

        # Lines 173-176 executed: Extract digits, keep last 4
        result = mask_credit_card(card)

        assert result == "****-****-****-9010"

    def test_mask_credit_card_handles_short_numbers(self):
        """Test credit card masking with fewer than 4 digits (Line 176)."""
        card = "123"

        # Line 176 executed: Fallback to full mask
        result = mask_credit_card(card)

        assert result == "****-****-****-****"

    def test_mask_credit_card_amex_format(self):
        """Test credit card masking with Amex format."""
        card = "3782-822463-10005"  # Amex 15 digits

        result = mask_credit_card(card)

        # Last 4 digits: 0005
        assert result == "****-****-****-0005"

    def test_mask_credit_card_no_formatting(self):
        """Test credit card masking with plain digits."""
        card = "4532123456789010"

        result = mask_credit_card(card)

        assert result == "****-****-****-9010"


class TestRedactValue:
    """Tests for generic value redaction."""

    def test_redact_value_returns_placeholder(self):
        """Test that any value is redacted to [REDACTED] (Line 189)."""
        # Line 189 executed: Return [REDACTED]
        assert redact_value("password123") == "[REDACTED]"
        assert redact_value(12345) == "[REDACTED]"
        assert redact_value({"key": "value"}) == "[REDACTED]"
        assert redact_value(None) == "[REDACTED]"


class TestSanitizeString:
    """Tests for string sanitization with pattern-based PII detection."""

    def test_sanitize_string_redacts_email(self):
        """Test that emails in strings are pseudonymized (Line 210)."""
        text = "Contact user@example.com for details"

        result = sanitize_string(text)

        # Email should be pseudonymized
        assert "user@example.com" not in result
        assert "email_hash_" in result
        assert "Contact" in result
        assert "for details" in result

    def test_sanitize_string_masks_phone(self):
        """Test that phones in strings are masked (Line 213)."""
        text = "Call +1-555-123-4567 today"

        result = sanitize_string(text)

        # Phone should be masked
        assert "+1-555-123-4567" not in result
        assert "***-***-4567" in result
        assert "Call" in result
        assert "today" in result

    def test_sanitize_string_masks_credit_card(self):
        """Test that credit cards in strings are masked (Line 216)."""
        text = "Card number: 4532 1234 5678 9010"

        result = sanitize_string(text)

        # Credit card should be masked
        assert "4532 1234 5678 9010" not in result
        assert "****-****-****-9010" in result
        assert "Card number:" in result

    def test_sanitize_string_redacts_tokens(self):
        """Test that tokens in strings are redacted (Line 219)."""
        text = "API key: sk_live_abcdefghijklmnopqrstuvwxyz1234567890"

        result = sanitize_string(text)

        # Token should be redacted
        assert "sk_live_" not in result
        assert "[REDACTED_TOKEN]" in result
        assert "API key:" in result

    def test_sanitize_string_multiple_pii_types(self):
        """Test string with multiple PII types."""
        text = "Email: user@example.com, Phone: +1-555-123-4567, Card: 4532 1234 5678 9010"

        result = sanitize_string(text)

        # All PII should be sanitized
        assert "user@example.com" not in result
        assert "+1-555-123-4567" not in result
        assert "4532 1234 5678 9010" not in result
        assert "email_hash_" in result
        assert "***-***-4567" in result
        assert "****-****-****-9010" in result


class TestSanitizeDict:
    """Tests for dictionary sanitization with field-based and pattern-based PII detection."""

    def test_sanitize_dict_redacts_sensitive_fields(self):
        """Test that sensitive field names are redacted (Lines 251-252)."""
        data = {
            "username": "alice",
            "password": "secret123",
            "api_key": "sk_test_abcd1234",
            "token": "bearer_xyz789",
        }

        # Lines 251-252 executed: Redact sensitive fields
        result = sanitize_dict(data)

        # Sensitive fields redacted
        assert result["username"] == "alice"  # Not sensitive
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_sanitize_dict_pseudonymizes_pii_fields(self):
        """Test that PII field names are pseudonymized (Lines 256-257)."""
        data = {
            "username": "alice",
            "email": "alice@example.com",
            "user_email": "alice@company.com",
        }

        # Lines 256-257 executed: Pseudonymize email fields
        result = sanitize_dict(data)

        # Email fields pseudonymized
        assert result["username"] == "alice"  # Not PII field
        assert result["email"].startswith("email_hash_")
        assert result["user_email"].startswith("email_hash_")
        assert "alice@example.com" not in str(result)

    def test_sanitize_dict_masks_phone_fields(self):
        """Test that phone field names are masked (Lines 261-262)."""
        data = {"username": "bob", "phone": "+1-555-987-6543", "mobile_number": "+33 6 12 34 56 78"}

        # Lines 261-262 executed: Mask phone fields
        result = sanitize_dict(data)

        # Phone fields masked
        assert result["username"] == "bob"  # Not phone field
        assert result["phone"] == "***-***-6543"
        assert result["mobile_number"] == "***-***-5678"
        assert "+1-555-987-6543" not in str(result)

    def test_sanitize_dict_recursive_nested_dict(self):
        """Test that nested dictionaries are recursively sanitized (Line 266)."""
        data = {
            "user": {
                "name": "charlie",
                "password": "secret456",
                "profile": {"email": "charlie@example.com", "phone": "+1-555-111-2222"},
            }
        }

        # Line 266 executed: Recursive sanitization
        result = sanitize_dict(data)

        # Verify nested sanitization
        assert result["user"]["name"] == "charlie"
        assert result["user"]["password"] == "[REDACTED]"
        assert result["user"]["profile"]["email"].startswith("email_hash_")
        assert result["user"]["profile"]["phone"] == "***-***-2222"

    def test_sanitize_dict_handles_lists(self):
        """Test that lists are sanitized (Lines 268-276)."""
        data = {
            "users": [
                {"email": "alice@example.com", "password": "pass1"},
                {"email": "bob@example.com", "password": "pass2"},
            ],
            "messages": ["Contact user@domain.com", "Call +1-555-999-8888"],
        }

        # Lines 268-276 executed: List sanitization
        result = sanitize_dict(data)

        # Verify list sanitization
        assert result["users"][0]["email"].startswith("email_hash_")
        assert result["users"][0]["password"] == "[REDACTED]"
        assert result["users"][1]["email"].startswith("email_hash_")
        assert result["users"][1]["password"] == "[REDACTED]"

        # String items in list sanitized
        assert "user@domain.com" not in result["messages"][0]
        assert "email_hash_" in result["messages"][0]
        assert "+1-555-999-8888" not in result["messages"][1]
        assert "***-***-8888" in result["messages"][1]

    def test_sanitize_dict_preserves_non_sensitive_data(self):
        """Test that non-sensitive data is preserved."""
        data = {
            "user_id": 12345,
            "username": "alice",
            "created_at": "2024-01-01T00:00:00Z",
            "is_active": True,
            "metadata": {"count": 42, "items": ["item1", "item2"]},
        }

        result = sanitize_dict(data)

        # All non-sensitive data preserved
        assert result["user_id"] == 12345
        assert result["username"] == "alice"
        assert result["created_at"] == "2024-01-01T00:00:00Z"
        assert result["is_active"] is True
        assert result["metadata"]["count"] == 42
        assert result["metadata"]["items"] == ["item1", "item2"]

    def test_sanitize_dict_case_insensitive_field_names(self):
        """Test that field names are matched case-insensitively."""
        data = {
            "Password": "secret1",
            "API_KEY": "key123",
            "Email": "user@example.com",
            "PHONE": "+1-555-777-6666",
        }

        result = sanitize_dict(data)

        # Case-insensitive matching
        assert result["Password"] == "[REDACTED]"
        assert result["API_KEY"] == "[REDACTED]"
        assert result["Email"].startswith("email_hash_")
        assert result["PHONE"] == "***-***-6666"


class TestAddPiiFilter:
    """Tests for structlog processor integration."""

    def test_add_pii_filter_sanitizes_event_dict(self):
        """Test that structlog processor sanitizes event dict."""
        event_dict = {
            "event": "user_login",
            "email": "user@example.com",
            "password": "secret123",
            "phone": "+1-555-123-4567",
            "user_id": 42,
        }

        result = add_pii_filter(None, "info", event_dict)

        # Verify sanitization
        assert result["event"] == "user_login"
        assert result["email"].startswith("email_hash_")
        assert result["password"] == "[REDACTED]"
        assert result["phone"] == "***-***-4567"
        assert result["user_id"] == 42

    def test_add_pii_filter_handles_nested_structures(self):
        """Test structlog processor with nested data."""
        event_dict = {
            "event": "api_request",
            "request": {
                "headers": {"authorization": "Bearer token123", "user-agent": "Mozilla/5.0"},
                "body": {"email": "user@example.com", "message": "Contact admin@company.com"},
            },
        }

        result = add_pii_filter(None, "info", event_dict)

        # Verify nested sanitization
        assert result["request"]["headers"]["authorization"] == "[REDACTED]"
        assert result["request"]["headers"]["user-agent"] == "Mozilla/5.0"
        assert result["request"]["body"]["email"].startswith("email_hash_")
        assert "admin@company.com" not in result["request"]["body"]["message"]
        assert "email_hash_" in result["request"]["body"]["message"]

    def test_add_pii_filter_preserves_empty_dict(self):
        """Test structlog processor with empty event dict."""
        event_dict = {}

        result = add_pii_filter(None, "info", event_dict)

        assert result == {}

    def test_add_pii_filter_real_world_log(self):
        """Test structlog processor with realistic log data."""
        event_dict = {
            "event": "user_registration",
            "timestamp": "2024-01-01T12:00:00Z",
            "user": {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "hashed_password_value",
                "phone": "+1-555-321-9876",
            },
            "request_id": "req_abc123",
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0",
        }

        result = add_pii_filter(None, "info", event_dict)

        # Verify comprehensive sanitization
        assert result["event"] == "user_registration"
        assert result["timestamp"] == "2024-01-01T12:00:00Z"
        assert result["user"]["username"] == "newuser"
        assert result["user"]["email"].startswith("email_hash_")
        assert result["user"]["password"] == "[REDACTED]"
        assert result["user"]["phone"] == "***-***-9876"
        assert result["request_id"] == "req_abc123"
        assert result["ip_address"] == "192.168.1.100"
        assert result["user_agent"] == "Mozilla/5.0"
