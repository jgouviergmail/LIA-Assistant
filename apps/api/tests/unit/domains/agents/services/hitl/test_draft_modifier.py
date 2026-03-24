"""
Unit tests for draft modification service.

Tests for the DraftModificationService that handles EDIT actions
in draft_critique HITL flow.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.hitl.draft_modifier import (
    CONTENT_FIELDS,
    PRESERVED_FIELDS,
    DraftModificationService,
    get_draft_modification_service,
)


class TestPreservedFieldsConstants:
    """Tests for PRESERVED_FIELDS constant."""

    def test_email_preserved_fields(self):
        """Test that email has no preserved fields (to, cc, bcc all modifiable)."""
        assert PRESERVED_FIELDS["email"] == []

    def test_email_reply_preserved_fields(self):
        """Test that email_reply preserves thread context."""
        assert "message_id" in PRESERVED_FIELDS["email_reply"]
        assert "thread_id" in PRESERVED_FIELDS["email_reply"]

    def test_email_forward_preserved_fields(self):
        """Test that email_forward preserves source message reference."""
        assert "message_id" in PRESERVED_FIELDS["email_forward"]

    def test_event_preserved_fields(self):
        """Test that event preserves calendar_id."""
        assert "calendar_id" in PRESERVED_FIELDS["event"]

    def test_contact_has_no_preserved_fields(self):
        """Test that contact can modify all fields."""
        assert PRESERVED_FIELDS["contact"] == []

    def test_all_draft_types_have_entries(self):
        """Test that all expected draft types are defined."""
        expected_types = [
            "email",
            "email_reply",
            "email_forward",
            "event",
            "event_update",
            "contact",
            "contact_update",
            "task",
            "task_update",
        ]
        for draft_type in expected_types:
            assert draft_type in PRESERVED_FIELDS


class TestContentFieldsConstants:
    """Tests for CONTENT_FIELDS constant."""

    def test_email_content_fields(self):
        """Test that email has expected content fields including cc and bcc."""
        assert "to" in CONTENT_FIELDS["email"]
        assert "cc" in CONTENT_FIELDS["email"]
        assert "bcc" in CONTENT_FIELDS["email"]
        assert "subject" in CONTENT_FIELDS["email"]
        assert "body" in CONTENT_FIELDS["email"]

    def test_email_reply_content_fields(self):
        """Test that email_reply only has fields supported by reply protocol."""
        assert "to" in CONTENT_FIELDS["email_reply"]
        assert "body" in CONTENT_FIELDS["email_reply"]
        # Not supported by connector protocol (reply_email signature)
        assert "cc" not in CONTENT_FIELDS["email_reply"]
        assert "bcc" not in CONTENT_FIELDS["email_reply"]
        assert "subject" not in CONTENT_FIELDS["email_reply"]

    def test_email_forward_content_fields(self):
        """Test that email_forward only has fields supported by forward protocol."""
        assert "to" in CONTENT_FIELDS["email_forward"]
        assert "cc" in CONTENT_FIELDS["email_forward"]
        assert "body" in CONTENT_FIELDS["email_forward"]
        # Not supported by connector protocol (forward_email signature)
        assert "bcc" not in CONTENT_FIELDS["email_forward"]
        assert "subject" not in CONTENT_FIELDS["email_forward"]

    def test_contact_update_content_fields_include_address(self):
        """Test that contact_update includes address field."""
        assert "address" in CONTENT_FIELDS["contact_update"]

    def test_task_preserved_fields_use_correct_field_name(self):
        """Test that task preserved fields use task_list_id (not tasklist_id)."""
        assert "task_list_id" in PRESERVED_FIELDS["task"]
        assert "task_list_id" in PRESERVED_FIELDS["task_update"]

    def test_event_preserved_fields_include_timezone(self):
        """Test that event types preserve timezone."""
        assert "timezone" in PRESERVED_FIELDS["event"]
        assert "timezone" in PRESERVED_FIELDS["event_update"]

    def test_event_content_fields(self):
        """Test that event has expected content fields."""
        assert "summary" in CONTENT_FIELDS["event"]
        assert "description" in CONTENT_FIELDS["event"]
        assert "location" in CONTENT_FIELDS["event"]
        assert "start_datetime" in CONTENT_FIELDS["event"]
        assert "end_datetime" in CONTENT_FIELDS["event"]
        assert "attendees" in CONTENT_FIELDS["event"]

    def test_contact_content_fields(self):
        """Test that contact has expected content fields."""
        assert "name" in CONTENT_FIELDS["contact"]
        assert "email" in CONTENT_FIELDS["contact"]
        assert "phone" in CONTENT_FIELDS["contact"]
        assert "organization" in CONTENT_FIELDS["contact"]
        assert "notes" in CONTENT_FIELDS["contact"]

    def test_task_content_fields(self):
        """Test that task has expected content fields."""
        assert "title" in CONTENT_FIELDS["task"]
        assert "notes" in CONTENT_FIELDS["task"]
        assert "due" in CONTENT_FIELDS["task"]

    def test_task_update_has_status_field(self):
        """Test that task_update includes status field."""
        assert "status" in CONTENT_FIELDS["task_update"]


class TestDraftModificationServiceInit:
    """Tests for DraftModificationService initialization."""

    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    def test_init_creates_llm_with_correct_config(self, mock_get_llm):
        """Test that init creates LLM with hitl_question_generator type."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        service = DraftModificationService()

        mock_get_llm.assert_called_once_with(
            llm_type="hitl_question_generator",
            config_override={"temperature": 0.7},
        )
        assert service.llm == mock_llm


