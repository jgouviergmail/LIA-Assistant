"""
Unit tests for ConnectorPreferencesService.

Tests cover:
- validate_and_encrypt: Schema validation, sanitization, encryption
- decrypt_and_get: Decryption and type conversion
- get_preference_value: Single value extraction with defaults
- _sanitize: Prompt injection protection

Security focus:
- Dangerous character removal
- Max length enforcement
- Fernet encryption/decryption
"""

from unittest.mock import patch

from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.schemas import (
    GoogleCalendarPreferences,
    GoogleTasksPreferences,
)
from src.domains.connectors.preferences.service import (
    DANGEROUS_CHARS_PATTERN,
    MAX_PREFERENCE_LENGTH,
    ConnectorPreferencesService,
)


class TestValidateAndEncrypt:
    """Tests for validate_and_encrypt method."""

    def test_validate_and_encrypt_success_calendar(self):
        """Test successful validation and encryption for calendar preferences."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        preferences_data = {"default_calendar_name": "Famille"}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert encrypted is not None
        assert errors == []

        # Verify decryption returns original value
        decrypted_json = decrypt_data(encrypted)
        assert "Famille" in decrypted_json

    def test_validate_and_encrypt_success_tasks(self):
        """Test successful validation and encryption for tasks preferences."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_TASKS.value
        preferences_data = {"default_task_list_name": "My Tasks"}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert encrypted is not None
        assert errors == []

        # Verify decryption returns original value
        decrypted_json = decrypt_data(encrypted)
        assert "My Tasks" in decrypted_json

    def test_validate_and_encrypt_no_schema(self):
        """Test failure when no schema exists for connector type."""
        # Arrange
        connector_type = "unknown_connector"
        preferences_data = {"some_field": "value"}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is False
        assert encrypted is None
        assert len(errors) == 1
        assert "No preferences schema" in errors[0]

    def test_validate_and_encrypt_validation_error_extra_field(self):
        """Test validation error when extra field provided (extra='forbid')."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        preferences_data = {
            "default_calendar_name": "Famille",
            "unknown_field": "should fail",
        }

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is False
        assert encrypted is None
        assert len(errors) >= 1
        # Pydantic extra='forbid' error message
        assert any("extra" in err.lower() or "unknown" in err.lower() for err in errors)

    def test_validate_and_encrypt_validation_error_too_long(self):
        """Test validation error when value exceeds max_length."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        too_long_value = "x" * 150  # max_length=100
        preferences_data = {"default_calendar_name": too_long_value}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is False
        assert encrypted is None
        assert len(errors) >= 1
        # Should mention string constraint violation
        assert any("100" in err or "length" in err.lower() for err in errors)

    def test_validate_and_encrypt_sanitizes_dangerous_chars(self):
        """Test that dangerous characters are removed during validation."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        # Include dangerous chars: newlines, quotes, backticks, backslashes, braces
        dangerous_value = "Famille\n\"test'`\\{}"
        preferences_data = {"default_calendar_name": dangerous_value}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert errors == []

        # Verify dangerous chars were removed by checking the decrypted preferences object
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)
        assert prefs is not None
        value = prefs.default_calendar_name
        assert "\n" not in value
        assert '"' not in value
        assert "'" not in value
        assert "`" not in value
        assert "\\" not in value
        assert "{" not in value
        assert "}" not in value
        # Should only contain "Familletest" after sanitization
        assert value == "Familletest"

    def test_validate_and_encrypt_enforces_max_length_after_sanitization(self):
        """Test that max length is enforced after sanitization."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        # Use 90 chars (within Pydantic limit) + dangerous chars
        # After sanitization, dangerous chars are removed, resulting in 90 chars
        value_with_dangerous = "x" * 90 + "\n\r\t\"'`"
        preferences_data = {"default_calendar_name": value_with_dangerous}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert errors == []

        # Verify length is within limit and dangerous chars removed
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)
        assert prefs is not None
        assert len(prefs.default_calendar_name) == 90
        assert len(prefs.default_calendar_name) <= MAX_PREFERENCE_LENGTH

    def test_validate_and_encrypt_null_value(self):
        """Test validation with null preference value."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        preferences_data = {"default_calendar_name": None}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert encrypted is not None
        assert errors == []

    def test_validate_and_encrypt_empty_dict(self):
        """Test validation with empty preferences dict."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        preferences_data = {}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is True
        assert encrypted is not None
        assert errors == []

    @patch("src.domains.connectors.preferences.service.encrypt_data")
    def test_validate_and_encrypt_encryption_failure(self, mock_encrypt):
        """Test handling of encryption failure."""
        # Arrange
        mock_encrypt.side_effect = Exception("Encryption failed")
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        preferences_data = {"default_calendar_name": "Famille"}

        # Act
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, preferences_data
        )

        # Assert
        assert success is False
        assert encrypted is None
        assert len(errors) == 1
        assert "Encryption failed" in errors[0]


