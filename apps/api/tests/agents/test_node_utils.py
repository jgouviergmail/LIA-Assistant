"""
Tests for node utility functions.

This module tests the common helper functions used across multiple nodes
to ensure consistent behavior and proper error handling.
"""

import pytest
from langchain_core.runnables import RunnableConfig

from src.domains.agents.nodes.utils import extract_session_id_from_config


class TestExtractSessionIdFromConfig:
    """Tests for extract_session_id_from_config helper function."""

    def test_extract_session_id_success(self):
        """Test successful extraction of session_id from config."""
        config: RunnableConfig = {"configurable": {"thread_id": "conv_123"}}
        result = extract_session_id_from_config(config)
        assert result == "conv_123"

    def test_extract_session_id_with_uuid(self):
        """Test extraction with UUID-style thread_id."""
        config: RunnableConfig = {
            "configurable": {"thread_id": "550e8400-e29b-41d4-a716-446655440000"}
        }
        result = extract_session_id_from_config(config)
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_extract_session_id_missing_required_raises_error(self):
        """Test that missing thread_id raises ValueError when required=True."""
        config: RunnableConfig = {"configurable": {}}
        with pytest.raises(ValueError, match="thread_id missing in config.configurable"):
            extract_session_id_from_config(config, required=True)

    def test_extract_session_id_missing_required_explicit(self):
        """Test explicit required=True parameter."""
        config: RunnableConfig = {"configurable": {}}
        with pytest.raises(ValueError) as exc_info:
            extract_session_id_from_config(config, required=True)

        error_msg = str(exc_info.value)
        assert "thread_id missing" in error_msg
        assert "config.configurable" in error_msg
        assert "RunnableConfig" in error_msg

    def test_extract_session_id_missing_optional_returns_empty(self):
        """Test that missing thread_id returns empty string when required=False."""
        config: RunnableConfig = {"configurable": {}}
        result = extract_session_id_from_config(config, required=False)
        assert result == ""

    def test_extract_session_id_empty_string_required_raises(self):
        """Test that empty string thread_id raises error when required=True."""
        config: RunnableConfig = {"configurable": {"thread_id": ""}}
        with pytest.raises(ValueError, match="thread_id missing"):
            extract_session_id_from_config(config, required=True)

    def test_extract_session_id_empty_string_optional_returns_empty(self):
        """Test that empty string thread_id returns empty when required=False."""
        config: RunnableConfig = {"configurable": {"thread_id": ""}}
        result = extract_session_id_from_config(config, required=False)
        assert result == ""

    def test_extract_session_id_missing_configurable_key(self):
        """Test behavior when 'configurable' key is missing entirely."""
        config: RunnableConfig = {}
        with pytest.raises(ValueError):
            extract_session_id_from_config(config, required=True)

    def test_extract_session_id_missing_configurable_key_optional(self):
        """Test that missing 'configurable' key returns empty when required=False."""
        config: RunnableConfig = {}
        result = extract_session_id_from_config(config, required=False)
        assert result == ""

    def test_extract_session_id_with_other_configurable_keys(self):
        """Test extraction when other keys are present in configurable."""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "conv_456",
                "user_id": "user_123",
                "checkpoint_id": "ckpt_789",
            }
        }
        result = extract_session_id_from_config(config)
        assert result == "conv_456"

    def test_extract_session_id_default_required_true(self):
        """Test that default behavior is required=True."""
        config: RunnableConfig = {"configurable": {}}
        # Default should be required=True, so should raise
        with pytest.raises(ValueError):
            extract_session_id_from_config(config)

    def test_extract_session_id_with_numeric_thread_id(self):
        """Test extraction with numeric thread_id (converted to string)."""
        config: RunnableConfig = {"configurable": {"thread_id": "12345"}}
        result = extract_session_id_from_config(config)
        assert result == "12345"

    def test_extract_session_id_with_special_characters(self):
        """Test extraction with special characters in thread_id."""
        config: RunnableConfig = {"configurable": {"thread_id": "conv_test-123_456"}}
        result = extract_session_id_from_config(config)
        assert result == "conv_test-123_456"

    def test_error_message_quality(self):
        """Test that error message provides clear guidance."""
        config: RunnableConfig = {"configurable": {}}
        with pytest.raises(ValueError) as exc_info:
            extract_session_id_from_config(config, required=True)

        error_msg = str(exc_info.value)
        # Check error message contains helpful guidance
        assert "required for session-based operations" in error_msg
        assert "thread_id" in error_msg
        assert "conversation_id" in error_msg