class TestBuildContextInfo:
    """Tests for _build_context_info method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.draft_modifier.get_llm"):
            return DraftModificationService()

    def test_email_context_info(self, service):
        """Test context info for email draft type."""
        draft = {"to": "test@example.com", "cc": "cc@example.com", "subject": "Test"}
        result = service._build_context_info(draft, "email")

        assert "Destinataire: test@example.com" in result
        assert "CC: cc@example.com" in result
        assert "Sujet actuel: Test" in result

    def test_email_context_info_minimal(self, service):
        """Test context info with minimal email fields."""
        draft = {"to": "test@example.com"}
        result = service._build_context_info(draft, "email")

        assert "Destinataire: test@example.com" in result
        assert "CC:" not in result

    def test_email_reply_context_no_subject(self, service):
        """Test that email_reply doesn't include subject."""
        draft = {"to": "test@example.com", "subject": "Re: Test"}
        result = service._build_context_info(draft, "email_reply")

        assert "Destinataire: test@example.com" in result
        assert "Sujet" not in result

    def test_event_context_info(self, service):
        """Test context info for event draft type."""
        draft = {"summary": "Meeting", "start_datetime": "2025-01-15T10:00"}
        result = service._build_context_info(draft, "event")

        assert "Meeting" in result
        assert "2025-01-15T10:00" in result

    def test_event_update_context_info(self, service):
        """Test context info for event_update draft type."""
        draft = {"summary": "Updated Meeting", "start_datetime": "2025-01-20T14:00"}
        result = service._build_context_info(draft, "event_update")

        assert "Updated Meeting" in result

    def test_contact_context_info(self, service):
        """Test context info for contact draft type."""
        draft = {"name": "John Doe"}
        result = service._build_context_info(draft, "contact")

        assert "Contact: John Doe" in result

    def test_contact_update_context_info(self, service):
        """Test context info for contact_update draft type."""
        draft = {"name": "Jane Smith"}
        result = service._build_context_info(draft, "contact_update")

        assert "Contact: Jane Smith" in result

    def test_task_context_info(self, service):
        """Test context info for task draft type."""
        draft = {"title": "Complete report"}
        result = service._build_context_info(draft, "task")

        assert "Tâche: Complete report" in result

    def test_task_update_context_info(self, service):
        """Test context info for task_update draft type."""
        draft = {"title": "Review document"}
        result = service._build_context_info(draft, "task_update")

        assert "Tâche: Review document" in result

    def test_unknown_draft_type_returns_generic(self, service):
        """Test that unknown draft types return generic message."""
        draft = {"field": "value"}
        result = service._build_context_info(draft, "unknown_type")

        assert result == "Brouillon générique"


