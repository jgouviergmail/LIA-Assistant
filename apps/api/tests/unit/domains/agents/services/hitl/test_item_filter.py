"""
Unit tests for HITL Item Filter Service.

Tests the item filtering service used in for_each_confirmation HITL flow.

@created: 2026-02-02
@coverage: item_filter.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.hitl.item_filter import (
    ItemFilterService,
    get_item_filter_service,
)

# ============================================================================
# ItemFilterService Class Tests
# ============================================================================


class TestItemFilterServiceInit:
    """Tests for ItemFilterService initialization."""

    @patch("src.domains.agents.services.hitl.item_filter.get_llm")
    def test_init_creates_llm(self, mock_get_llm):
        """Test initialization creates LLM with correct config."""
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        service = ItemFilterService()

        mock_get_llm.assert_called_once_with(
            llm_type="hitl_classifier",
            config_override={"temperature": 0.0},
        )
        assert service.llm is mock_llm


# ============================================================================
# filter Method Tests
# ============================================================================


class TestFilterMethod:
    """Tests for ItemFilterService.filter method."""

    @pytest.fixture
    def mock_service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock()
            mock_get_llm.return_value = mock_llm
            service = ItemFilterService()
            yield service

    @pytest.mark.asyncio
    async def test_empty_items_returns_empty_list(self, mock_service):
        """Test empty item list returns empty list without LLM call."""
        result = await mock_service.filter(
            item_previews=[],
            exclude_criteria="test",
        )
        assert result == []
        mock_service.llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_criteria_returns_all_indices(self, mock_service):
        """Test empty criteria returns all item indices."""
        items = [
            {"subject": "Email 1"},
            {"subject": "Email 2"},
            {"subject": "Email 3"},
        ]
        result = await mock_service.filter(
            item_previews=items,
            exclude_criteria="",
        )
        assert result == [0, 1, 2]
        mock_service.llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_criteria_returns_all_indices(self, mock_service):
        """Test whitespace-only criteria returns all indices."""
        items = [{"name": "Test"}]
        result = await mock_service.filter(
            item_previews=items,
            exclude_criteria="   ",
        )
        assert result == [0]

    @pytest.mark.asyncio
    async def test_filters_matching_items(self, mock_service):
        """Test filtering excludes matching items."""
        # Configure mock to return indices to exclude
        mock_response = MagicMock()
        mock_response.content = "[1]"  # Exclude item at index 1
        mock_service.llm.ainvoke.return_value = mock_response

        items = [
            {"subject": "Newsletter Carrefour", "from": "news@carrefour.fr"},
            {"subject": "Meeting", "from": "guy.savoy@restaurant.com"},
            {"subject": "Invoice", "from": "billing@company.com"},
        ]

        result = await mock_service.filter(
            item_previews=items,
            exclude_criteria="Guy Savoy",
        )

        # Should return indices 0 and 2 (keeping items NOT matching)
        assert result == [0, 2]

    @pytest.mark.asyncio
    async def test_no_matches_returns_all_indices(self, mock_service):
        """Test no matches returns all indices."""
        mock_response = MagicMock()
        mock_response.content = "[]"  # No items to exclude
        mock_service.llm.ainvoke.return_value = mock_response

        items = [
            {"subject": "Email 1"},
            {"subject": "Email 2"},
        ]

        result = await mock_service.filter(
            item_previews=items,
            exclude_criteria="nonexistent",
        )

        assert result == [0, 1]

    @pytest.mark.asyncio
    async def test_all_matches_returns_empty_list(self, mock_service):
        """Test all items matching returns empty list."""
        mock_response = MagicMock()
        mock_response.content = "[0, 1, 2]"  # Exclude all
        mock_service.llm.ainvoke.return_value = mock_response

        items = [
            {"subject": "Newsletter 1"},
            {"subject": "Newsletter 2"},
            {"subject": "Newsletter 3"},
        ]

        result = await mock_service.filter(
            item_previews=items,
            exclude_criteria="newsletters",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_llm_error_propagates(self, mock_service):
        """Test LLM errors are propagated."""
        mock_service.llm.ainvoke.side_effect = Exception("LLM error")

        items = [{"subject": "Test"}]

        with pytest.raises(Exception) as exc_info:
            await mock_service.filter(
                item_previews=items,
                exclude_criteria="test",
            )

        assert "LLM error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_id_passed_to_config(self, mock_service):
        """Test run_id is passed in config."""
        mock_response = MagicMock()
        mock_response.content = "[]"
        mock_service.llm.ainvoke.return_value = mock_response

        with patch(
            "src.domains.agents.services.hitl.item_filter.create_instrumented_config"
        ) as mock_config:
            mock_config.return_value = {}

            await mock_service.filter(
                item_previews=[{"test": "data"}],
                exclude_criteria="test",
                run_id="test_run_123",
            )

            mock_config.assert_called_once()
            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["metadata"]["run_id"] == "test_run_123"


# ============================================================================
# _build_filter_prompt Method Tests
# ============================================================================


class TestBuildFilterPrompt:
    """Tests for ItemFilterService._build_filter_prompt method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm"):
            return ItemFilterService()

    def test_prompt_contains_criteria(self, service):
        """Test prompt contains exclusion criteria."""
        items = [{"subject": "Test"}]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="Guy Savoy",
            user_language="fr",
        )
        assert "Guy Savoy" in prompt

    def test_prompt_contains_items(self, service):
        """Test prompt contains item previews."""
        items = [
            {"subject": "Email 1", "from": "user1@example.com"},
            {"subject": "Email 2", "from": "user2@example.com"},
        ]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        assert "Email 1" in prompt
        assert "Email 2" in prompt
        assert "user1@example.com" in prompt

    def test_prompt_has_numbered_items(self, service):
        """Test prompt has numbered items (0-indexed)."""
        items = [
            {"name": "Item A"},
            {"name": "Item B"},
            {"name": "Item C"},
        ]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        assert "0. " in prompt
        assert "1. " in prompt
        assert "2. " in prompt

    def test_prompt_truncates_long_values(self, service):
        """Test long field values are truncated."""
        long_value = "x" * 100
        items = [{"subject": long_value}]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        # Should truncate to 47 chars + "..."
        assert "..." in prompt
        assert long_value not in prompt

    def test_prompt_handles_none_values(self, service):
        """Test None values are skipped."""
        items = [{"subject": "Test", "body": None}]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        assert "subject: Test" in prompt
        # body should not appear since it's None

    def test_prompt_handles_empty_preview(self, service):
        """Test empty preview dict shows (empty)."""
        items = [{}]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        assert "(empty)" in prompt

    def test_prompt_includes_instructions(self, service):
        """Test prompt includes filtering instructions."""
        items = [{"test": "data"}]
        prompt = service._build_filter_prompt(
            item_previews=items,
            exclude_criteria="test",
            user_language="en",
        )
        assert "EXCLUDE" in prompt or "exclude" in prompt
        assert "JSON" in prompt


