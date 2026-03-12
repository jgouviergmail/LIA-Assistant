"""
Unit tests for Hallucinated Tools Registry.

Tests the hallucination detection and registry management.

@created: 2026-02-02
@enhanced: 2026-02-05 - Added parametrized tests, logging tests, edge cases
@coverage: hallucinated_tools.py
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.domains.agents.registry.hallucinated_tools import (
    DEFAULT_EXACT_TOOLS,
    DEFAULT_PATTERNS,
    HALLUCINATIONS_FILE,
    _load_registry,
    _save_registry,
    _save_registry_unlocked,
    add_exact_tool,
    add_pattern,
    get_registry,
    is_hallucinated_tool,
    record_hallucination,
)

# ============================================================================
# Default Constants Tests
# ============================================================================


class TestDefaultConstants:
    """Tests for default patterns and exact tools."""

    def test_default_patterns_exist(self):
        """Test default patterns list is not empty."""
        assert len(DEFAULT_PATTERNS) > 0
        assert "resolve_reference" in DEFAULT_PATTERNS
        assert "get_reference" in DEFAULT_PATTERNS

    def test_default_exact_tools_exist(self):
        """Test default exact tools list is not empty."""
        assert len(DEFAULT_EXACT_TOOLS) > 0
        assert "resolve_reference_tool" in DEFAULT_EXACT_TOOLS

    def test_hallucinations_file_path(self):
        """Test file path is in same directory as module."""
        assert HALLUCINATIONS_FILE.name == "hallucinated_tools.json"
        assert HALLUCINATIONS_FILE.parent.name == "registry"


# ============================================================================
# is_hallucinated_tool Tests
# ============================================================================


class TestIsHallucinatedTool:
    """Tests for is_hallucinated_tool function."""

    @pytest.fixture(autouse=True)
    def mock_registry(self):
        """Mock _load_registry to avoid file I/O."""
        mock_data = {
            "patterns": ["resolve_reference", "get_context"],
            "exact_tools": ["my_hallucinated_tool"],
            "history": [],
            "stats": {"total_detections": 0},
        }
        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            yield mock_data

    def test_empty_tool_name(self):
        """Test empty tool name returns False."""
        is_hallucinated, pattern = is_hallucinated_tool("")
        assert is_hallucinated is False
        assert pattern == ""

    def test_exact_match(self):
        """Test exact tool match."""
        is_hallucinated, pattern = is_hallucinated_tool("my_hallucinated_tool")
        assert is_hallucinated is True
        assert pattern.startswith("exact:")

    def test_exact_match_case_insensitive(self):
        """Test exact match is case insensitive."""
        is_hallucinated, pattern = is_hallucinated_tool("MY_HALLUCINATED_TOOL")
        assert is_hallucinated is True

    def test_pattern_match(self):
        """Test pattern substring match."""
        is_hallucinated, pattern = is_hallucinated_tool("some_resolve_reference_tool")
        assert is_hallucinated is True
        assert pattern.startswith("pattern:")
        assert "resolve_reference" in pattern

    def test_pattern_match_case_insensitive(self):
        """Test pattern match is case insensitive."""
        is_hallucinated, pattern = is_hallucinated_tool("Get_Context_Tool")
        assert is_hallucinated is True

    def test_non_hallucinated_tool(self):
        """Test non-hallucinated tool returns False."""
        is_hallucinated, pattern = is_hallucinated_tool("send_email_tool")
        assert is_hallucinated is False
        assert pattern == ""


# ============================================================================
# _load_registry Tests
# ============================================================================


class TestLoadRegistry:
    """Tests for _load_registry function."""

    def test_creates_file_if_not_exists(self):
        """Test creates initial file if doesn't exist."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False

        with patch(
            "src.domains.agents.registry.hallucinated_tools.HALLUCINATIONS_FILE",
            mock_path,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry_unlocked"
            ) as mock_save:
                with patch("src.domains.agents.registry.hallucinated_tools._file_lock"):
                    result = _load_registry()

                mock_save.assert_called_once()
                assert "patterns" in result
                assert "exact_tools" in result

    def test_loads_existing_file(self):
        """Test loads data from existing file."""
        existing_data = {
            "patterns": ["custom_pattern"],
            "exact_tools": ["custom_tool"],
            "history": [],
            "stats": {"total_detections": 5},
        }

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        m = mock_open(read_data=json.dumps(existing_data))

        with patch(
            "src.domains.agents.registry.hallucinated_tools.HALLUCINATIONS_FILE",
            mock_path,
        ):
            with patch(
                "builtins.open",
                m,
            ):
                with patch("src.domains.agents.registry.hallucinated_tools._file_lock"):
                    result = _load_registry()

        assert result["patterns"] == ["custom_pattern"]
        assert result["stats"]["total_detections"] == 5

    def test_handles_load_error_gracefully(self):
        """Test returns defaults on load error."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch(
            "src.domains.agents.registry.hallucinated_tools.HALLUCINATIONS_FILE",
            mock_path,
        ):
            with patch(
                "builtins.open",
                side_effect=OSError("File read error"),
            ):
                with patch("src.domains.agents.registry.hallucinated_tools._file_lock"):
                    result = _load_registry()

        # Should return defaults on error
        assert "patterns" in result
        assert result["patterns"] == DEFAULT_PATTERNS


# ============================================================================
# record_hallucination Tests
# ============================================================================


class TestRecordHallucination:
    """Tests for record_hallucination function."""

    @pytest.fixture
    def mock_registry_ops(self):
        """Mock registry load/save operations."""
        initial_data = {
            "patterns": ["existing_pattern"],
            "exact_tools": ["existing_tool"],
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=initial_data.copy(),
        ) as mock_load:
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(False, ""),
                ):
                    yield {
                        "mock_load": mock_load,
                        "mock_save": mock_save,
                        "initial_data": initial_data,
                    }

    def test_increments_stats(self, mock_registry_ops):
        """Test detection count is incremented."""
        record_hallucination("new_tool", domain="test", auto_add=False)

        mock_registry_ops["mock_save"].assert_called_once()
        saved_data = mock_registry_ops["mock_save"].call_args[0][0]
        assert saved_data["stats"]["total_detections"] == 1

    def test_adds_to_history(self, mock_registry_ops):
        """Test hallucination is added to history."""
        record_hallucination(
            "new_tool",
            domain="test_domain",
            query="test query",
            auto_add=False,
        )

        saved_data = mock_registry_ops["mock_save"].call_args[0][0]
        assert len(saved_data["history"]) == 1
        entry = saved_data["history"][0]
        assert entry["tool"] == "new_tool"
        assert entry["domain"] == "test_domain"
        assert "query_preview" in entry
        assert "timestamp" in entry

    def test_auto_adds_new_tool(self, mock_registry_ops):
        """Test auto_add adds new tool to exact_tools."""
        record_hallucination("brand_new_tool", auto_add=True)

        saved_data = mock_registry_ops["mock_save"].call_args[0][0]
        assert "brand_new_tool" in saved_data["exact_tools"]

    def test_truncates_query_preview(self, mock_registry_ops):
        """Test query is truncated for privacy."""
        long_query = "x" * 200
        record_hallucination("tool", query=long_query, auto_add=False)

        saved_data = mock_registry_ops["mock_save"].call_args[0][0]
        assert len(saved_data["history"][0]["query_preview"]) == 80

    def test_limits_history_size(self):
        """Test history is limited to 100 entries."""
        existing_history = [{"tool": f"tool_{i}"} for i in range(100)]
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": existing_history,
            "stats": {"total_detections": 100},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(True, "pattern:test"),
                ):
                    record_hallucination("new_tool", auto_add=False)

                saved_data = mock_save.call_args[0][0]
                assert len(saved_data["history"]) <= 100


# ============================================================================
# get_registry Tests
# ============================================================================


class TestGetRegistry:
    """Tests for get_registry function."""

    def test_returns_registry_data(self):
        """Test returns registry dictionary."""
        mock_data = {
            "patterns": ["test"],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            result = get_registry()

        assert result == mock_data


# ============================================================================
# add_pattern Tests
# ============================================================================


class TestAddPattern:
    """Tests for add_pattern function."""

    def test_adds_new_pattern(self):
        """Test adding a new pattern."""
        data = {
            "patterns": ["existing"],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_pattern("new_pattern")

                saved_data = mock_save.call_args[0][0]
                assert "new_pattern" in saved_data["patterns"]

    def test_does_not_add_duplicate(self):
        """Test doesn't add duplicate pattern."""
        data = {
            "patterns": ["existing"],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_pattern("existing")  # Already exists

                mock_save.assert_not_called()

    def test_case_insensitive_duplicate_check(self):
        """Test duplicate check is case insensitive."""
        data = {
            "patterns": ["EXISTING"],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_pattern("existing")  # Different case

                mock_save.assert_not_called()


# ============================================================================
# add_exact_tool Tests
# ============================================================================


class TestAddExactTool:
    """Tests for add_exact_tool function."""

    def test_adds_new_exact_tool(self):
        """Test adding a new exact tool."""
        data = {
            "patterns": [],
            "exact_tools": ["existing_tool"],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_exact_tool("new_tool")

                saved_data = mock_save.call_args[0][0]
                assert "new_tool" in saved_data["exact_tools"]

    def test_does_not_add_duplicate(self):
        """Test doesn't add duplicate tool."""
        data = {
            "patterns": [],
            "exact_tools": ["existing_tool"],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_exact_tool("existing_tool")

                mock_save.assert_not_called()

    def test_case_insensitive_duplicate_check(self):
        """Test duplicate check is case insensitive."""
        data = {
            "patterns": [],
            "exact_tools": ["EXISTING_TOOL"],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_exact_tool("existing_tool")

                mock_save.assert_not_called()


# ============================================================================
# Integration Tests
# ============================================================================


class TestHallucinatedToolsIntegration:
    """Integration tests for hallucinated tools module."""

    def test_common_hallucination_patterns(self):
        """Test common LLM hallucination patterns are detected."""
        mock_data = {
            "patterns": DEFAULT_PATTERNS,
            "exact_tools": DEFAULT_EXACT_TOOLS,
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            # Common hallucinations based on DEFAULT_PATTERNS:
            # resolve_reference, get_reference, resolve_context, get_context,
            # resolve_item, get_resolved, lookup_reference, dereference
            hallucinations = [
                "resolve_reference_tool",  # matches exact tool
                "get_reference_tool",  # matches exact tool
                "resolve_context_helper",  # matches resolve_context pattern
                "get_context_tool",  # matches get_context pattern
                "lookup_reference_util",  # matches lookup_reference pattern
            ]

            for tool in hallucinations:
                is_h, pattern = is_hallucinated_tool(tool)
                assert is_h is True, f"'{tool}' should be detected as hallucination"

    def test_legitimate_tools_not_flagged(self):
        """Test legitimate tools are not flagged."""
        mock_data = {
            "patterns": DEFAULT_PATTERNS,
            "exact_tools": DEFAULT_EXACT_TOOLS,
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            legitimate_tools = [
                "send_email_tool",
                "get_contacts_tool",
                "search_events_tool",
                "create_task_tool",
                "get_weather_tool",
            ]

            for tool in legitimate_tools:
                is_h, pattern = is_hallucinated_tool(tool)
                assert is_h is False, f"'{tool}' should NOT be flagged as hallucination"


# ============================================================================
# Additional Default Constants Tests
# ============================================================================


class TestDefaultConstantsEnhanced:
    """Enhanced tests for default patterns and exact tools."""

    def test_default_patterns_are_lowercase(self):
        """Test that default patterns are lowercase for consistent matching."""
        for pattern in DEFAULT_PATTERNS:
            assert pattern == pattern.lower(), f"Pattern '{pattern}' should be lowercase"

    def test_default_exact_tools_are_lowercase(self):
        """Test that default exact tools are lowercase."""
        for tool in DEFAULT_EXACT_TOOLS:
            assert tool == tool.lower(), f"Tool '{tool}' should be lowercase"

    def test_default_patterns_no_duplicates(self):
        """Test that default patterns have no duplicates."""
        assert len(DEFAULT_PATTERNS) == len(set(DEFAULT_PATTERNS))

    def test_default_exact_tools_no_duplicates(self):
        """Test that default exact tools have no duplicates."""
        assert len(DEFAULT_EXACT_TOOLS) == len(set(DEFAULT_EXACT_TOOLS))

    def test_default_patterns_content(self):
        """Test expected patterns are present."""
        expected = ["resolve_reference", "get_reference", "resolve_context", "get_context"]
        for pattern in expected:
            assert pattern in DEFAULT_PATTERNS

    def test_hallucinations_file_is_json(self):
        """Test file has .json extension."""
        assert HALLUCINATIONS_FILE.suffix == ".json"


# ============================================================================
# Parametrized Tests for is_hallucinated_tool
# ============================================================================


class TestIsHallucinatedToolParametrized:
    """Parametrized tests for is_hallucinated_tool."""

    @pytest.fixture(autouse=True)
    def mock_registry(self):
        """Mock _load_registry to avoid file I/O."""
        mock_data = {
            "patterns": DEFAULT_PATTERNS,
            "exact_tools": DEFAULT_EXACT_TOOLS,
            "history": [],
            "stats": {"total_detections": 0},
        }
        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            yield mock_data

    @pytest.mark.parametrize(
        "tool_name",
        [
            "resolve_reference_tool",
            "get_reference_tool",
            "RESOLVE_REFERENCE_TOOL",  # Case insensitive
            "my_resolve_reference_helper",
            "get_context_from_state",
            "resolve_context_util",
            "lookup_reference_service",
            "dereference_id",
        ],
    )
    def test_hallucinated_tools_detected(self, tool_name: str):
        """Test that hallucinated tools are detected."""
        is_h, _ = is_hallucinated_tool(tool_name)
        assert is_h is True, f"'{tool_name}' should be detected as hallucination"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "send_email_tool",
            "search_contacts_tool",
            "get_weather_tool",
            "create_calendar_event_tool",
            "list_tasks_tool",
            "search_places_tool",
            "get_directions_tool",
        ],
    )
    def test_legitimate_tools_not_detected(self, tool_name: str):
        """Test that legitimate tools are not flagged."""
        is_h, _ = is_hallucinated_tool(tool_name)
        assert is_h is False, f"'{tool_name}' should NOT be flagged"

    @pytest.mark.parametrize(
        "tool_name,expected_pattern_type",
        [
            ("resolve_reference_tool", "exact"),
            ("get_reference_tool", "exact"),
            ("some_resolve_reference_helper", "pattern"),
            ("get_context_tool", "pattern"),
        ],
    )
    def test_pattern_type_in_result(self, tool_name: str, expected_pattern_type: str):
        """Test that result contains correct pattern type prefix."""
        is_h, pattern = is_hallucinated_tool(tool_name)
        assert is_h is True
        assert pattern.startswith(expected_pattern_type + ":")


# ============================================================================
# Edge Cases for is_hallucinated_tool
# ============================================================================


class TestIsHallucinatedToolEdgeCases:
    """Edge case tests for is_hallucinated_tool."""

    @pytest.fixture(autouse=True)
    def mock_registry(self):
        """Mock _load_registry to avoid file I/O."""
        mock_data = {
            "patterns": ["test_pattern"],
            "exact_tools": ["exact_tool"],
            "history": [],
            "stats": {"total_detections": 0},
        }
        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            yield

    def test_none_tool_name(self):
        """Test None tool name (should handle gracefully)."""
        # None is falsy, so should return False
        is_h, pattern = is_hallucinated_tool(None)  # type: ignore
        assert is_h is False
        assert pattern == ""

    def test_whitespace_only_tool_name(self):
        """Test whitespace tool name."""
        is_h, pattern = is_hallucinated_tool("   ")
        # Non-empty string with whitespace, won't match patterns
        assert is_h is False

    def test_special_characters_in_tool_name(self):
        """Test tool name with special characters."""
        is_h, pattern = is_hallucinated_tool("tool@#$%")
        assert is_h is False

    def test_numeric_tool_name(self):
        """Test numeric tool name."""
        is_h, pattern = is_hallucinated_tool("12345")
        assert is_h is False

    def test_very_long_tool_name(self):
        """Test very long tool name."""
        long_name = "a" * 1000
        is_h, pattern = is_hallucinated_tool(long_name)
        assert is_h is False

    def test_unicode_tool_name(self):
        """Test unicode tool name."""
        is_h, pattern = is_hallucinated_tool("tool_émoji_🔧")
        assert is_h is False


# ============================================================================
# Save Registry Tests
# ============================================================================


class TestSaveRegistry:
    """Tests for _save_registry functions."""

    def test_save_registry_adds_timestamp(self):
        """Test that save adds last_updated timestamp."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {"total_detections": 0},
        }

        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            with patch("src.domains.agents.registry.hallucinated_tools._file_lock"):
                _save_registry_unlocked(data)

        assert "last_updated" in data["stats"]

    def test_save_registry_handles_error(self):
        """Test that save handles errors gracefully."""
        data = {"stats": {}}

        with patch("builtins.open", side_effect=OSError("Write error")):
            with patch("src.domains.agents.registry.hallucinated_tools.logger") as mock_logger:
                with patch("src.domains.agents.registry.hallucinated_tools._file_lock"):
                    _save_registry_unlocked(data)

                # Should log error
                mock_logger.error.assert_called()

    def test_save_registry_thread_safe(self):
        """Test that _save_registry uses lock."""
        data = {"stats": {}}

        with patch("builtins.open", mock_open()):
            with patch("src.domains.agents.registry.hallucinated_tools._file_lock") as mock_lock:
                _save_registry(data)

                # Should have acquired lock
                mock_lock.__enter__.assert_called()


# ============================================================================
# Record Hallucination Enhanced Tests
# ============================================================================


class TestRecordHallucinationEnhanced:
    """Enhanced tests for record_hallucination function."""

    def test_logs_warning_on_record(self):
        """Test that recording logs a warning."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch("src.domains.agents.registry.hallucinated_tools._save_registry"):
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(False, ""),
                ):
                    with patch(
                        "src.domains.agents.registry.hallucinated_tools.logger"
                    ) as mock_logger:
                        record_hallucination("new_tool", domain="test")

                        mock_logger.warning.assert_called()
                        call_kwargs = mock_logger.warning.call_args[1]
                        assert call_kwargs["tool_name"] == "new_tool"
                        assert call_kwargs["domain"] == "test"

    def test_logs_info_when_auto_adding(self):
        """Test that auto-add logs info."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch("src.domains.agents.registry.hallucinated_tools._save_registry"):
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(False, ""),
                ):
                    with patch(
                        "src.domains.agents.registry.hallucinated_tools.logger"
                    ) as mock_logger:
                        record_hallucination("brand_new_tool", auto_add=True)

                        # Should have info call for auto-add
                        mock_logger.info.assert_called()

    def test_does_not_auto_add_when_already_covered(self):
        """Test that auto_add doesn't add if already covered."""
        data = {
            "patterns": ["existing_pattern"],
            "exact_tools": [],
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(True, "pattern:existing_pattern"),  # Already covered
                ):
                    record_hallucination("existing_pattern_tool", auto_add=True)

                    # Should NOT add to exact_tools
                    saved_data = mock_save.call_args[0][0]
                    assert "existing_pattern_tool" not in saved_data.get("exact_tools", [])

    def test_history_entry_structure(self):
        """Test history entry has correct structure."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {"total_detections": 0},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                with patch(
                    "src.domains.agents.registry.hallucinated_tools.is_hallucinated_tool",
                    return_value=(False, ""),
                ):
                    record_hallucination(
                        "test_tool",
                        domain="test_domain",
                        query="test query",
                        auto_add=False,
                    )

                    saved_data = mock_save.call_args[0][0]
                    entry = saved_data["history"][0]

                    # Verify structure
                    assert "tool" in entry
                    assert "domain" in entry
                    assert "query_preview" in entry
                    assert "timestamp" in entry
                    assert "was_new" in entry


# ============================================================================
# Get Registry Tests
# ============================================================================


class TestGetRegistryEnhanced:
    """Enhanced tests for get_registry function."""

    def test_returns_dict(self):
        """Test returns a dictionary."""
        mock_data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            result = get_registry()

        assert isinstance(result, dict)

    def test_returns_expected_keys(self):
        """Test returns expected keys."""
        mock_data = {
            "patterns": ["p1"],
            "exact_tools": ["t1"],
            "history": [{"entry": 1}],
            "stats": {"total_detections": 5},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            result = get_registry()

        assert "patterns" in result
        assert "exact_tools" in result
        assert "history" in result
        assert "stats" in result


# ============================================================================
# Add Pattern Enhanced Tests
# ============================================================================


class TestAddPatternEnhanced:
    """Enhanced tests for add_pattern function."""

    def test_pattern_stored_lowercase(self):
        """Test that patterns are stored lowercase."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_pattern("NEW_PATTERN")

                saved_data = mock_save.call_args[0][0]
                assert "new_pattern" in saved_data["patterns"]
                assert "NEW_PATTERN" not in saved_data["patterns"]

    def test_logs_on_add(self):
        """Test that adding pattern logs info."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch("src.domains.agents.registry.hallucinated_tools._save_registry"):
                with patch("src.domains.agents.registry.hallucinated_tools.logger") as mock_logger:
                    add_pattern("new_pattern")

                    mock_logger.info.assert_called()


# ============================================================================
# Add Exact Tool Enhanced Tests
# ============================================================================


class TestAddExactToolEnhanced:
    """Enhanced tests for add_exact_tool function."""

    def test_tool_stored_lowercase(self):
        """Test that tools are stored lowercase."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch(
                "src.domains.agents.registry.hallucinated_tools._save_registry"
            ) as mock_save:
                add_exact_tool("NEW_TOOL")

                saved_data = mock_save.call_args[0][0]
                assert "new_tool" in saved_data["exact_tools"]
                assert "NEW_TOOL" not in saved_data["exact_tools"]

    def test_logs_on_add(self):
        """Test that adding tool logs info."""
        data = {
            "patterns": [],
            "exact_tools": [],
            "history": [],
            "stats": {},
        }

        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=data,
        ):
            with patch("src.domains.agents.registry.hallucinated_tools._save_registry"):
                with patch("src.domains.agents.registry.hallucinated_tools.logger") as mock_logger:
                    add_exact_tool("new_tool")

                    mock_logger.info.assert_called()


# ============================================================================
# Real-World Integration Tests
# ============================================================================


class TestRealWorldIntegration:
    """Real-world integration tests."""

    @pytest.fixture(autouse=True)
    def mock_registry(self):
        """Mock with real default patterns."""
        mock_data = {
            "patterns": DEFAULT_PATTERNS,
            "exact_tools": DEFAULT_EXACT_TOOLS,
            "history": [],
            "stats": {"total_detections": 0},
        }
        with patch(
            "src.domains.agents.registry.hallucinated_tools._load_registry",
            return_value=mock_data,
        ):
            yield

    @pytest.mark.parametrize(
        "hallucinated_tool",
        [
            # Common LLM hallucinations
            "resolve_reference_tool",
            "get_reference_by_id",
            "resolve_context_from_state",
            "get_context_tool",
            "resolve_item_reference",
            "get_resolved_entity",
            "lookup_reference_by_name",
            "dereference_pointer",
        ],
    )
    def test_common_llm_hallucinations(self, hallucinated_tool: str):
        """Test that common LLM hallucinations are detected."""
        is_h, _ = is_hallucinated_tool(hallucinated_tool)
        assert is_h is True

    @pytest.mark.parametrize(
        "tool_name,domain",
        [
            ("contacts", "send_email_tool"),
            ("calendar", "create_event_tool"),
            ("tasks", "create_task_tool"),
            ("weather", "get_weather_tool"),
            ("places", "search_places_tool"),
            ("routes", "get_directions_tool"),
        ],
    )
    def test_domain_tools_not_hallucinated(self, tool_name: str, domain: str):
        """Test that real domain tools are not flagged."""
        is_h, _ = is_hallucinated_tool(domain)
        assert is_h is False