class TestBuildContactContextInfo:
    """Tests for _build_contact_context_info method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.draft_modifier.get_llm"):
            return DraftModificationService()

    def test_no_context_returns_empty(self, service):
        """Test that None context returns empty string."""
        result = service._build_contact_context_info(None)
        assert result == ""

    def test_empty_context_returns_empty(self, service):
        """Test that empty list returns empty string."""
        result = service._build_contact_context_info([])
        assert result == ""

    def test_contact_with_emails(self, service):
        """Test context with contact having emails."""
        contacts = [{"name": "Jean Dupond", "emails": ["jean@example.com", "jean@carven.com"]}]
        result = service._build_contact_context_info(contacts)

        assert "Adresses email disponibles" in result
        assert "Jean Dupond" in result
        assert "jean@example.com" in result
        assert "jean@carven.com" in result

    def test_multiple_contacts(self, service):
        """Test context with multiple contacts."""
        contacts = [
            {"name": "Alice", "emails": ["alice@example.com"]},
            {"name": "Bob", "emails": ["bob@work.com", "bob@home.com"]},
        ]
        result = service._build_contact_context_info(contacts)

        assert "Alice" in result
        assert "alice@example.com" in result
        assert "Bob" in result
        assert "bob@work.com" in result
        assert "bob@home.com" in result

    def test_contact_without_emails(self, service):
        """Test that contact without emails is skipped."""
        contacts = [{"name": "NoEmail", "emails": []}]
        result = service._build_contact_context_info(contacts)

        assert result == ""  # Header only, so returns empty

    def test_contact_missing_name_uses_default(self, service):
        """Test that missing name uses default."""
        contacts = [{"emails": ["unknown@example.com"]}]
        result = service._build_contact_context_info(contacts)

        # Should have some name (the default from constants)
        assert "unknown@example.com" in result


class TestFormatExpectedFields:
    """Tests for _format_expected_fields method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.draft_modifier.get_llm"):
            return DraftModificationService()

    def test_formats_single_field(self, service):
        """Test formatting a single field."""
        result = service._format_expected_fields(["body"])
        assert '"body": "contenu modifié"' in result

    def test_formats_multiple_fields(self, service):
        """Test formatting multiple fields."""
        result = service._format_expected_fields(["subject", "body"])

        assert '"subject": "contenu modifié"' in result
        assert '"body": "contenu modifié"' in result
        assert ",\n" in result  # Fields separated by comma and newline

    def test_formats_empty_fields(self, service):
        """Test formatting empty field list."""
        result = service._format_expected_fields([])
        assert result == ""


