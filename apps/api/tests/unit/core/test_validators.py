"""
Unit tests for core/validators.py.

Tests email validation, timezone validation, and common timezone listing.
"""

import pytest

from src.core.validators import (
    EMAIL_REGEX,
    get_common_timezones,
    validate_email,
    validate_timezone,
)


@pytest.mark.unit
class TestEmailValidation:
    """Test email validation functionality."""

    def test_valid_simple_email(self):
        """Test validation of simple email addresses."""
        valid_emails = [
            "user@example.com",
            "test@domain.org",
            "john.doe@company.co.uk",
        ]
        for email in valid_emails:
            assert validate_email(email) is True, f"Expected valid: {email}"

    def test_valid_complex_emails(self):
        """Test validation of complex but valid email addresses."""
        valid_emails = [
            "user+tag@example.com",
            "user.name@subdomain.domain.com",
            "user_name@example.io",
            "user123@example456.net",
            "a@b.co",  # Minimum valid email
            "firstname.lastname@company.travel",  # Long TLD
        ]
        for email in valid_emails:
            assert validate_email(email) is True, f"Expected valid: {email}"

    def test_invalid_email_no_at_symbol(self):
        """Test rejection of emails without @ symbol."""
        assert validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        """Test rejection of emails without domain."""
        assert validate_email("user@") is False

    def test_invalid_email_no_tld(self):
        """Test rejection of emails without TLD (top-level domain)."""
        invalid_emails = [
            "user@example",
            "user@domain",
            "user@hotmail",
        ]
        for email in invalid_emails:
            assert validate_email(email) is False, f"Expected invalid: {email}"

    def test_invalid_email_with_spaces(self):
        """Test rejection of emails with spaces."""
        invalid_emails = [
            "user @example.com",
            "user@ example.com",
            " user@example.com",
            "user@example.com ",
        ]
        for email in invalid_emails:
            # Note: spaces at start/end are trimmed by the validator
            # but internal spaces should fail
            if email.strip() != email:
                # Leading/trailing spaces are trimmed
                assert validate_email(email) is True
            else:
                assert validate_email(email) is False, f"Expected invalid: {email}"

    def test_invalid_email_multiple_at_symbols(self):
        """Test rejection of emails with multiple @ symbols."""
        assert validate_email("user@@example.com") is False
        assert validate_email("user@domain@example.com") is False

    def test_invalid_email_empty_string(self):
        """Test rejection of empty string."""
        assert validate_email("") is False

    def test_invalid_email_none(self):
        """Test rejection of None value."""
        assert validate_email(None) is False  # type: ignore[arg-type]

    def test_invalid_email_non_string(self):
        """Test rejection of non-string types."""
        assert validate_email(123) is False  # type: ignore[arg-type]
        assert validate_email(["user@example.com"]) is False  # type: ignore[arg-type]
        assert validate_email({"email": "user@example.com"}) is False  # type: ignore[arg-type]

    def test_email_with_whitespace_trimming(self):
        """Test that leading/trailing whitespace is trimmed."""
        assert validate_email("  user@example.com  ") is True

    def test_email_regex_pattern_exists(self):
        """Test that EMAIL_REGEX is properly compiled."""
        assert EMAIL_REGEX is not None
        assert EMAIL_REGEX.pattern


