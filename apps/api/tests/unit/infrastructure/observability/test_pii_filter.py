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

import pytest

from src.infrastructure.observability.pii_filter import (
    add_pii_filter,
    fingerprint_secret,
    mask_credit_card,
    mask_phone,
    pseudonymize_email,
    redact_value,
    sanitize_dict,
    sanitize_string,
    sanitize_url_query,
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
        """Test structlog processor with nested data (DEBUG level).

        At DEBUG the content-field net is off, so nested values are still
        pattern-sanitized individually. At INFO the whole `body` field is a
        content field and gets redacted (see test below).
        """
        event_dict = {
            "event": "api_request",
            "request": {
                "headers": {"authorization": "Bearer token123", "user-agent": "Mozilla/5.0"},
                "body": {"email": "user@example.com", "message": "Contact admin@company.com"},
            },
        }

        result = add_pii_filter(None, "debug", event_dict)

        # Verify nested sanitization
        assert result["request"]["headers"]["authorization"] == "[REDACTED]"
        assert result["request"]["headers"]["user-agent"] == "Mozilla/5.0"
        assert result["request"]["body"]["email"].startswith("email_hash_")
        assert "admin@company.com" not in result["request"]["body"]["message"]
        assert "email_hash_" in result["request"]["body"]["message"]

    def test_add_pii_filter_redacts_nested_body_at_info(self):
        """At INFO, `body` is a content field: fully redacted (audit wave 2, C7)."""
        event_dict = {
            "event": "api_request",
            "request": {
                "headers": {"authorization": "Bearer token123", "user-agent": "Mozilla/5.0"},
                "body": {"email": "user@example.com", "message": "Contact admin@company.com"},
            },
        }

        result = add_pii_filter(None, "info", event_dict)

        assert result["request"]["headers"]["authorization"] == "[REDACTED]"
        assert result["request"]["body"] == "[REDACTED]"

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

    def test_add_pii_filter_preserves_event_names_matching_token_pattern(self):
        """Structlog meta fields (event/logger/level/timestamp/...) are
        developer-controlled identifiers and must never be sanitized, even when
        their value happens to match TOKEN_PATTERN.

        Regression: events like ``database_connection_pool_exhausted`` or
        ``langgraph_observability_initialized`` were redacted to
        ``[REDACTED_TOKEN]``.
        """
        # Sample developer-controlled event names that historically matched
        # the over-broad generic TOKEN_PATTERN (now removed).
        token_like_events = [
            "database_connection_pool_exhausted",
            "langgraph_observability_initialized",
            "callbacks_factory_initialization_complete",
            "tracking_context_persistence_failed",
            "subagent_daily_budget_check_failed",
        ]

        for event_name in token_like_events:
            event_dict = {
                "event": event_name,
                "logger": "src.infrastructure.token_tracking_service",
                "level": "info",
                "timestamp": "2024-01-01T12:00:00Z",
            }
            result = add_pii_filter(None, "info", event_dict)
            assert (
                result["event"] == event_name
            ), f"Event name {event_name!r} should pass through unchanged"
            assert result["logger"] == "src.infrastructure.token_tracking_service"
            assert result["level"] == "info"
            assert result["timestamp"] == "2024-01-01T12:00:00Z"

    def test_add_pii_filter_preserves_payload_developer_identifiers(self):
        """Developer-controlled identifiers in payload fields (``note``,
        ``reason``, ``stage``, ...) must NOT match TOKEN_PATTERN even though
        they look like ``something_long_with_underscores``. The token pattern
        is restricted to high-confidence signatures (Stripe / GitHub / JWT).

        Regression: factory.py logged ``note="langfuse_callbacks_added_via_config_enrichment"``
        and the value was redacted to ``[REDACTED_TOKEN]`` by the previous
        over-broad generic pattern.
        """
        developer_identifiers = [
            "langfuse_callbacks_added_via_config_enrichment",
            "skill_registry_loaded_from_database",
            "fallback_to_static_greeting_on_llm_error",
            "intelligent_filtering_data_generation_skipped",
        ]
        for value in developer_identifiers:
            event_dict = {"event": "llm_created", "note": value}
            result = add_pii_filter(None, "info", event_dict)
            assert (
                result["note"] == value
            ), f"Payload developer identifier {value!r} should not be redacted"

    def test_add_pii_filter_still_redacts_real_tokens(self):
        """Defence-in-depth: real-token signatures must still be caught when
        they appear in free-text payload values.

        The token literals below are split via runtime concatenation so the
        source file does not embed full provider-prefixed strings — that
        keeps GitHub Push Protection (secret scanning) happy while still
        producing the exact same payload for the regex at runtime.
        """
        # Stripe live secret key (>= 24 chars after prefix).
        stripe_token = "sk_" + "live_" + "AbCdEfGhIjKlMnOpQrStUvWx"
        stripe_value = f"Some context with {stripe_token} in the middle."
        # GitHub personal access token (>= 36 chars after prefix).
        github_token = "gh" + "p_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
        github_value = f"Header authorization=Bearer {github_token}"
        # JWT (three URL-safe-base64 segments).
        jwt_token = (
            "ey" + "JhbGciOiJIUzI1NiJ9.ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        jwt_value = f"Auth token {jwt_token} rest of message"

        for value in (stripe_value, github_value, jwt_value):
            event_dict = {"event": "audit", "raw": value}
            result = add_pii_filter(None, "info", event_dict)
            assert (
                "[REDACTED_TOKEN]" in result["raw"]
            ), f"Expected real token in {value!r} to be redacted"


class TestContentFieldRedactionAtInfo:
    """Systemic net (audit wave 2, C7): content-bearing fields are redacted at
    INFO and above, but pass through at DEBUG.

    Criterion: a full scenario (contact resolution + memory + home route) must
    leave no name, email, or coordinate in INFO logs — even if a future call
    site logs `subject=` / `lat=` / `mappings=` at INFO again.
    """

    def test_content_fields_redacted_at_info(self):
        """Names, emails, coordinates, subjects are redacted at INFO."""
        event_dict = {
            "event": "scenario",
            # contact resolution
            "contact_name": "Jean Dupond",
            "to": "jean.dupond@example.com",
            "subject": "Rendez-vous demain",
            # memory resolution
            "mappings": {"mon frère": "Paul Dupond"},
            "content_preview": "User is anxious about...",
            # home route
            "lat": 48.8566,
            "lon": 2.3522,
            "address": "12 rue de la Paix, Paris",
            "destination": "Gare de Lyon",
        }

        result = add_pii_filter(None, "info", event_dict)

        rendered = str(result)
        assert "Jean Dupond" not in rendered
        assert "jean.dupond" not in rendered
        assert "Rendez-vous" not in rendered
        assert "Paul Dupond" not in rendered
        assert "anxious" not in rendered
        assert "48.8566" not in rendered
        assert "2.3522" not in rendered
        assert "rue de la Paix" not in rendered
        assert "Gare de Lyon" not in rendered
        # Event name untouched (structlog metadata)
        assert result["event"] == "scenario"

    def test_content_fields_redacted_at_warning_and_error(self):
        """The net applies to every level above DEBUG, not just INFO."""
        for level in ("warning", "error", "critical"):
            result = add_pii_filter(None, level, {"event": "e", "params": {"to": "a@b.com"}})
            assert result["params"] == "[REDACTED]", f"params must be redacted at {level}"

    def test_content_fields_pass_through_at_debug(self):
        """DEBUG keeps contents (minus pattern-based email pseudonymization)."""
        event_dict = {
            "event": "details",
            "contact_name": "Jean Dupond",
            "lat": 48.8566,
            "subject": "Rendez-vous demain",
        }

        result = add_pii_filter(None, "debug", event_dict)

        assert result["contact_name"] == "Jean Dupond"
        assert result["lat"] == 48.8566
        assert result["subject"] == "Rendez-vous demain"

    def test_content_fields_redacted_in_nested_dicts(self):
        """Redaction recurses into nested payloads (e.g. params dicts)."""
        event_dict = {
            "event": "tool_error",
            "context": {"tool_args": {"subject": "Secret subject", "count": 3}},
        }

        result = add_pii_filter(None, "error", event_dict)

        assert result["context"]["tool_args"]["subject"] == "[REDACTED]"
        assert result["context"]["tool_args"]["count"] == 3

    def test_non_content_fields_untouched_at_info(self):
        """Counters, IDs and flags stay readable at INFO."""
        event_dict = {
            "event": "ok",
            "user_id": "1234",
            "mappings_count": 2,
            "has_address": True,
            "query_length": 42,
        }

        result = add_pii_filter(None, "info", event_dict)

        assert result == event_dict


class TestContentFieldNetHardening:
    """CA-1 (audit S9): residual PII leaks where user content is logged at INFO
    under field names the content-field net did not yet cover.

    Confirmed pre-fix leak sites (all logging raw user content at INFO):
    - agents/services/orchestration/service.py — ``user_message=`` (8 HITL sites)
    - agents/tools/calendar_tools.py — ``summary=`` (event titles)
    - agents/tools/tasks_tools.py — ``title=`` (task titles)
    - conversations/service.py — ``new_content=`` / ``original_content_preview=``
    - agents/tools/reminder_tools.py — ``content=`` (reminder body)

    Criterion: each field is redacted at INFO/WARNING/ERROR, passed through at
    DEBUG (net off) so local debugging keeps the raw value.
    """

    def test_orchestration_user_message_redacted_at_info(self):
        """HITL decision log must not leak the user's raw message at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "approval_decision_fast_path", "user_message": "rendez-vous médical"},
        )

        assert result["user_message"] == "[REDACTED]"

    def test_calendar_summary_redacted_at_info(self):
        """A calendar event summary (``RDV Dr Martin``) must be redacted at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "create_event_draft_prepared", "summary": "RDV Dr Martin"},
        )

        assert result["summary"] == "[REDACTED]"

    def test_task_title_redacted_at_info(self):
        """A task title must be redacted at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "create_task_draft_prepared", "title": "Appeler le cabinet médical"},
        )

        assert result["title"] == "[REDACTED]"

    def test_conversation_edit_content_fields_redacted_at_info(self):
        """``last_user_message_updated`` must not leak the edited message body."""
        result = add_pii_filter(
            None,
            "info",
            {
                "event": "last_user_message_updated",
                "original_content_preview": "mon rendez-vous chez le docteur",
                "new_content": "annule mon rendez-vous chez le docteur",
            },
        )

        assert result["original_content_preview"] == "[REDACTED]"
        assert result["new_content"] == "[REDACTED]"

    def test_reminder_content_redacted_at_info(self):
        """A reminder body must be redacted at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "cancel_reminder_draft_prepared", "content": "prendre le traitement du soir"},
        )

        assert result["content"] == "[REDACTED]"

    def test_hitl_edit_content_fields_redacted_at_info(self):
        """HITL edit/reformulation logs carry the user's original message and
        edit request (orchestration/service.py, hitl/resumption_strategies.py):
        ``original_content`` and ``reformulated_intent`` must not leak at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {
                "event": "hitl_edit_message_reformulation_applied",
                "original_content": "annule mon rendez-vous chez le docteur",
                "reformulated_intent": "supprime l'événement du 12 mars avec Dr Martin",
            },
        )

        assert result["original_content"] == "[REDACTED]"
        assert result["reformulated_intent"] == "[REDACTED]"

    def test_hitl_response_fields_redacted_at_info(self):
        """HITL classifier / clarification logs carry the user's raw reply
        (hitl_classifier.py, clarification_node.py, resumption_strategies.py):
        ``user_response`` / ``original_user_response`` / ``clarification_response``
        must not leak at INFO."""
        result = add_pii_filter(
            None,
            "info",
            {
                "event": "hitl_response_classified",
                "user_response": "oui mais change le destinataire en jean",
                "original_user_response": "annule le rendez-vous du 12",
                "clarification_response": "à Paris, chez le Dr Martin",
            },
        )

        assert result["user_response"] == "[REDACTED]"
        assert result["original_user_response"] == "[REDACTED]"
        assert result["clarification_response"] == "[REDACTED]"

    def test_new_content_fields_redacted_at_warning_and_error(self):
        """The net applies to every level above DEBUG."""
        for level in ("warning", "error", "critical"):
            result = add_pii_filter(
                None, level, {"event": "e", "user_message": "rendez-vous médical"}
            )
            assert result["user_message"] == "[REDACTED]", f"must be redacted at {level}"

    def test_new_content_fields_pass_through_at_debug(self):
        """DEBUG keeps the raw content (net off) for local debugging."""
        event = {
            "event": "details",
            "user_message": "rendez-vous médical",
            "summary": "RDV Dr Martin",
            "title": "Appeler le cabinet médical",
            "content": "prendre le traitement du soir",
            "new_content": "annule le rendez-vous",
            "original_content_preview": "mon rendez-vous",
        }

        result = add_pii_filter(None, "debug", dict(event))

        for key, value in event.items():
            assert result[key] == value, f"{key} must pass through unchanged at DEBUG"

    # --- Edge cases (CA-1 hardening) ---

    def test_content_field_redacted_when_nested_at_info(self):
        """A net field nested inside a payload dict is still redacted at INFO:
        the redaction recurses (e.g. `context={"user_message": ...}`)."""
        result = add_pii_filter(
            None,
            "info",
            {
                "event": "hitl_context",
                "context": {"user_message": "rendez-vous médical", "attempt": 2},
            },
        )

        assert result["context"]["user_message"] == "[REDACTED]"
        # Non-content siblings stay readable.
        assert result["context"]["attempt"] == 2

    def test_content_field_value_type_agnostic_at_info(self):
        """Redaction ignores the value type — a dict/None/number under a net
        field name is redacted wholesale at INFO (fail-closed)."""
        result = add_pii_filter(
            None,
            "info",
            {
                "event": "e",
                "content": {"secret_body": "x"},  # dict, not str
                "summary": None,  # None
                "title": 42,  # number
            },
        )

        assert result["content"] == "[REDACTED]"
        assert result["summary"] == "[REDACTED]"
        assert result["title"] == "[REDACTED]"

    def test_content_field_at_debug_still_pattern_scrubs_embedded_email(self):
        """At DEBUG the net is off, but pattern-based scrubbing still runs:
        an email embedded in a content field is pseudonymized (defense in
        depth — DEBUG logs must not ship raw emails either)."""
        result = add_pii_filter(
            None,
            "debug",
            {"event": "details", "user_message": "écris à jean.dupont@example.com stp"},
        )

        assert "jean.dupont@example.com" not in result["user_message"]
        assert "email_hash_" in result["user_message"]

    def test_filename_and_exclude_criteria_redacted(self):
        """O-1 + Rés.3-partiel: user-uploaded file names and FOR_EACH exclusion
        criteria must not leak in logs.

        - ``original_filename`` — a user's uploaded document/attachment name
          (rag_spaces/service.py & processing.py at INFO,
          attachments/llm_content.py at WARNING).
        - ``exclude_criteria`` — the user's bulk-operation exclusion text
          (for_each_confirm_node.py, hitl/item_filter.py,
          orchestration/service.py at INFO).
        """
        info_result = add_pii_filter(
            None,
            "info",
            {
                "event": "rag_document_uploaded",
                "original_filename": "CV Jean Dupont.pdf",
                "exclude_criteria": "sauf les emails de Marie",
            },
        )
        assert info_result["original_filename"] == "[REDACTED]"
        assert info_result["exclude_criteria"] == "[REDACTED]"

        # original_filename also leaks at WARNING (image load failure path).
        warn_result = add_pii_filter(
            None,
            "warning",
            {"event": "attachment_image_load_failed", "original_filename": "IRM cerveau.png"},
        )
        assert warn_result["original_filename"] == "[REDACTED]"


class TestSec012CredentialRedaction:
    """SEC-012: single-use auth credentials — OAuth state, PKCE, reset and
    verification links — must never reach the logs, while high-entropy state
    stays *correlatable* and short application-state strings stay readable.

    Confirmed pre-fix leak sites (all logging single-use credentials):
    - core/oauth/flow_handler.py — ``state=`` (6 sites, INFO/WARNING/ERROR)
    - domains/connectors/service.py — ``state=`` (~28 sites)
    - domains/auth/service.py — ``verification_url=`` / ``reset_url=`` (INFO;
      the URL query carries the single-use token)

    Criterion: the raw secret is absent from the rendered log, correlation is
    preserved (same state → same fingerprint), and a plain LangGraph/app
    ``state`` is left untouched (no observability regression).
    """

    # A realistic opaque OAuth state (shape of ``secrets.token_urlsafe(32)`` =
    # 43 URL-safe-base64 chars). Not a real secret.
    OAUTH_STATE = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-aBcDeF"

    def test_fingerprint_secret_is_stable_and_non_reversible(self):
        """fingerprint_secret: same input → same tag, never contains the raw."""
        fp1 = fingerprint_secret(self.OAUTH_STATE)
        fp2 = fingerprint_secret(self.OAUTH_STATE)

        assert fp1 == fp2  # deterministic → correlatable
        assert fp1.startswith("fp_")
        assert self.OAUTH_STATE not in fp1  # non-reversible
        assert fingerprint_secret("other-high-entropy-value-000000000") != fp1

    def test_oauth_state_field_is_fingerprinted_at_info(self):
        """An opaque ``state`` is fingerprinted (not raw, not fully redacted)."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "oauth_flow_initiated", "provider": "google", "state": self.OAUTH_STATE},
        )

        assert result["state"] == fingerprint_secret(self.OAUTH_STATE)
        assert self.OAUTH_STATE not in str(result)
        # Correlation metadata survives.
        assert result["provider"] == "google"

    def test_oauth_state_fingerprint_survives_all_levels(self):
        """flow_handler logs state at INFO/WARNING/ERROR — all must fingerprint."""
        for level in ("info", "warning", "error", "critical"):
            result = add_pii_filter(
                None, level, {"event": "oauth_invalid_state", "state": self.OAUTH_STATE}
            )
            assert result["state"] == fingerprint_secret(self.OAUTH_STATE), level
            assert self.OAUTH_STATE not in str(result)

    def test_short_application_state_is_preserved(self):
        """A LangGraph/app ``state`` label (short, not token-shaped) stays raw —
        no observability regression (invoke_helpers.py, agents/api/service.py)."""
        for value in ("running", "pending_approval", "completed", "awaiting_hitl"):
            result = add_pii_filter(None, "info", {"event": "node_transition", "state": value})
            assert result["state"] == value, f"app state {value!r} must stay readable"

    def test_langgraph_state_dict_is_not_fingerprinted(self):
        """A ``state`` whose value is a dict (LangGraph MessagesState) is recursed
        into, never fingerprinted (fingerprint only applies to opaque strings)."""
        result = add_pii_filter(
            None,
            "debug",
            {"event": "graph_step", "state": {"phase": "router", "iteration": 3}},
        )
        assert result["state"] == {"phase": "router", "iteration": 3}

    def test_verification_and_reset_url_tokens_are_stripped(self):
        """A logged verification/reset URL keeps its structure but loses the
        single-use token in its query string."""
        event = {
            "event": "email_link_built",
            "verification_url": "https://app.example.com/verify?token=SENTINEL_TOKEN_VALUE&lang=fr",
            "reset_url": "https://app.example.com/reset?token=SENTINEL_RESET_VALUE",
        }
        # Log these under non-content field names at DEBUG so only the URL
        # query-string net applies (INFO would redact by content-field name).
        result = add_pii_filter(None, "debug", event)

        assert "SENTINEL_TOKEN_VALUE" not in str(result)
        assert "SENTINEL_RESET_VALUE" not in str(result)
        # Structure + non-sensitive params preserved for debugging.
        assert "token=[REDACTED]" in result["verification_url"]
        assert "lang=fr" in result["verification_url"]

    def test_sanitize_url_query_masks_only_sensitive_params(self):
        """sanitize_url_query: masks sensitive param VALUES, keeps names + others."""
        cleaned = sanitize_url_query("https://x/cb?code=abc123&state=def456&lang=fr&page=2")
        assert "code=[REDACTED]" in cleaned
        assert "state=[REDACTED]" in cleaned
        assert "lang=fr" in cleaned
        assert "page=2" in cleaned
        assert "abc123" not in cleaned
        assert "def456" not in cleaned

    def test_sanitize_url_query_ignores_free_text_code(self):
        """A free-text ``code=200`` (no ?/& boundary) is NOT masked — the net is
        anchored on real query parameters to avoid observability false positives."""
        assert sanitize_url_query("http response code=200 ok") == "http response code=200 ok"

    def test_pkce_and_oauth_credential_fields_are_redacted(self):
        """PKCE verifier/challenge, client secret, id_token, auth code → redacted."""
        event = {
            "event": "oauth_token_exchange",
            "code_verifier": "SENTINEL_VERIFIER",
            "code_challenge": "SENTINEL_CHALLENGE",
            "client_secret": "SENTINEL_CLIENT_SECRET",
            "id_token": "SENTINEL_ID_TOKEN",
            "authorization_code": "SENTINEL_AUTH_CODE",
        }
        result = add_pii_filter(None, "info", event)

        for key in event:
            if key == "event":
                continue
            assert result[key] == "[REDACTED]", key
        for sentinel in (
            "SENTINEL_VERIFIER",
            "SENTINEL_CHALLENGE",
            "SENTINEL_CLIENT_SECRET",
            "SENTINEL_ID_TOKEN",
            "SENTINEL_AUTH_CODE",
        ):
            assert sentinel not in str(result)

    def test_end_to_end_oauth_init_log_leaks_no_secret(self):
        """Full oauth_flow_initiated-style record: no raw secret anywhere, and
        the flow stays correlatable via the state fingerprint + provider."""
        event = {
            "event": "oauth_flow_initiated",
            "provider": "google",
            "state": self.OAUTH_STATE,
            "authorization_url": (
                "https://accounts.google.com/o/oauth2/auth"
                f"?client_id=x&state={self.OAUTH_STATE}&code_challenge=SENTINEL_CHALLENGE"
            ),
        }
        # authorization_url is not a content field → survives to the URL net.
        result = add_pii_filter(None, "debug", event)

        rendered = str(result)
        assert self.OAUTH_STATE not in rendered
        assert "SENTINEL_CHALLENGE" not in rendered
        # Correlation preserved.
        assert result["state"] == fingerprint_secret(self.OAUTH_STATE)
        assert result["provider"] == "google"


