"""
Standalone test script for PII filter validation.
Can be run without full environment setup: python test_pii_standalone.py
"""

import sys
from pathlib import Path

# Add src to path (go up from tests/unit to apps/api, then into src)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from infrastructure.observability.pii_filter import (
    add_pii_filter,
    mask_credit_card,
    mask_phone,
    pseudonymize_email,
    sanitize_dict,
    sanitize_string,
)


def test_email_pseudonymization():
    """Test email pseudonymization."""
    email = "user@example.com"
    result = pseudonymize_email(email)

    assert result.startswith("email_hash_"), f"Expected hash prefix, got: {result}"
    assert len(result) == 27, f"Expected length 27, got: {len(result)}"

    # Test consistency
    result2 = pseudonymize_email(email)
    assert result == result2, "Email hashes should be consistent"

    # Test different emails produce different hashes
    email2 = "admin@example.com"
    result3 = pseudonymize_email(email2)
    assert result != result3, "Different emails should produce different hashes"

    print("[OK] Email pseudonymization tests passed")


def test_phone_masking():
    """Test phone number masking."""
    phone1 = "+1-555-123-4567"
    result1 = mask_phone(phone1)
    assert result1 == "***-***-4567", f"Expected '***-***-4567', got: {result1}"

    phone2 = "+33 6 12 34 56 78"
    result2 = mask_phone(phone2)
    assert result2 == "***-***-5678", f"Expected '***-***-5678', got: {result2}"

    phone3 = "+1 555 123 4567"
    result3 = mask_phone(phone3)
    assert result3 == "***-***-4567", f"Expected '***-***-4567', got: {result3}"

    print("[OK] Phone masking tests passed")


def test_credit_card_masking():
    """Test credit card masking."""
    card = "4532 1234 5678 9010"
    result = mask_credit_card(card)
    assert result == "****-****-****-9010", f"Expected '****-****-****-9010', got: {result}"
    assert "4532" not in result, "Card prefix should be masked"

    print("[OK] Credit card masking tests passed")


def test_string_sanitization():
    """Test string sanitization with multiple PII types."""
    text = "Contact user@example.com or call +1-555-123-4567 for support"
    result = sanitize_string(text)

    assert "user@example.com" not in result, "Email should be pseudonymized"
    assert "email_hash_" in result, "Email hash should be present"
    assert "+1-555-123-4567" not in result, "Phone should be masked"
    assert "***-***-4567" in result, "Masked phone should be present"

    print("[OK] String sanitization tests passed")


def test_dict_sanitization():
    """Test dictionary sanitization with sensitive fields."""
    data = {
        "event": "user_login",
        "email": "admin@example.com",
        "password": "SuperSecret123!",
        "user_id": "12345",
        "token": "sk_test_1234567890abcdef1234567890abcdef",
    }

    result = sanitize_dict(data)

    assert result["event"] == "user_login", "Event should be preserved"
    assert "admin@example.com" not in str(result["email"]), "Email should be pseudonymized"
    assert result["password"] == "[REDACTED]", "Password should be redacted"
    assert result["user_id"] == "12345", "User ID should be preserved"
    assert result["token"] == "[REDACTED]", "Token should be redacted"

    print("[OK] Dictionary sanitization tests passed")


def test_nested_structures():
    """Test sanitization of nested structures."""
    data = {
        "user": {
            "email": "user@test.com",
            "password": "secret",
            "profile": {"phone": "+33 6 12 34 56 78", "name": "John Doe"},
        }
    }

    result = sanitize_dict(data)

    print(f"[DEBUG] Result: {result}")
    print(f"[DEBUG] Phone value: {result['user']['profile']['phone']}")

    assert "user@test.com" not in str(
        result["user"]["email"]
    ), "Nested email should be pseudonymized"
    assert result["user"]["password"] == "[REDACTED]", "Nested password should be redacted"
    assert (
        "***-***-5678" in result["user"]["profile"]["phone"]
    ), f"Nested phone should be masked, got: {result['user']['profile']['phone']}"
    assert result["user"]["profile"]["name"] == "John Doe", "Non-PII should be preserved"

    print("[OK] Nested structure tests passed")


def test_structlog_processor():
    """Test structlog processor integration."""
    event_dict = {
        "event": "authentication_failed",
        "email": "hacker@evil.com",
        "password": "attempted_password",
        "ip_address": "192.168.1.100",
    }

    result = add_pii_filter(None, "error", event_dict)

    assert result["event"] == "authentication_failed", "Event should be preserved"
    assert "hacker@evil.com" not in str(result["email"]), "Email should be pseudonymized"
    assert result["password"] == "[REDACTED]", "Password should be redacted"
    assert result["ip_address"] == "192.168.1.100", "IP should be preserved"

    print("[OK] Structlog processor tests passed")


def test_real_world_example():
    """Test real-world logging scenario."""
    log_data = {
        "timestamp": "2025-10-21T14:30:00Z",
        "level": "info",
        "event": "user_registration",
        "email": "newuser@example.com",
        "password": "TempPass123!!",
        "phone": "+33 6 12 34 56 78",
        "api_key": "sk_live_abcdefghijklmnopqrstuvwxyz123456",
        "user_agent": "Mozilla/5.0",
        "trace_id": "abc123def456",
    }

    result = sanitize_dict(log_data)

    # Verify non-PII preserved
    assert result["timestamp"] == "2025-10-21T14:30:00Z"
    assert result["level"] == "info"
    assert result["event"] == "user_registration"
    assert result["user_agent"] == "Mozilla/5.0"
    assert result["trace_id"] == "abc123def456"

    # Verify PII sanitized
    assert "newuser@example.com" not in str(result["email"])
    assert "email_hash_" in result["email"]
    assert result["password"] == "[REDACTED]"
    assert "***-***-5678" in result["phone"]
    assert result["api_key"] == "[REDACTED]"

    print("[OK] Real-world example tests passed")
    print("\n[INFO] Sanitized log output:")
    print(result)


if __name__ == "__main__":
    print("Running PII Filter Validation Tests\n")
    print("=" * 60)

    try:
        test_email_pseudonymization()
        test_phone_masking()
        test_credit_card_masking()
        test_string_sanitization()
        test_dict_sanitization()
        test_nested_structures()
        test_structlog_processor()
        test_real_world_example()

        print("\n" + "=" * 60)
        print("SUCCESS: ALL TESTS PASSED (8/8)")
        print("=" * 60)
        print("\nPII Filter is working correctly!")
        print("Ready for production deployment")

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"[FAIL] TEST FAILED: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[ERROR] UNEXPECTED ERROR: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        sys.exit(1)
