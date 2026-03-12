"""
Tests for Pydantic normalization of tools (Phase 2).

This module tests:
- ToolResponse, ToolErrorModel (common.py)
- Contact Input/Output models (contacts_models.py)
- Validators and parsers (contacts_validators.py)

Coverage target: 95% on new Pydantic code
"""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.domains.agents.tools.common import (
    ToolErrorCode,
    ToolErrorModel,
    ToolInputValidationError,
    ToolResponse,
    create_error_response,
    create_success_response,
    validate_tool_input,
)
from src.domains.agents.tools.contacts_models import (
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
from src.domains.agents.tools.contacts_validators import (
    parse_get_contact_details_response,
    parse_list_contacts_response,
    parse_search_contacts_response,
    validate_and_normalize_search_response,
    validate_get_contact_details_input,
    validate_list_contacts_input,
    validate_search_contacts_input,
)

# ============================================================================
# Tests ToolResponse & ToolError
# ============================================================================


class TestToolResponse:
    """Tests for ToolResponse model"""

    def test_success_response(self):
        """Test creating a success response"""
        response = ToolResponse(
            success=True,
            data={"result": "ok"},
            metadata={"count": 5},
        )
        assert response.success is True
        assert response.data == {"result": "ok"}
        assert response.error is None
        assert response.metadata["count"] == 5
        assert isinstance(response.timestamp, datetime)

    def test_error_response(self):
        """Test creating an error response"""
        response = ToolResponse(
            success=False,
            error="Something went wrong",
            error_code=ToolErrorCode.INTERNAL_ERROR,
            metadata={"context": "test"},
        )
        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.error_code == ToolErrorCode.INTERNAL_ERROR
        assert response.data is None

    def test_model_dump_serialization(self):
        """Test model_dump() serialization"""
        response = ToolResponse(
            success=True,
            data={"contacts": []},
            error_code=ToolErrorCode.EMPTY_RESULT,
        )
        dumped = response.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["success"] is True
        assert isinstance(dumped["timestamp"], str)  # Converted to ISO string
        assert dumped["error_code"] == "EMPTY_RESULT"  # Enum converted to string


class TestToolErrorModel:
    """Tests for ToolErrorModel model"""

    def test_tool_error_creation(self):
        """Test ToolErrorModel creation"""
        error = ToolErrorModel(
            code=ToolErrorCode.INVALID_INPUT,
            message="Invalid parameter",
            context={"param": "query"},
            recoverable=False,
        )
        assert error.code == ToolErrorCode.INVALID_INPUT
        assert error.message == "Invalid parameter"
        assert error.context["param"] == "query"
        assert error.recoverable is False

    def test_from_exception(self):
        """Test ToolErrorModel.from_exception()"""
        exc = ValueError("Test error")
        error = ToolErrorModel.from_exception(
            exc,
            code=ToolErrorCode.INVALID_INPUT,
            context={"field": "test"},
            recoverable=True,
        )
        assert error.message == "Test error"
        assert error.code == ToolErrorCode.INVALID_INPUT
        assert error.context["exception_type"] == "ValueError"
        assert error.recoverable is True

    def test_to_response(self):
        """Test ToolErrorModel -> ToolResponse conversion"""
        error = ToolErrorModel(
            code=ToolErrorCode.NOT_FOUND,
            message="Contact not found",
            context={"resource_name": "people/c123"},
        )
        response = error.to_response()

        assert response["success"] is False
        assert response["error"] == "Contact not found"
        assert response["error_code"] == "NOT_FOUND"
        assert response["metadata"]["context"]["resource_name"] == "people/c123"


class TestHelperFunctions:
    """Tests for helper functions"""

    def test_create_success_response(self):
        """Test create_success_response()"""
        result = create_success_response(
            data={"result": "ok"},
            metadata={"source": "cache"},
        )
        assert result["success"] is True
        assert result["data"] == {"result": "ok"}
        assert result["metadata"]["source"] == "cache"

    def test_create_error_response(self):
        """Test create_error_response()"""
        result = create_error_response(
            message="Rate limit exceeded",
            code=ToolErrorCode.RATE_LIMIT_EXCEEDED,
            context={"retry_after": 60},
            recoverable=True,
        )
        assert result["success"] is False
        assert result["error"] == "Rate limit exceeded"
        assert result["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert result["metadata"]["recoverable"] is True

    def test_validate_tool_input_success(self):
        """Test validate_tool_input() success"""
        validated = validate_tool_input(
            SearchContactsInput,
            {"query": "John", "max_results": 20},
        )
        assert validated.query == "John"
        assert validated.max_results == 20

    def test_validate_tool_input_failure(self):
        """Test validate_tool_input() failure"""
        with pytest.raises(ToolInputValidationError) as exc_info:
            validate_tool_input(
                SearchContactsInput,
                {"query": ""},  # Empty query invalid
            )
        assert exc_info.value.tool_error.code == ToolErrorCode.INVALID_INPUT


# ============================================================================
# Tests Contacts Models
# ============================================================================


class TestContactsModels:
    """Tests for contact models"""

    def test_contact_name(self):
        """Test ContactName model"""
        name = ContactName(
            display="John Doe",
            given_name="John",
            family_name="Doe",
        )
        assert name.display == "John Doe"
        assert name.given_name == "John"
        assert name.family_name == "Doe"

    def test_contact_email(self):
        """Test ContactEmail model"""
        email = ContactEmail(value="john@example.com", type="work")
        assert email.value == "john@example.com"
        assert email.type == "work"

    def test_contact_phone(self):
        """Test ContactPhone model"""
        phone = ContactPhone(value="+33 6 12 34 56 78", type="mobile")
        assert phone.value == "+33 6 12 34 56 78"
        assert phone.type == "mobile"

    def test_contact_basic(self):
        """Test ContactBasic model"""
        contact = ContactBasic(
            resource_name="people/c123456789",
            name=ContactName(display="John Doe"),
            emails=[ContactEmail(value="john@example.com")],
            phones=[ContactPhone(value="+33 6 12")],
        )
        assert contact.resource_name == "people/c123456789"
        assert contact.name.display == "John Doe"
        assert len(contact.emails) == 1
        assert len(contact.phones) == 1

    def test_contact_basic_invalid_resource_name(self):
        """Test ContactBasic with invalid resource_name"""
        with pytest.raises(ValidationError):
            ContactBasic(
                resource_name="invalid_format",  # Must start with "people/"
                name=ContactName(display="John"),
            )

    def test_contact_detailed(self):
        """Test ContactDetailed model"""
        contact = ContactDetailed(
            resource_name="people/c123",
            name=ContactName(display="John Doe"),
            emails=[],
            phones=[],
            addresses=[],
            organizations=[{"name": "Company"}],
        )
        assert contact.resource_name == "people/c123"
        assert len(contact.organizations) == 1


class TestSearchContactsModels:
    """Tests for SearchContacts Input/Output"""

    def test_search_input_valid(self):
        """Test valid SearchContactsInput"""
        input_data = SearchContactsInput(
            query="John",
            max_results=20,
            fields=["names", "emails"],
            force_refresh=True,
        )
        assert input_data.query == "John"
        assert input_data.max_results == 20
        assert len(input_data.fields) == 2
        assert input_data.force_refresh is True

    def test_search_input_defaults(self):
        """Test SearchContactsInput default values"""
        input_data = SearchContactsInput(query="Test")
        assert input_data.query == "Test"
        assert input_data.max_results == 10  # Default
        assert input_data.fields is None
        assert input_data.force_refresh is False

    def test_search_input_empty_query_raises(self):
        """Test SearchContactsInput with empty query"""
        with pytest.raises(ValidationError):
            SearchContactsInput(query="")  # Empty query invalid

    def test_search_input_max_results_constraints(self):
        """Test max_results constraints (1-50)"""
        # Too small
        with pytest.raises(ValidationError):
            SearchContactsInput(query="Test", max_results=0)

        # Too large
        with pytest.raises(ValidationError):
            SearchContactsInput(query="Test", max_results=51)

        # OK
        input_data = SearchContactsInput(query="Test", max_results=50)
        assert input_data.max_results == 50

    def test_search_output_valid(self):
        """Test valid SearchContactsOutput"""
        contact = ContactBasic(
            resource_name="people/c123",
            name=ContactName(display="John"),
        )
        output = SearchContactsOutput(
            contacts=[contact],
            total_found=1,
            from_cache=True,
        )
        assert len(output.contacts) == 1
        assert output.total_found == 1
        assert output.from_cache is True


class TestListContactsModels:
    """Tests for ListContacts Input/Output"""

    def test_list_input_valid(self):
        """Test valid ListContactsInput"""
        input_data = ListContactsInput(
            limit=50,
            fields=["names"],
            force_refresh=False,
        )
        assert input_data.limit == 50
        assert len(input_data.fields) == 1

    def test_list_input_limit_constraints(self):
        """Test limit constraints (1-100)"""
        with pytest.raises(ValidationError):
            ListContactsInput(limit=0)

        with pytest.raises(ValidationError):
            ListContactsInput(limit=101)

        # OK
        input_data = ListContactsInput(limit=100)
        assert input_data.limit == 100

    def test_list_output_valid(self):
        """Test valid ListContactsOutput"""
        output = ListContactsOutput(
            contacts=[],
            total_returned=0,
            has_more=False,
            from_cache=False,
        )
        assert output.total_returned == 0
        assert output.has_more is False


class TestGetContactDetailsModels:
    """Tests for GetContactDetails Input/Output"""

    def test_get_details_input_valid(self):
        """Test valid GetContactDetailsInput"""
        input_data = GetContactDetailsInput(
            resource_name="people/c123456789",
            force_refresh=True,
        )
        assert input_data.resource_name == "people/c123456789"
        assert input_data.force_refresh is True

    def test_get_details_input_invalid_format(self):
        """Test GetContactDetailsInput with invalid format"""
        with pytest.raises(ValidationError):
            GetContactDetailsInput(resource_name="invalid")

        with pytest.raises(ValidationError):
            GetContactDetailsInput(resource_name="people/invalid")

        # OK
        input_data = GetContactDetailsInput(resource_name="people/c999")
        assert input_data.resource_name == "people/c999"

    def test_get_details_output_valid(self):
        """Test valid GetContactDetailsOutput"""
        contact = ContactDetailed(
            resource_name="people/c123",
            name=ContactName(display="John Doe"),
        )
        output = GetContactDetailsOutput(
            contact=contact,
            from_cache=True,
        )
        assert output.contact.resource_name == "people/c123"
        assert output.from_cache is True


# ============================================================================
# Tests Validators
# ============================================================================


class TestInputValidators:
    """Tests for input validation functions"""

    def test_validate_search_contacts_input(self):
        """Test validate_search_contacts_input()"""
        validated = validate_search_contacts_input(
            query="John",
            max_results=30,
            fields=["names", "emails"],
            force_refresh=True,
        )
        assert validated.query == "John"
        assert validated.max_results == 30

    def test_validate_list_contacts_input(self):
        """Test validate_list_contacts_input()"""
        validated = validate_list_contacts_input(
            limit=25,
            fields=["names"],
            force_refresh=False,
        )
        assert validated.limit == 25

    def test_validate_get_contact_details_input(self):
        """Test validate_get_contact_details_input()"""
        validated = validate_get_contact_details_input(
            resource_name="people/c123456789",
            force_refresh=True,
        )
        assert validated.resource_name == "people/c123456789"

    def test_validate_get_contact_details_input_invalid_format(self):
        """Test that validation fails with invalid format"""
        with pytest.raises(ToolInputValidationError):
            validate_get_contact_details_input(resource_name="invalid_format")


class TestOutputParsers:
    """Tests for response parsers"""

    def test_parse_search_contacts_response_success(self):
        """Test parse_search_contacts_response() success"""
        json_response = {
            "contacts": [
                {
                    "resource_name": "people/c123",
                    "name": {"display": "John Doe"},
                    "emails": [{"value": "john@example.com", "type": "work"}],
                    "phones": [],
                }
            ],
            "from_cache": True,
        }
        output = parse_search_contacts_response(json_response)

        assert len(output.contacts) == 1
        assert output.contacts[0].resource_name == "people/c123"
        assert output.contacts[0].name.display == "John Doe"
        assert len(output.contacts[0].emails) == 1
        assert output.total_found == 1
        assert output.from_cache is True

    def test_parse_search_contacts_response_from_json_string(self):
        """Test parsing from JSON string"""
        json_str = json.dumps(
            {
                "contacts": [{"resource_name": "people/c456", "name": {"display": "Jane"}}],
                "from_cache": False,
            }
        )
        output = parse_search_contacts_response(json_str)

        assert len(output.contacts) == 1
        assert output.contacts[0].name.display == "Jane"

    def test_parse_list_contacts_response_success(self):
        """Test parse_list_contacts_response() success"""
        json_response = {
            "contacts": [
                {"resource_name": "people/c1", "name": {"display": "Contact 1"}},
                {"resource_name": "people/c2", "name": {"display": "Contact 2"}},
            ],
            "has_more": True,
            "from_cache": False,
        }
        output = parse_list_contacts_response(json_response)

        assert len(output.contacts) == 2
        assert output.total_returned == 2
        assert output.has_more is True

    def test_parse_get_contact_details_response_success(self):
        """Test parse_get_contact_details_response() success"""
        json_response = {
            "contact": {
                "resource_name": "people/c789",
                "name": {"display": "Detailed Contact", "given_name": "Detailed"},
                "emails": [{"value": "detailed@example.com"}],
                "phones": [{"value": "+33 6 12 34 56 78"}],
                "addresses": [],
                "organizations": [{"name": "Company"}],
            },
            "from_cache": True,
        }
        output = parse_get_contact_details_response(json_response)

        assert output.contact.resource_name == "people/c789"
        assert output.contact.name.given_name == "Detailed"
        assert len(output.contact.organizations) == 1
        assert output.from_cache is True

    def test_parse_response_invalid_json(self):
        """Test that parsing fails with invalid JSON"""
        with pytest.raises(ValueError):
            parse_search_contacts_response("not valid json")

    def test_parse_response_missing_required_field(self):
        """Test that parsing fails with missing required field"""
        json_response = {"contacts": [{"name": {"display": "John"}}]}  # Missing resource_name

        with pytest.raises(ValueError):
            parse_search_contacts_response(json_response)


class TestHighLevelWrappers:
    """Tests for high-level wrappers"""

    def test_validate_and_normalize_search_response_success(self):
        """Test validate_and_normalize_search_response() success"""
        json_response = {
            "contacts": [{"resource_name": "people/c123", "name": {"display": "John"}}],
            "from_cache": True,
        }
        result = validate_and_normalize_search_response(json_response)

        assert result["success"] is True
        assert "data" in result
        assert result["data"]["total_found"] == 1
        assert result["metadata"]["from_cache"] is True

    def test_validate_and_normalize_search_response_empty(self):
        """Test validate_and_normalize_search_response() with empty structure"""
        # Parser is lenient - structure without "contacts" = empty list (valid)
        empty_response = {"invalid": "structure"}
        result = validate_and_normalize_search_response(empty_response)

        assert result["success"] is True
        assert result["data"]["total_found"] == 0
        assert result["data"]["contacts"] == []
        assert "metadata" in result
