"""Unit tests for vCard contacts normalizer."""

import pytest

from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)

_SAMPLE_VCARD = """\
BEGIN:VCARD
VERSION:3.0
FN:Alice Dupont
N:Dupont;Alice;;;
EMAIL;TYPE=WORK:alice@example.com
TEL;TYPE=CELL:+33612345678
ORG:Acme Corp
NOTE:VIP client
BDAY:1990-05-15
ADR;TYPE=HOME:;;123 Rue de Paris;Paris;;75001;France
END:VCARD"""


@pytest.mark.unit
class TestNormalizeVcard:
    """Tests for normalize_vcard()."""

    def test_full_vcard(self) -> None:
        """All standard fields are extracted from a valid vCard 3.0 string."""
        result = normalize_vcard(_SAMPLE_VCARD, resource_name="contacts/abc-123")

        assert result["resourceName"] == "contacts/abc-123"

        # Names
        assert result["names"][0]["displayName"] == "Alice Dupont"
        assert result["names"][0]["givenName"] == "Alice"
        assert result["names"][0]["familyName"] == "Dupont"

        # Email
        assert result["emailAddresses"][0]["value"] == "alice@example.com"

        # Phone
        assert result["phoneNumbers"][0]["value"] == "+33612345678"

        # Organization
        assert result["organizations"][0]["name"] == "Acme Corp"

        # Birthday
        assert result["birthdays"][0]["date"] == {"year": 1990, "month": 5, "day": 15}

        # Address
        assert result["addresses"][0]["streetAddress"] == "123 Rue de Paris"
        assert result["addresses"][0]["city"] == "Paris"
        assert result["addresses"][0]["country"] == "France"

        # Note
        assert result["biographies"][0]["value"] == "VIP client"

    def test_minimal_vcard(self) -> None:
        """A vCard with only FN produces names and no extra fields."""
        vcard_str = "BEGIN:VCARD\nVERSION:3.0\nFN:Bob\nN:Bob;;;;\nEND:VCARD"
        result = normalize_vcard(vcard_str)

        assert result["names"][0]["displayName"] == "Bob"
        assert "emailAddresses" not in result
        assert "phoneNumbers" not in result

    def test_invalid_vcard_returns_fallback(self) -> None:
        """Invalid vCard data returns a fallback dict with 'Unknown' name."""
        result = normalize_vcard("NOT A VCARD", resource_name="contacts/bad")

        assert result["resourceName"] == "contacts/bad"
        assert result["names"][0]["displayName"] == "Unknown"


@pytest.mark.unit
class TestBuildVcard:
    """Tests for build_vcard()."""

    def test_full_build(self) -> None:
        """Building with all params produces a parseable vCard with those fields."""
        vcard_str = build_vcard(
            name="Charlie Martin",
            email="charlie@example.com",
            phone="+33698765432",
            organization="Startup Inc",
            notes="Met at conference",
        )

        # Verify it round-trips through normalize_vcard
        result = normalize_vcard(vcard_str)

        assert result["names"][0]["displayName"] == "Charlie Martin"
        assert result["names"][0]["givenName"] == "Charlie"
        assert result["names"][0]["familyName"] == "Martin"
        assert result["emailAddresses"][0]["value"] == "charlie@example.com"
        assert result["phoneNumbers"][0]["value"] == "+33698765432"
        assert result["organizations"][0]["name"] == "Startup Inc"
        assert result["biographies"][0]["value"] == "Met at conference"

    def test_name_only(self) -> None:
        """Building with just a name produces a valid vCard."""
        vcard_str = build_vcard(name="Mononym")
        result = normalize_vcard(vcard_str)

        assert result["names"][0]["displayName"] == "Mononym"
        assert "emailAddresses" not in result


@pytest.mark.unit
class TestMergeVcardFields:
    """Tests for merge_vcard_fields()."""

    def test_update_name(self) -> None:
        """Updating the name changes FN and N while preserving other fields."""
        updated = merge_vcard_fields(_SAMPLE_VCARD, name="Alice Martin")
        result = normalize_vcard(updated)

        assert result["names"][0]["displayName"] == "Alice Martin"
        assert result["names"][0]["familyName"] == "Martin"
        # Original email should still be present
        assert result["emailAddresses"][0]["value"] == "alice@example.com"

    def test_update_email_and_phone(self) -> None:
        """Email and phone replacements work correctly."""
        updated = merge_vcard_fields(
            _SAMPLE_VCARD,
            email="newalice@example.com",
            phone="+33700000000",
        )
        result = normalize_vcard(updated)

        assert result["emailAddresses"][0]["value"] == "newalice@example.com"
        assert result["phoneNumbers"][0]["value"] == "+33700000000"

    def test_add_address(self) -> None:
        """Adding an address stores it as free-form street in ADR."""
        simple_vcard = "BEGIN:VCARD\nVERSION:3.0\nFN:Test\nN:Test;;;;\nEND:VCARD"
        updated = merge_vcard_fields(simple_vcard, address="42 Avenue des Champs")
        result = normalize_vcard(updated)

        assert any(
            a.get("streetAddress") == "42 Avenue des Champs" for a in result.get("addresses", [])
        )

    def test_invalid_existing_vcard_fallback(self) -> None:
        """When existing vCard is unparseable, a new card is built from params."""
        updated = merge_vcard_fields(
            "GARBAGE DATA",
            name="Fallback Person",
            email="fallback@example.com",
        )
        result = normalize_vcard(updated)

        assert result["names"][0]["displayName"] == "Fallback Person"
        assert result["emailAddresses"][0]["value"] == "fallback@example.com"