class TestFreeTextEventUrlRedaction:
    """FN-4 — the `event` field must not smuggle credentials out of the filter.

    `event` sits in `STRUCTLOG_META_FIELDS`, which bypasses sanitisation on
    purpose: an event NAME is a developer-controlled identifier, and running the
    full sanitizer over it produced false-positive redactions
    (`database_connection_pool_exhausted` matches the generic token regex).

    That bypass is correct for identifiers and wrong for free text. `event` is
    the only meta field that can hold either: a stdlib record routed into
    structlog puts the whole log MESSAGE there — including an access line with
    `?code=..&state=..`. So `event` gets exactly one narrow exception,
    `sanitize_url_query`, which rewrites only `?param=value` on a `?`/`&`
    boundary — a shape a snake_case event name cannot have.
    """

    OAUTH_CODE = "4/0AY0e-g7SENTINELCODE"
    OAUTH_STATE = "Zx8QpLmv3NrTfKe1Ab9YsWc7Hd2Gj5Uo0Vi4Rt6Bn"

    def test_oauth_callback_access_line_is_redacted(self):
        """An access log carrying a callback URL loses code and state."""
        event = {
            "event": (
                '127.0.0.1 - "GET /auth/google/callback'
                f"?code={self.OAUTH_CODE}&state={self.OAUTH_STATE}"
                ' HTTP/1.1" 302'
            )
        }

        result = add_pii_filter(None, "info", event)

        assert self.OAUTH_CODE not in result["event"]
        assert self.OAUTH_STATE not in result["event"]
        # The parameter names survive: the log still says which link was hit.
        assert "code=[REDACTED]" in result["event"]
        assert "state=[REDACTED]" in result["event"]

    def test_redaction_applies_at_every_level(self):
        """Credentials are stripped at DEBUG too — they are never "content"."""
        event = {"event": f"GET /cb?code={self.OAUTH_CODE}"}

        for method in ("debug", "info", "warning", "error", "critical"):
            result = add_pii_filter(None, method, dict(event))
            assert self.OAUTH_CODE not in result["event"], f"leaked at {method}"

    @pytest.mark.parametrize(
        "event_name",
        [
            "database_connection_pool_exhausted",
            "langfuse_callbacks_added_via_config_enrichment",
            "oauth_flow_initiated",
            "mcp_oauth_token_exchange_http_error",
            "telegram_webhook_rejected_no_secret",
        ],
    )
    def test_event_names_are_left_untouched(self, event_name):
        """The bypass still holds: identifiers are not rewritten.

        This is the regression the meta-field exemption exists to prevent, so it
        is asserted explicitly rather than assumed.
        """
        assert add_pii_filter(None, "info", {"event": event_name})["event"] == event_name

    @pytest.mark.parametrize(
        "message",
        [
            "GET /api/v1/conversations?limit=50&offset=0 200",
            "GET /api/v1/rag-spaces/3f2b?include=documents 200",
            "Application startup complete.",
            "Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
        ],
    )
    def test_benign_messages_are_not_over_redacted(self, message):
        """Non-sensitive query parameters and plain messages stay readable."""
        assert add_pii_filter(None, "info", {"event": message})["event"] == message

    def test_non_string_event_is_passed_through(self):
        """A non-str `event` must not raise (stdlib allows arbitrary objects)."""
        assert add_pii_filter(None, "info", {"event": 42})["event"] == 42

    def test_other_meta_fields_keep_their_bypass(self):
        """Only `event` gets the exception — the rest are untouched identifiers."""
        event = {
            "event": "x",
            "logger": "src.domains.auth.service",
            "level": "info",
            "lineno": 42,
            "filename": "service.py",
        }

        result = add_pii_filter(None, "info", dict(event))

        assert result["logger"] == event["logger"]
        assert result["level"] == event["level"]
        assert result["lineno"] == 42
        assert result["filename"] == "service.py"