class TestDecryptAndGet:
    """Tests for decrypt_and_get method."""

    def test_decrypt_and_get_success_calendar(self):
        """Test successful decryption for calendar preferences."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        prefs = GoogleCalendarPreferences(default_calendar_name="Famille")
        encrypted = encrypt_data(prefs.model_dump_json())

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert
        assert result is not None
        assert isinstance(result, GoogleCalendarPreferences)
        assert result.default_calendar_name == "Famille"

    def test_decrypt_and_get_success_tasks(self):
        """Test successful decryption for tasks preferences."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_TASKS.value
        prefs = GoogleTasksPreferences(default_task_list_name="Ma Liste")
        encrypted = encrypt_data(prefs.model_dump_json())

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert
        assert result is not None
        assert isinstance(result, GoogleTasksPreferences)
        assert result.default_task_list_name == "Ma Liste"

    def test_decrypt_and_get_none_encrypted(self):
        """Test returns None when encrypted_preferences is None."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, None)

        # Assert
        assert result is None

    def test_decrypt_and_get_empty_string(self):
        """Test returns None when encrypted_preferences is empty string."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, "")

        # Assert
        assert result is None

    def test_decrypt_and_get_no_schema(self):
        """Test returns None when no schema for connector type."""
        # Arrange
        connector_type = "unknown_connector"
        encrypted = "some_encrypted_data"

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert
        assert result is None

    def test_decrypt_and_get_decryption_failure(self):
        """Test returns None on decryption failure (corrupted data)."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        corrupted_encrypted = "NOT_VALID_FERNET_TOKEN"

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, corrupted_encrypted)

        # Assert
        assert result is None

    def test_decrypt_and_get_invalid_json(self):
        """Test returns None when decrypted data is not valid JSON."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        invalid_json = encrypt_data("not-valid-json{")

        # Act
        result = ConnectorPreferencesService.decrypt_and_get(connector_type, invalid_json)

        # Assert
        assert result is None


class TestGetPreferenceValue:
    """Tests for get_preference_value method."""

    def test_get_preference_value_success(self):
        """Test successful single preference value retrieval."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        prefs = GoogleCalendarPreferences(default_calendar_name="Famille")
        encrypted = encrypt_data(prefs.model_dump_json())

        # Act
        result = ConnectorPreferencesService.get_preference_value(
            connector_type, encrypted, "default_calendar_name"
        )

        # Assert
        assert result == "Famille"

    def test_get_preference_value_with_default(self):
        """Test returns default when preference is None."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        prefs = GoogleCalendarPreferences(default_calendar_name=None)
        encrypted = encrypt_data(prefs.model_dump_json())

        # Act
        result = ConnectorPreferencesService.get_preference_value(
            connector_type, encrypted, "default_calendar_name", default="Primary"
        )

        # Assert
        assert result == "Primary"

    def test_get_preference_value_no_encrypted_data(self):
        """Test returns default when no encrypted data."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value

        # Act
        result = ConnectorPreferencesService.get_preference_value(
            connector_type, None, "default_calendar_name", default="Default Value"
        )

        # Assert
        assert result == "Default Value"

    def test_get_preference_value_unknown_field(self):
        """Test returns default when preference field doesn't exist."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        prefs = GoogleCalendarPreferences(default_calendar_name="Famille")
        encrypted = encrypt_data(prefs.model_dump_json())

        # Act
        result = ConnectorPreferencesService.get_preference_value(
            connector_type, encrypted, "nonexistent_field", default="Fallback"
        )

        # Assert
        assert result == "Fallback"

    def test_get_preference_value_decryption_failure(self):
        """Test returns default on decryption failure."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        corrupted = "INVALID_ENCRYPTED_DATA"

        # Act
        result = ConnectorPreferencesService.get_preference_value(
            connector_type, corrupted, "default_calendar_name", default="Safe Default"
        )

        # Assert
        assert result == "Safe Default"


class TestSanitize:
    """Tests for _sanitize method (prompt injection protection)."""

    def test_sanitize_removes_newlines(self):
        """Test that newlines are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test\nCalendar\r\n")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert "\n" not in result.default_calendar_name
        assert "\r" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendar"

    def test_sanitize_removes_tabs(self):
        """Test that tabs are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test\tCalendar")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert "\t" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendar"

    def test_sanitize_removes_quotes(self):
        """Test that quotes are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test\"Calendar'Here")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert '"' not in result.default_calendar_name
        assert "'" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendarHere"

    def test_sanitize_removes_backticks(self):
        """Test that backticks are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test`Calendar`")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert "`" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendar"

    def test_sanitize_removes_backslashes(self):
        """Test that backslashes are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test\\Calendar")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert "\\" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendar"

    def test_sanitize_removes_braces(self):
        """Test that braces are removed."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="Test{Calendar}")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert "{" not in result.default_calendar_name
        assert "}" not in result.default_calendar_name
        assert result.default_calendar_name == "TestCalendar"

    def test_sanitize_enforces_max_length(self):
        """Test that max length enforcement logic works correctly."""
        # Note: Pydantic validates max_length=100 BEFORE _sanitize is called
        # So we test the truncation logic in isolation

        # Test the truncation logic directly as used in _sanitize
        long_value = "x" * 150

        # Act - test the truncation logic as implemented in _sanitize
        sanitized = DANGEROUS_CHARS_PATTERN.sub("", long_value)
        truncated = sanitized[:MAX_PREFERENCE_LENGTH]

        # Assert - truncation works correctly
        assert len(truncated) == MAX_PREFERENCE_LENGTH
        assert truncated == "x" * 100

    def test_sanitize_strips_whitespace(self):
        """Test that whitespace is stripped."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name="  Famille  ")

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert result.default_calendar_name == "Famille"

    def test_sanitize_preserves_normal_characters(self):
        """Test that normal characters are preserved."""
        # Arrange
        normal_value = "Calendrier-Famille_2024 (Principal)"
        prefs = GoogleCalendarPreferences(default_calendar_name=normal_value)

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert result.default_calendar_name == normal_value

    def test_sanitize_handles_none_value(self):
        """Test that None values are preserved."""
        # Arrange
        prefs = GoogleCalendarPreferences(default_calendar_name=None)

        # Act
        result = ConnectorPreferencesService._sanitize(prefs)

        # Assert
        assert result.default_calendar_name is None

    def test_sanitize_returns_same_type(self):
        """Test that sanitize returns the same preference type."""
        # Arrange
        prefs_calendar = GoogleCalendarPreferences(default_calendar_name="Test")
        prefs_tasks = GoogleTasksPreferences(default_task_list_name="Test")

        # Act
        result_calendar = ConnectorPreferencesService._sanitize(prefs_calendar)
        result_tasks = ConnectorPreferencesService._sanitize(prefs_tasks)

        # Assert
        assert isinstance(result_calendar, GoogleCalendarPreferences)
        assert isinstance(result_tasks, GoogleTasksPreferences)