@pytest.mark.unit
class TestTimezoneValidation:
    """Test timezone validation functionality."""

    def test_valid_common_timezones(self):
        """Test validation of common IANA timezones."""
        valid_timezones = [
            "UTC",
            "Europe/Paris",
            "Europe/London",
            "America/New_York",
            "America/Los_Angeles",
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Australia/Sydney",
        ]
        for tz in valid_timezones:
            assert validate_timezone(tz) is True, f"Expected valid: {tz}"

    def test_valid_regional_timezones(self):
        """Test validation of various regional timezones."""
        valid_timezones = [
            "Europe/Berlin",
            "Europe/Madrid",
            "Africa/Cairo",
            "Asia/Dubai",
            "Pacific/Auckland",
        ]
        for tz in valid_timezones:
            assert validate_timezone(tz) is True, f"Expected valid: {tz}"

    def test_invalid_timezone_fake_zone(self):
        """Test rejection of non-existent timezones."""
        invalid_timezones = [
            "Invalid/Zone",
            "Fake/Timezone",
            "NotA/RealPlace",
            "Europe/FakeCity",
        ]
        for tz in invalid_timezones:
            assert validate_timezone(tz) is False, f"Expected invalid: {tz}"

    def test_invalid_timezone_empty_string(self):
        """Test rejection of empty string."""
        assert validate_timezone("") is False

    def test_invalid_timezone_malformed(self):
        """Test rejection of malformed timezone strings."""
        invalid_timezones = [
            "europe/paris",  # Case-sensitive
            "EUROPE/PARIS",  # Wrong case
            "Europe Paris",  # Space instead of slash
            "Paris",  # Missing region
            "/Europe/Paris",  # Leading slash
        ]
        for tz in invalid_timezones:
            assert validate_timezone(tz) is False, f"Expected invalid: {tz}"

    def test_timezone_with_numeric_offset(self):
        """Test timezones with special characters."""
        # Some systems support Etc/GMT+X timezones
        # These should work if in available_timezones()
        result_gmt = validate_timezone("Etc/GMT")
        # We just verify it doesn't crash - actual validity depends on system
        assert isinstance(result_gmt, bool)


@pytest.mark.unit
class TestGetCommonTimezones:
    """Test the get_common_timezones function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        result = get_common_timezones()
        assert isinstance(result, dict)

    def test_contains_major_regions(self):
        """Test that result contains major timezone regions."""
        result = get_common_timezones()
        expected_regions = ["Europe", "America", "Asia", "Pacific", "Africa"]
        for region in expected_regions:
            assert region in result, f"Missing region: {region}"

    def test_europe_contains_paris(self):
        """Test that Europe region contains Paris."""
        result = get_common_timezones()
        assert "Europe" in result
        assert "Europe/Paris" in result["Europe"]

    def test_america_contains_new_york(self):
        """Test that America region contains New York."""
        result = get_common_timezones()
        assert "America" in result
        assert "America/New_York" in result["America"]

    def test_asia_contains_tokyo(self):
        """Test that Asia region contains Tokyo."""
        result = get_common_timezones()
        assert "Asia" in result
        assert "Asia/Tokyo" in result["Asia"]

    def test_all_timezones_are_valid(self):
        """Test that all returned timezones are valid IANA timezones."""
        result = get_common_timezones()
        for _region, timezones in result.items():
            for tz in timezones:
                assert validate_timezone(tz), f"Invalid timezone in result: {tz}"

    def test_timezones_match_region(self):
        """Test that each timezone starts with its region prefix."""
        result = get_common_timezones()
        for region, timezones in result.items():
            for tz in timezones:
                assert tz.startswith(f"{region}/"), f"Timezone {tz} doesn't match region {region}"

    def test_timezones_are_sorted(self):
        """Test that timezones within each region are sorted."""
        result = get_common_timezones()
        for region, timezones in result.items():
            assert timezones == sorted(timezones), f"Timezones in {region} are not sorted"

    def test_australia_handled_separately(self):
        """Test that Australia timezones are grouped correctly."""
        result = get_common_timezones()
        # Australia timezones should be under 'Australia' key
        # or potentially grouped with Pacific
        if "Australia" in result:
            assert len(result["Australia"]) > 0
            assert "Australia/Sydney" in result["Australia"]

    def test_no_duplicate_timezones(self):
        """Test that there are no duplicate timezones."""
        result = get_common_timezones()
        all_timezones = []
        for timezones in result.values():
            all_timezones.extend(timezones)

        assert len(all_timezones) == len(set(all_timezones)), "Duplicate timezones found"

    def test_minimum_timezone_count(self):
        """Test that a reasonable number of timezones are returned."""
        result = get_common_timezones()
        total_count = sum(len(tzs) for tzs in result.values())
        # Should have at least 40 common timezones
        assert total_count >= 40, f"Expected at least 40 timezones, got {total_count}"
