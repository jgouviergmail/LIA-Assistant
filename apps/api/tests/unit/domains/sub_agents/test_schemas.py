"""
Unit tests for Sub-Agents Pydantic schemas.

Tests validation rules, default values, and model serialization.
"""

import pytest
from pydantic import ValidationError

from src.domains.sub_agents.schemas import (
    SubAgentCreate,
    SubAgentExecutionRequest,
    SubAgentTemplateResponse,
    SubAgentUpdate,
)


class TestSubAgentCreate:
    """Tests for SubAgentCreate schema."""

    def test_valid_minimal(self):
        """Create with required fields only."""
        data = SubAgentCreate(
            name="Test Agent",
            description="A test agent",
            system_prompt="You are helpful.",
        )
        assert data.name == "Test Agent"
        assert data.skill_ids == []
        assert data.blocked_tools == []
        assert data.max_iterations == 5
        assert data.timeout_seconds == 120

    def test_valid_full(self):
        """Create with all fields."""
        data = SubAgentCreate(
            name="Research Bot",
            description="Deep research",
            system_prompt="Research everything.",
            personality_instruction="Be concise.",
            icon="🔍",
            llm_provider="openai",
            llm_model="gpt-4.1-mini",
            llm_temperature=0.7,
            max_iterations=10,
            timeout_seconds=300,
            skill_ids=["web_search"],
            allowed_tools=["brave_search_tool"],
            blocked_tools=["send_email_tool"],
            context_instructions="Focus on recent data.",
        )
        assert data.llm_temperature == 0.7
        assert data.max_iterations == 10

    def test_name_too_long(self):
        """Reject name over 100 characters."""
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="x" * 101,
                description="test",
                system_prompt="test",
            )

    def test_name_empty(self):
        """Reject empty name."""
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="",
                description="test",
                system_prompt="test",
            )

    def test_max_iterations_bounds(self):
        """Reject max_iterations outside 1-15."""
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="Test",
                description="test",
                system_prompt="test",
                max_iterations=16,
            )
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="Test",
                description="test",
                system_prompt="test",
                max_iterations=0,
            )

    def test_timeout_bounds(self):
        """Reject timeout outside 10-600."""
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="Test",
                description="test",
                system_prompt="test",
                timeout_seconds=5,
            )

    def test_temperature_bounds(self):
        """Reject temperature outside 0.0-2.0."""
        with pytest.raises(ValidationError):
            SubAgentCreate(
                name="Test",
                description="test",
                system_prompt="test",
                llm_temperature=2.5,
            )


class TestSubAgentUpdate:
    """Tests for SubAgentUpdate schema."""

    def test_all_optional(self):
        """All fields are optional."""
        data = SubAgentUpdate()
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_partial_update(self):
        """Partial update with only some fields."""
        data = SubAgentUpdate(name="New Name", max_iterations=10)
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"name": "New Name", "max_iterations": 10}


class TestSubAgentExecutionRequest:
    """Tests for SubAgentExecutionRequest schema."""

    def test_valid(self):
        """Valid execution request."""
        req = SubAgentExecutionRequest(instruction="Search for Python tutorials")
        assert req.run_in_background is False
        assert req.context is None

    def test_empty_instruction(self):
        """Reject empty instruction."""
        with pytest.raises(ValidationError):
            SubAgentExecutionRequest(instruction="")


class TestSubAgentTemplateResponse:
    """Tests for SubAgentTemplateResponse schema."""

    def test_serialization(self):
        """Template response serializes correctly."""
        resp = SubAgentTemplateResponse(
            id="research_assistant",
            name="Research Assistant",
            description="Deep research",
            icon="🔍",
            suggested_skill_ids=["web_search"],
            suggested_tools=["brave_search_tool"],
            default_blocked_tools=["send_email_tool"],
        )
        assert resp.id == "research_assistant"
        assert len(resp.default_blocked_tools) == 1