# ============================================================================
# _parse_filter_response Method Tests
# ============================================================================


class TestParseFilterResponse:
    """Tests for ItemFilterService._parse_filter_response method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked LLM."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm"):
            return ItemFilterService()

    def test_parse_valid_json_array(self, service):
        """Test parsing valid JSON array."""
        result = service._parse_filter_response("[0, 2, 4]", max_index=5)
        assert result == [0, 2, 4]

    def test_parse_empty_array(self, service):
        """Test parsing empty array."""
        result = service._parse_filter_response("[]", max_index=5)
        assert result == []

    def test_parse_single_element(self, service):
        """Test parsing single element array."""
        result = service._parse_filter_response("[1]", max_index=5)
        assert result == [1]

    def test_parse_strips_whitespace(self, service):
        """Test parsing strips surrounding whitespace."""
        result = service._parse_filter_response("  [0, 1]  \n", max_index=5)
        assert result == [0, 1]

    def test_parse_removes_markdown_code_block(self, service):
        """Test parsing removes markdown code block."""
        result = service._parse_filter_response("```json\n[0, 1]\n```", max_index=5)
        assert result == [0, 1]

    def test_parse_removes_simple_code_block(self, service):
        """Test parsing removes simple code block."""
        result = service._parse_filter_response("```\n[2, 3]\n```", max_index=5)
        assert result == [2, 3]

    def test_parse_filters_out_of_range_indices(self, service):
        """Test out-of-range indices are filtered out."""
        result = service._parse_filter_response("[0, 5, 10]", max_index=5)
        assert result == [0]  # Only 0 is valid (0-4 range)

    def test_parse_filters_negative_indices(self, service):
        """Test negative indices are filtered out."""
        result = service._parse_filter_response("[-1, 0, 1]", max_index=5)
        assert result == [0, 1]

    def test_parse_handles_non_integer_values(self, service):
        """Test non-integer values are filtered out."""
        result = service._parse_filter_response('[0, "string", 2]', max_index=5)
        assert result == [0, 2]

    def test_parse_invalid_json_falls_back_to_regex(self, service):
        """Test invalid JSON falls back to regex extraction."""
        result = service._parse_filter_response(
            "The indices to exclude are 0 and 2",
            max_index=5,
        )
        assert 0 in result
        assert 2 in result

    def test_parse_non_list_returns_empty(self, service):
        """Test non-list JSON returns empty list."""
        result = service._parse_filter_response('{"not": "a list"}', max_index=5)
        assert result == []

    def test_parse_handles_float_indices(self, service):
        """Test float indices are handled (should be filtered)."""
        result = service._parse_filter_response("[0, 1.5, 2]", max_index=5)
        assert 0 in result
        assert 2 in result
        # 1.5 is not an int, so filtered


# ============================================================================
# get_item_filter_service Singleton Tests
# ============================================================================


class TestGetItemFilterService:
    """Tests for get_item_filter_service singleton function."""

    def test_returns_instance(self):
        """Test function returns ItemFilterService instance."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm"):
            # Reset singleton
            import src.domains.agents.services.hitl.item_filter as module

            module._item_filter_service = None

            service = get_item_filter_service()
            assert isinstance(service, ItemFilterService)

    def test_returns_same_instance(self):
        """Test function returns same instance (singleton)."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm"):
            # Reset singleton
            import src.domains.agents.services.hitl.item_filter as module

            module._item_filter_service = None

            service1 = get_item_filter_service()
            service2 = get_item_filter_service()
            assert service1 is service2


# ============================================================================
# Integration Tests
# ============================================================================


class TestItemFilterIntegration:
    """Integration tests for item filter service."""

    @pytest.mark.asyncio
    async def test_full_filter_workflow(self):
        """Test complete filter workflow."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "[0, 2]"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_llm.return_value = mock_llm

            service = ItemFilterService()

            items = [
                {"subject": "Newsletter", "from": "news@company.com"},
                {"subject": "Important", "from": "boss@company.com"},
                {"subject": "Spam", "from": "spam@spam.com"},
                {"subject": "Personal", "from": "friend@example.com"},
            ]

            result = await service.filter(
                item_previews=items,
                exclude_criteria="newsletters and spam",
                user_language="en",
                run_id="test_run",
            )

            # Indices 0 and 2 excluded, so keep 1 and 3
            assert result == [1, 3]

    @pytest.mark.asyncio
    async def test_email_domain_exclusion(self):
        """Test excluding emails by domain."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "[1]"  # Exclude carrefour
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_llm.return_value = mock_llm

            service = ItemFilterService()

            items = [
                {"subject": "Order Confirmation", "from": "orders@amazon.com"},
                {"subject": "Weekly Deals", "from": "promo@carrefour.fr"},
            ]

            result = await service.filter(
                item_previews=items,
                exclude_criteria="carrefour",
            )

            assert result == [0]  # Keep amazon, exclude carrefour

    @pytest.mark.asyncio
    async def test_contact_name_exclusion(self):
        """Test excluding contacts by name."""
        with patch("src.domains.agents.services.hitl.item_filter.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "[0, 1]"  # Exclude both Johns
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_llm.return_value = mock_llm

            service = ItemFilterService()

            items = [
                {"name": "John Smith", "email": "john.smith@example.com"},
                {"name": "John Doe", "email": "john.doe@example.com"},
                {"name": "Jane Smith", "email": "jane.smith@example.com"},
            ]

            result = await service.filter(
                item_previews=items,
                exclude_criteria="John",
            )

            assert result == [2]  # Keep only Jane
