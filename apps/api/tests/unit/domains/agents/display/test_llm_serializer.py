"""
Unit tests for LLM Serializer.

Tests the generic payload-to-text conversion for LLM context.
"""

from src.domains.agents.display.llm_serializer import (
    _extract_display_name,
    _humanize_key,
    _should_skip,
    payload_to_text,
)


class TestPayloadToText:
    """Test the main payload_to_text function."""

    def test_empty_payload(self):
        """Empty payload returns empty string."""
        assert payload_to_text({}) == ""
        assert payload_to_text(None) == ""

    def test_contact_payload_google_style(self):
        """Google Contacts API format with names array."""
        payload = {
            "names": [{"displayName": "Jean Dupont", "givenName": "Jean"}],
            "emailAddresses": [{"value": "jean@example.com"}],
            "phoneNumbers": [{"value": "+33 6 12 34 56 78"}],
            "id": "abc123",  # Should be skipped
            "etag": "xyz",  # Should be skipped
        }
        result = payload_to_text(payload)

        assert "Jean Dupont" in result
        assert "email addresses" in result
        assert "jean@example.com" in result
        assert "phone numbers" in result
        assert "+33 6 12 34 56 78" in result
        assert "abc123" not in result  # ID should be filtered
        assert "xyz" not in result  # etag should be filtered

    def test_email_payload(self):
        """Email payload with subject and sender."""
        payload = {
            "subject": "Meeting tomorrow",
            "from": "alice@example.com",
            "snippet": "Hi, let's meet at 10am...",
        }
        result = payload_to_text(payload)

        assert "Meeting tomorrow" in result
        assert "from" in result
        assert "alice@example.com" in result

    def test_event_payload(self):
        """Calendar event with summary and location."""
        payload = {
            "summary": "Team standup",
            "location": "Conference Room A",
            "start": "2024-01-15T10:00:00",
        }
        result = payload_to_text(payload)

        assert "Team standup" in result
        assert "location" in result
        assert "Conference Room A" in result

    def test_list_of_dicts_extraction(self):
        """Lists of dicts extract 'value' or 'name' fields."""
        payload = {
            "displayName": "Test",
            "addresses": [
                {"formatted": "123 Main St"},
                {"formatted": "456 Oak Ave"},
            ],
        }
        result = payload_to_text(payload)

        assert "123 Main St" in result
        assert "456 Oak Ave" in result

    def test_google_people_api_addresses(self):
        """Google People API uses 'formattedValue' for addresses."""
        payload = {
            "names": [{"displayName": "jean dupond"}],
            "addresses": [
                {"formattedValue": "123 Rue de Paris, 75001 Paris", "type": "home"},
            ],
            "emailAddresses": [{"value": "jean@example.com"}],
        }
        result = payload_to_text(payload)

        assert "jean dupond" in result
        assert "123 Rue de Paris" in result
        assert "jean@example.com" in result

    def test_max_items_limit(self):
        """Max items limits the number of values shown."""
        payload = {
            "name": "Test",
            "emails": [
                {"value": "a@x.com"},
                {"value": "b@x.com"},
                {"value": "c@x.com"},
                {"value": "d@x.com"},
                {"value": "e@x.com"},
            ],
        }
        result = payload_to_text(payload, max_items=2)

        assert "a@x.com" in result
        assert "b@x.com" in result
        assert "(+3)" in result  # 5-2 = 3 remaining

    def test_truncation(self):
        """Long values are truncated."""
        payload = {
            "name": "Test",
            "location": "A"
            * 100,  # Use location instead of description (which is in CONTENT_FIELDS)
        }
        result = payload_to_text(payload, max_length=20)

        # Value should be truncated to 20 chars with "..."
        assert "..." in result


class TestExtractDisplayName:
    """Test display name extraction."""

    def test_google_names_array(self):
        """Extract from Google-style names array."""
        payload = {"names": [{"displayName": "John Doe"}]}
        assert _extract_display_name(payload) == "John Doe"

    def test_direct_display_name(self):
        """Extract from displayName field."""
        payload = {"displayName": "Jane Doe"}
        assert _extract_display_name(payload) == "Jane Doe"

    def test_title_fallback(self):
        """Fall back to title if no name."""
        payload = {"title": "Meeting Notes"}
        assert _extract_display_name(payload) == "Meeting Notes"

    def test_subject_fallback(self):
        """Fall back to subject for emails."""
        payload = {"subject": "Important: Action Required"}
        assert _extract_display_name(payload) == "Important: Action Required"

    def test_no_name_found(self):
        """Return default when no name found."""
        payload = {"randomField": "value"}
        assert _extract_display_name(payload) == "(sans nom)"


class TestShouldSkip:
    """Test field skip logic."""

    def test_skip_ids(self):
        """IDs should be skipped."""
        assert _should_skip("id") is True
        assert _should_skip("ID") is True
        assert _should_skip("etag") is True

    def test_skip_metadata(self):
        """Metadata fields should be skipped."""
        assert _should_skip("metadata") is True
        assert _should_skip("sources") is True

    def test_skip_photos(self):
        """Photo fields should be skipped."""
        assert _should_skip("photos") is True
        assert _should_skip("thumbnailLink") is True

    def test_skip_private_fields(self):
        """Fields starting with _ should be skipped."""
        assert _should_skip("_internal") is True
        assert _should_skip("_raw_data") is True

    def test_keep_normal_fields(self):
        """Normal fields should not be skipped."""
        assert _should_skip("emailAddresses") is False
        assert _should_skip("phoneNumbers") is False
        assert _should_skip("location") is False


class TestHumanizeKey:
    """Test key humanization."""

    def test_camel_case(self):
        """CamelCase becomes spaced lowercase."""
        assert _humanize_key("emailAddresses") == "email addresses"
        assert _humanize_key("phoneNumbers") == "phone numbers"

    def test_snake_case(self):
        """snake_case becomes spaced lowercase."""
        assert _humanize_key("email_address") == "email address"
        assert _humanize_key("phone_number") == "phone number"

    def test_simple_key(self):
        """Simple keys stay lowercase."""
        assert _humanize_key("email") == "email"
        assert _humanize_key("location") == "location"