class TestParseModificationResponse:
    """Tests for _parse_modification_response method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.draft_modifier.get_llm"):
            return DraftModificationService()

    def test_parses_valid_json(self, service):
        """Test parsing valid JSON response."""
        response = '{"subject": "New Subject", "body": "New Body"}'
        content_fields = ["subject", "body"]
        original = {"to": "test@example.com"}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["subject"] == "New Subject"
        assert result["body"] == "New Body"

    def test_parses_json_in_markdown_block(self, service):
        """Test parsing JSON in markdown code block."""
        response = '```json\n{"body": "Modified content"}\n```'
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["body"] == "Modified content"

    def test_parses_json_in_plain_markdown_block(self, service):
        """Test parsing JSON in plain markdown code block."""
        response = '```\n{"body": "Plain block content"}\n```'
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["body"] == "Plain block content"

    def test_filters_unexpected_fields(self, service):
        """Test that unexpected fields are filtered out."""
        response = '{"body": "Content", "unexpected": "Should be ignored"}'
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert "body" in result
        assert "unexpected" not in result

    def test_skips_empty_fields(self, service):
        """Test that empty or null fields are skipped."""
        response = '{"subject": "", "body": "Content"}'
        content_fields = ["subject", "body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert "subject" not in result
        assert result["body"] == "Content"

    def test_allows_clearing_cc_field(self, service):
        """Test that cc can be explicitly cleared (set to empty string)."""
        response = '{"cc": "", "body": "Content"}'
        content_fields = ["cc", "body"]
        original = {"cc": "old@example.com"}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["cc"] == ""
        assert result["body"] == "Content"

    def test_allows_clearing_bcc_field(self, service):
        """Test that bcc can be explicitly cleared (set to empty string)."""
        response = '{"bcc": "", "body": "Content"}'
        content_fields = ["bcc", "body"]
        original = {"bcc": "old@example.com"}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["bcc"] == ""

    def test_adds_cc_field(self, service):
        """Test that cc can be added via modification."""
        response = '{"cc": "new@example.com", "body": "Content"}'
        content_fields = ["cc", "body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["cc"] == "new@example.com"
        assert result["body"] == "Content"

    def test_returns_empty_when_no_fields_extracted(self, service):
        """Test that empty dict is returned when no expected fields found."""
        response = '{"other": "value"}'
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result == {}

    def test_handles_invalid_json_with_body_fallback(self, service):
        """Test fallback to body field on invalid JSON."""
        response = "This is just plain text content that is long enough."
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result["body"] == response

    def test_handles_invalid_json_no_body_field(self, service):
        """Test empty return on invalid JSON without body field."""
        response = "Just some text"
        content_fields = ["subject"]  # Not "body"
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result == {}

    def test_handles_short_invalid_response(self, service):
        """Test that very short invalid response returns empty."""
        response = "Hi"  # Less than 10 chars
        content_fields = ["body"]
        original = {}

        result = service._parse_modification_response(response, content_fields, original)

        assert result == {}


class TestModifyMethod:
    """Tests for the main modify method."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.domains.agents.services.hitl.draft_modifier.create_instrumented_config")
    @patch("src.domains.agents.services.hitl.draft_modifier.enrich_config_with_node_metadata")
    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    async def test_modify_returns_merged_draft(
        self, mock_get_llm, mock_enrich, mock_create_config, mock_load_prompt
    ):
        """Test that modify returns merged draft with modifications."""
        # Setup
        mock_load_prompt.return_value = "System prompt {user_language} {draft_type} {context_info} {contact_info} {current_content} {instructions} {expected_fields}"
        mock_create_config.return_value = {}
        mock_enrich.return_value = {}

        mock_response = MagicMock()
        mock_response.content = '{"body": "Modified body text"}'
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        service = DraftModificationService()
        original_draft = {"to": "test@example.com", "subject": "Test", "body": "Original"}

        # Execute
        result = await service.modify(
            original_draft=original_draft,
            instructions="make it shorter",
            draft_type="email",
            user_language="fr",
            run_id="test_run",
        )

        # Verify
        assert result["to"] == "test@example.com"  # Preserved
        assert result["subject"] == "Test"  # Preserved
        assert result["body"] == "Modified body text"  # Modified

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.domains.agents.services.hitl.draft_modifier.create_instrumented_config")
    @patch("src.domains.agents.services.hitl.draft_modifier.enrich_config_with_node_metadata")
    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    async def test_modify_handles_llm_error(
        self, mock_get_llm, mock_enrich, mock_create_config, mock_load_prompt
    ):
        """Test that LLM errors are propagated."""
        mock_load_prompt.return_value = "prompt"
        mock_create_config.return_value = {}
        mock_enrich.return_value = {}

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM Error"))
        mock_get_llm.return_value = mock_llm

        service = DraftModificationService()

        with pytest.raises(Exception, match="LLM Error"):
            await service.modify(
                original_draft={"body": "test"},
                instructions="modify",
                draft_type="email",
            )

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.domains.agents.services.hitl.draft_modifier.create_instrumented_config")
    @patch("src.domains.agents.services.hitl.draft_modifier.enrich_config_with_node_metadata")
    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    async def test_modify_with_contact_context(
        self, mock_get_llm, mock_enrich, mock_create_config, mock_load_prompt
    ):
        """Test that contact_context is passed to prompt builder."""
        mock_load_prompt.return_value = "prompt {contact_info}"
        mock_create_config.return_value = {}
        mock_enrich.return_value = {}

        mock_response = MagicMock()
        mock_response.content = '{"to": "jean@carven.com", "body": "Modified"}'
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        service = DraftModificationService()
        contact_context = [{"name": "Jean", "emails": ["jean@example.com", "jean@carven.com"]}]

        result = await service.modify(
            original_draft={"to": "jean@example.com", "body": "Original"},
            instructions="utilise son adresse @carven",
            draft_type="email",
            contact_context=contact_context,
        )

        # The LLM should have received the contact context and changed the email
        assert result["to"] == "jean@carven.com"

    @pytest.mark.asyncio
    @patch("src.domains.agents.prompts.load_prompt")
    @patch("src.domains.agents.services.hitl.draft_modifier.create_instrumented_config")
    @patch("src.domains.agents.services.hitl.draft_modifier.enrich_config_with_node_metadata")
    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    async def test_modify_unknown_draft_type(
        self, mock_get_llm, mock_enrich, mock_create_config, mock_load_prompt
    ):
        """Test modify with unknown draft type uses empty content fields."""
        mock_load_prompt.return_value = "prompt"
        mock_create_config.return_value = {}
        mock_enrich.return_value = {}

        mock_response = MagicMock()
        mock_response.content = "{}"
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        service = DraftModificationService()

        result = await service.modify(
            original_draft={"field": "value"},
            instructions="modify",
            draft_type="unknown_type",
        )

        # Should return original since no content fields for unknown type
        assert result["field"] == "value"


class TestGetDraftModificationService:
    """Tests for singleton accessor function."""

    def setup_method(self):
        """Reset singleton before each test."""
        import src.domains.agents.services.hitl.draft_modifier as module

        module._service_instance = None

    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    def test_creates_singleton_instance(self, mock_get_llm):
        """Test that singleton is created on first call."""
        mock_get_llm.return_value = MagicMock()

        service1 = get_draft_modification_service()
        service2 = get_draft_modification_service()

        assert service1 is service2

    @patch("src.domains.agents.services.hitl.draft_modifier.get_llm")
    def test_returns_existing_instance(self, mock_get_llm):
        """Test that existing instance is returned."""
        mock_get_llm.return_value = MagicMock()

        # First call creates instance
        service1 = get_draft_modification_service()

        # Second call should not create new LLM
        mock_get_llm.reset_mock()
        service2 = get_draft_modification_service()

        mock_get_llm.assert_not_called()
        assert service1 is service2