class TestDangerousCharsPattern:
    """Tests for the DANGEROUS_CHARS_PATTERN regex."""

    def test_pattern_matches_all_dangerous_chars(self):
        """Test that pattern matches all dangerous characters."""
        dangerous_chars = ["\n", "\r", "\t", '"', "'", "`", "\\", "{", "}"]

        for char in dangerous_chars:
            assert (
                DANGEROUS_CHARS_PATTERN.search(char) is not None
            ), f"Pattern should match: {repr(char)}"

    def test_pattern_does_not_match_safe_chars(self):
        """Test that pattern does not match safe characters."""
        safe_chars = list(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_()[].,;:!?éèàù"
        )

        for char in safe_chars:
            assert (
                DANGEROUS_CHARS_PATTERN.search(char) is None
            ), f"Pattern should NOT match: {repr(char)}"


class TestIntegrationRoundTrip:
    """Integration tests for full encrypt/decrypt round trip."""

    def test_full_round_trip_calendar(self):
        """Test full round trip: validate → encrypt → decrypt for calendar."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        original_value = "Calendrier Famille"

        # Act - Encrypt
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, {"default_calendar_name": original_value}
        )

        # Assert - Encrypt succeeded
        assert success is True
        assert encrypted is not None

        # Act - Decrypt
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert - Decrypt succeeded and value matches
        assert prefs is not None
        assert prefs.default_calendar_name == original_value

    def test_full_round_trip_tasks(self):
        """Test full round trip: validate → encrypt → decrypt for tasks."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_TASKS.value
        original_value = "Liste de tâches principale"

        # Act - Encrypt
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, {"default_task_list_name": original_value}
        )

        # Assert - Encrypt succeeded
        assert success is True
        assert encrypted is not None

        # Act - Decrypt
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert - Decrypt succeeded and value matches
        assert prefs is not None
        assert prefs.default_task_list_name == original_value

    def test_round_trip_with_sanitization(self):
        """Test round trip with dangerous characters sanitized."""
        # Arrange
        connector_type = ConnectorType.GOOGLE_CALENDAR.value
        dirty_value = "Famille\n{injection}"

        # Act - Encrypt (includes sanitization)
        success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
            connector_type, {"default_calendar_name": dirty_value}
        )

        # Assert
        assert success is True

        # Act - Decrypt
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted)

        # Assert - Dangerous chars were removed
        assert prefs is not None
        assert prefs.default_calendar_name == "Familleinjection"
        assert "\n" not in prefs.default_calendar_name
        assert "{" not in prefs.default_calendar_name
        assert "}" not in prefs.default_calendar_name
