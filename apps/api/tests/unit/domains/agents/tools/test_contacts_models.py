"""
Unit tests for contacts Pydantic models and validators.

Phase: Session 16 - Tools Modules (tools/contacts_models)
Created: 2025-11-20

Focus: Pydantic field validators (raise ValueError paths)
Target Coverage: 89% → 100% (9 missing lines in 3 validators)
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.tools.contacts_models import (
    ContactAddress,
    ContactBasic,
    ContactDetailed,
    ContactEmail,
    ContactName,
    ContactPhone,
    GetContactDetailsInput,
    GetContactDetailsOutput,
    ListContactsInput,
    ListContactsOutput,
    SearchContactsInput,
    SearchContactsOutput,
)


class TestContactBasic:
    """Tests for ContactBasic model and validators."""

    def test_contact_basic_valid_resource_name(self):
        """Test ContactBasic with valid resource_name format."""
        contact = ContactBasic(
            resource_name="people/c1234567890",
            name=ContactName(display="John Doe"),
        )

        assert contact.resource_name == "people/c1234567890"
        assert contact.name.display == "John Doe"

    def test_contact_basic_invalid_resource_name_raises(self):
        """Test that resource_name without 'people/' prefix raises ValueError (Lines 120-122)."""
        with pytest.raises(ValidationError) as exc_info:
            ContactBasic(
                resource_name="invalid_format_12345",  # Missing 'people/' prefix
            )

        # Pydantic V2 wraps ValueError in ValidationError
        error_msg = str(exc_info.value)
        assert "resource_name must start with 'people/'" in error_msg

    def test_contact_basic_with_all_fields(self):
        """Test ContactBasic with all optional fields populated."""
        contact = ContactBasic(
            resource_name="people/c9999999999",
            name=ContactName(
                display="Jane Smith",
                given_name="Jane",
                family_name="Smith",
            ),
            emails=[ContactEmail(value="jane@example.com", type="work")],
            phones=[ContactPhone(value="+1234567890", type="mobile")],
            addresses=[
                ContactAddress(
                    formatted_value="123 Main St, City, State",
                    type="home",
                )
            ],
            birthdays=["1990-01-15"],
        )

        assert len(contact.emails) == 1
        assert len(contact.phones) == 1
        assert len(contact.addresses) == 1
        assert len(contact.birthdays) == 1


class TestSearchContactsInput:
    """Tests for SearchContactsInput model and validators."""

    def test_search_contacts_input_valid(self):
        """Test SearchContactsInput with valid query."""
        input_data = SearchContactsInput(
            query="Jean Dupond",
            max_results=20,
            fields=["names", "emailAddresses"],
            force_refresh=False,
        )

        assert input_data.query == "Jean Dupond"
        assert input_data.max_results == 20
        assert len(input_data.fields) == 2

    def test_search_contacts_input_query_stripped(self):
        """Test that query is stripped of whitespace."""
        input_data = SearchContactsInput(query="  Jean  ")

        # Validator strips whitespace
        assert input_data.query == "Jean"

    def test_search_contacts_input_empty_query_raises(self):
        """Test that empty query (after strip) raises ValueError (Lines 175-177)."""
        with pytest.raises(ValidationError) as exc_info:
            SearchContactsInput(query="   ")  # Only whitespace

        error_msg = str(exc_info.value)
        assert "query must not be empty" in error_msg

    def test_search_contacts_input_defaults(self):
        """Test SearchContactsInput default values."""
        input_data = SearchContactsInput(query="test")

        assert input_data.max_results == 10  # Default
        assert input_data.fields is None  # Default
        assert input_data.force_refresh is False  # Default

    def test_search_contacts_input_max_results_validation(self):
        """Test max_results field constraints (ge=1, le=50)."""
        # Valid: min boundary
        input_min = SearchContactsInput(query="test", max_results=1)
        assert input_min.max_results == 1

        # Valid: max boundary
        input_max = SearchContactsInput(query="test", max_results=50)
        assert input_max.max_results == 50

        # Invalid: below min
        with pytest.raises(ValidationError):
            SearchContactsInput(query="test", max_results=0)

        # Invalid: above max
        with pytest.raises(ValidationError):
            SearchContactsInput(query="test", max_results=51)


class TestSearchContactsOutput:
    """Tests for SearchContactsOutput model."""

    def test_search_contacts_output_with_contacts(self):
        """Test SearchContactsOutput with contact results."""
        contacts = [
            ContactBasic(
                resource_name="people/c111",
                name=ContactName(display="Contact 1"),
            ),
            ContactBasic(
                resource_name="people/c222",
                name=ContactName(display="Contact 2"),
            ),
        ]

        output = SearchContactsOutput(
            contacts=contacts,
            total_found=2,
            from_cache=True,
        )

        assert len(output.contacts) == 2
        assert output.total_found == 2
        assert output.from_cache is True

    def test_search_contacts_output_defaults(self):
        """Test SearchContactsOutput default values."""
        output = SearchContactsOutput()

        assert output.contacts == []
        assert output.total_found == 0
        assert output.from_cache is False


class TestListContactsInput:
    """Tests for ListContactsInput model."""

    def test_list_contacts_input_valid(self):
        """Test ListContactsInput with valid parameters."""
        input_data = ListContactsInput(
            limit=50,
            fields=["names", "emailAddresses", "phoneNumbers"],
            force_refresh=True,
        )

        assert input_data.limit == 50
        assert len(input_data.fields) == 3
        assert input_data.force_refresh is True

    def test_list_contacts_input_defaults(self):
        """Test ListContactsInput default values."""
        input_data = ListContactsInput()

        assert input_data.limit == 10
        assert input_data.fields is None
        assert input_data.force_refresh is False

    def test_list_contacts_input_limit_validation(self):
        """Test limit field constraints (ge=1, le=100)."""
        # Valid boundaries
        ListContactsInput(limit=1)
        ListContactsInput(limit=100)

        # Invalid: below min
        with pytest.raises(ValidationError):
            ListContactsInput(limit=0)

        # Invalid: above max
        with pytest.raises(ValidationError):
            ListContactsInput(limit=101)


class TestListContactsOutput:
    """Tests for ListContactsOutput model."""

    def test_list_contacts_output_with_pagination(self):
        """Test ListContactsOutput with pagination."""
        contacts = [
            ContactBasic(resource_name=f"people/c{i}", name=ContactName(display=f"Contact {i}"))
            for i in range(10)
        ]

        output = ListContactsOutput(
            contacts=contacts,
            total_returned=10,
            has_more=True,
            from_cache=False,
        )

        assert len(output.contacts) == 10
        assert output.total_returned == 10
        assert output.has_more is True
        assert output.from_cache is False

    def test_list_contacts_output_defaults(self):
        """Test ListContactsOutput default values."""
        output = ListContactsOutput()

        assert output.contacts == []
        assert output.total_returned == 0
        assert output.has_more is False
        assert output.from_cache is False


class TestGetContactDetailsInput:
    """Tests for GetContactDetailsInput model and validators."""

    def test_get_contact_details_input_valid(self):
        """Test GetContactDetailsInput with valid resource_name."""
        input_data = GetContactDetailsInput(
            resource_name="people/c1234567890",
            force_refresh=False,
        )

        assert input_data.resource_name == "people/c1234567890"
        assert input_data.force_refresh is False

    def test_get_contact_details_input_invalid_resource_name_raises(self):
        """Test that resource_name without 'people/c' prefix raises ValidationError (pattern validation)."""
        with pytest.raises(ValidationError) as exc_info:
            GetContactDetailsInput(
                resource_name="people/invalid123",  # Missing 'c' after 'people/'
            )

        error_msg = str(exc_info.value)
        # Pydantic V2 pattern validation error
        assert "string_pattern_mismatch" in error_msg or "String should match pattern" in error_msg

    def test_get_contact_details_input_pattern_validation(self):
        r"""Test regex pattern validation (^people/c\d+$)."""
        # Valid: correct format
        GetContactDetailsInput(resource_name="people/c123")
        GetContactDetailsInput(resource_name="people/c9999999999")

        # Invalid: wrong format (caught by regex pattern before validator)
        with pytest.raises(ValidationError):
            GetContactDetailsInput(resource_name="invalid")

        # Invalid: missing 'c' (caught by custom validator)
        with pytest.raises(ValidationError):
            GetContactDetailsInput(resource_name="people/123")


class TestGetContactDetailsOutput:
    """Tests for GetContactDetailsOutput model."""

    def test_get_contact_details_output_valid(self):
        """Test GetContactDetailsOutput with detailed contact."""
        detailed_contact = ContactDetailed(
            resource_name="people/c555",
            name=ContactName(display="Detailed Contact", given_name="Detailed"),
            emails=[ContactEmail(value="detailed@example.com")],
            organizations=[{"name": "Acme Corp", "title": "CEO"}],
            biographies=[{"value": "Software engineer"}],
        )

        output = GetContactDetailsOutput(
            contact=detailed_contact,
            from_cache=True,
        )

        assert output.contact.resource_name == "people/c555"
        assert output.from_cache is True
        assert len(output.contact.organizations) == 1

    def test_get_contact_details_output_defaults(self):
        """Test GetContactDetailsOutput default from_cache."""
        contact = ContactDetailed(resource_name="people/c999")
        output = GetContactDetailsOutput(contact=contact)

        assert output.from_cache is False


class TestContactName:
    """Tests for ContactName model."""

    def test_contact_name_full(self):
        """Test ContactName with all fields."""
        name = ContactName(
            display="Dr. John Robert Doe Jr.",
            given_name="John",
            family_name="Doe",
            middle_name="Robert",
            prefix="Dr.",
            suffix="Jr.",
        )

        assert name.display == "Dr. John Robert Doe Jr."
        assert name.given_name == "John"
        assert name.middle_name == "Robert"

    def test_contact_name_minimal(self):
        """Test ContactName with minimal fields (all optional)."""
        name = ContactName()

        assert name.display is None
        assert name.given_name is None


class TestContactEmail:
    """Tests for ContactEmail model."""

    def test_contact_email_with_type(self):
        """Test ContactEmail with type."""
        email = ContactEmail(
            value="test@example.com",
            type="work",
            formatted_type="Work",
        )

        assert email.value == "test@example.com"
        assert email.type == "work"


class TestContactPhone:
    """Tests for ContactPhone model."""

    def test_contact_phone_mobile(self):
        """Test ContactPhone with mobile type."""
        phone = ContactPhone(
            value="+33612345678",
            type="mobile",
            formatted_type="Mobile",
        )

        assert phone.value == "+33612345678"
        assert phone.type == "mobile"


class TestContactAddress:
    """Tests for ContactAddress model."""

    def test_contact_address_complete(self):
        """Test ContactAddress with all fields."""
        address = ContactAddress(
            formatted_value="123 Main St, Paris 75001, France",
            type="home",
            street_address="123 Main St",
            city="Paris",
            region="Île-de-France",
            postal_code="75001",
            country="France",
        )

        assert address.city == "Paris"
        assert address.postal_code == "75001"

    def test_contact_address_minimal(self):
        """Test ContactAddress with minimal fields."""
        address = ContactAddress()

        assert address.formatted_value is None
        assert address.city is None


class TestContactDetailed:
    """Tests for ContactDetailed model (inherits from ContactBasic)."""

    def test_contact_detailed_inherits_from_basic(self):
        """Test that ContactDetailed inherits ContactBasic fields."""
        contact = ContactDetailed(
            resource_name="people/c777",
            name=ContactName(display="Test"),
            emails=[ContactEmail(value="test@example.com")],
        )

        # Has ContactBasic fields
        assert contact.resource_name == "people/c777"
        assert len(contact.emails) == 1

        # Has additional detailed fields (defaults)
        assert contact.organizations == []
        assert contact.biographies == []
        assert contact.metadata == {}

    def test_contact_detailed_with_extra_fields(self):
        """Test ContactDetailed with additional detailed fields."""
        contact = ContactDetailed(
            resource_name="people/c888",
            organizations=[{"name": "Company", "title": "Developer"}],
            biographies=[{"value": "Bio text"}],
            birthdays=[{"date": {"year": 1990, "month": 1, "day": 15}}],
            urls=[{"value": "https://example.com"}],
            relations=[{"person": "Jane", "type": "spouse"}],
            metadata={"source": "CONTACT", "updated": "2025-01-01"},
        )

        assert len(contact.organizations) == 1
        assert len(contact.birthdays) == 1
        assert contact.metadata["source"] == "CONTACT"