class TestGeolocationQueryRedaction:
    """FN-4 — GPS coordinates in a logged URL are PII, not credentials.

    The logging policy forbids GPS coordinates at INFO. LIA builds static-map
    URLs carrying the user's exact position (`?lat=..&lng=..` for a location
    card, `?origin=48.85,2.35&dest=..` for a route), so a logged URL would pin
    the user on a map. `CONTENT_FIELD_NAMES` already covers these as log FIELD
    names; this covers them as query PARAMETERS, which is the shape they take
    inside a URL.
    """

    @pytest.mark.parametrize(
        ("url", "secrets"),
        [
            (
                "GET /api/v1/connectors/google-location/static-map?lat=48.8566&lng=2.3522 200",
                ["48.8566", "2.3522"],
            ),
            (
                "GET /connectors/google-routes/static-map"
                "?polyline=abc&origin=48.85,2.35&dest=45.76,4.83 200",
                ["48.85,2.35", "45.76,4.83"],
            ),
            (
                "https://maps.example/api?latitude=48.8566&longitude=2.3522",
                ["48.8566", "2.3522"],
            ),
        ],
        ids=["lat-lng", "origin-dest", "latitude-longitude"],
    )
    def test_coordinates_are_stripped_from_urls(self, url, secrets):
        """No coordinate survives in a logged URL."""
        result = add_pii_filter(None, "info", {"event": url})["event"]

        for secret in secrets:
            assert secret not in result, f"{secret} leaked: {result}"

    def test_non_coordinate_parameters_survive(self):
        """The redaction is scoped: the rest of the URL stays diagnosable."""
        result = add_pii_filter(
            None,
            "info",
            {"event": "GET /connectors/google-routes/static-map?polyline=abc123&origin=48.85,2.35"},
        )["event"]

        assert "polyline=abc123" in result
        assert "origin=[REDACTED]" in result

    def test_coordinates_in_a_dedicated_url_field_are_stripped_too(self):
        """The same net applies to a URL carried in a normal log field."""
        result = add_pii_filter(
            None,
            "debug",
            {"event": "static_map_requested", "map_url": "/static-map?lat=48.8566&lng=2.3522"},
        )

        assert "48.8566" not in str(result)
        assert "2.3522" not in str(result)


class TestEmailNeverReachesALogVerbatim:
    """SEC-012 — the account-lifecycle log lines, through the real filter.

    `pseudonymize_email` was covered in isolation, which proves the helper works
    and nothing about the pipeline that has to call it. These cases pin the
    actual events emitted by `AuthService._send_verification_email` and
    `_send_password_reset_email`: an address recorded in a log survives log
    shipping, retention and backups long after the account is gone.
    """

    @pytest.mark.parametrize("level", ["debug", "info", "warning", "error"])
    @pytest.mark.parametrize(
        "event",
        [
            "verification_email_sent",
            "verification_email_failed",
            "password_reset_email_sent",
            "password_reset_email_failed",
        ],
    )
    def test_the_address_is_pseudonymized_at_every_level(self, event, level):
        """Including DEBUG: there is no level at which the raw address is fine."""
        address = "victim@example.com"

        result = add_pii_filter(None, level, {"event": event, "email": address})

        assert address not in str(result)
        assert result["email"].startswith("email_hash_")

    def test_the_pseudonym_stays_stable_so_support_can_still_correlate(self):
        """Redaction must not cost diagnosability, or it gets removed later.

        The hash is deterministic: hashing the address of the person reporting
        "I never got the email" finds their lines. That is what makes it
        acceptable NOT to expose the address even at DEBUG.
        """
        first = add_pii_filter(None, "info", {"event": "x", "email": "a@b.test"})["email"]
        second = add_pii_filter(None, "debug", {"event": "y", "email": "a@b.test"})["email"]
        other = add_pii_filter(None, "info", {"event": "x", "email": "c@d.test"})["email"]

        assert first == second
        assert first != other

    def test_an_address_embedded_in_free_text_is_caught_too(self):
        """Not every leak arrives in a field named `email`."""
        result = add_pii_filter(
            None, "info", {"event": "could not deliver to victim@example.com after 3 tries"}
        )

        assert "victim@example.com" not in str(result)

    @pytest.mark.parametrize(
        "event_name",
        [
            "verification_email_sent",
            "user_email_address_updated",
            "oauth_flow_initiated",
            "fcm_token_unregistered",
            "telegram_webhook_duplicate_update",
            "global_rate_limit_check_failed",
        ],
    )
    def test_a_legitimate_event_name_is_never_rewritten(self, event_name):
        """The counterpart to the free-text sweep: names must survive intact.

        This is the risk the `event` bypass exists to avoid — a sanitizer that
        mangles identifiers makes every dashboard and alert query silently
        wrong. Names containing the word `email` are in the table on purpose.
        """
        result = add_pii_filter(None, "info", {"event": event_name})

        assert result["event"] == event_name
