"""
Unit tests for SubAgentService.

Tests CRUD operations, ownership checks, limits, templates, toggle,
and execution recording.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.sub_agents.constants import SUBAGENT_TEMPLATES
from src.domains.sub_agents.models import SubAgentCreatedBy, SubAgentStatus
from src.domains.sub_agents.schemas import (
    SubAgentCreate,
    SubAgentCreateFromTemplate,
    SubAgentUpdate,
)
from src.domains.sub_agents.service import SubAgentService


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """SubAgentService with mocked DB."""
    return SubAgentService(mock_db)


@pytest.fixture
def sample_create_data():
    """Sample SubAgentCreate data."""
    return SubAgentCreate(
        name="Research Assistant",
        description="Deep research specialist",
        system_prompt="You are a research specialist.",
        skill_ids=["web_search"],
        blocked_tools=["send_email_tool"],
    )


@pytest.fixture
def mock_subagent():
    """Mock SubAgent ORM instance."""
    agent = MagicMock()
    agent.id = uuid4()
    agent.user_id = uuid4()
    agent.name = "Research Assistant"
    agent.description = "Deep research specialist"
    agent.is_enabled = True
    agent.status = SubAgentStatus.READY.value
    agent.created_by = SubAgentCreatedBy.USER.value
    agent.execution_count = 0
    agent.consecutive_failures = 0
    agent.last_error = None
    agent.last_execution_summary = None
    return agent


class TestCreate:
    """Tests for SubAgentService.create()."""

    async def test_create_success(self, service, sample_create_data, mock_subagent):
        """Create a sub-agent successfully."""
        user_id = uuid4()
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.get_by_name_for_user = AsyncMock(return_value=None)
        service.repository.create = AsyncMock(return_value=mock_subagent)

        result = await service.create(user_id, sample_create_data)

        assert result == mock_subagent
        service.repository.count_for_user.assert_called_once_with(user_id)
        service.repository.get_by_name_for_user.assert_called_once_with(
            user_id, "Research Assistant"
        )

    async def test_create_exceeds_limit(self, service, sample_create_data):
        """Raise ValidationError when user limit is reached."""
        from src.core.exceptions import ValidationError

        user_id = uuid4()
        service.repository.count_for_user = AsyncMock(return_value=10)

        with pytest.raises(ValidationError, match="Maximum of"):
            await service.create(user_id, sample_create_data)

    async def test_create_duplicate_name(self, service, sample_create_data, mock_subagent):
        """Raise ResourceConflictError on duplicate name."""
        from src.core.exceptions import ResourceConflictError

        user_id = uuid4()
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.get_by_name_for_user = AsyncMock(return_value=mock_subagent)

        with pytest.raises(ResourceConflictError, match="already exists"):
            await service.create(user_id, sample_create_data)


class TestCreateFromTemplate:
    """Tests for SubAgentService.create_from_template()."""

    async def test_create_from_template_success(self, service, mock_subagent):
        """Create from a valid template."""
        user_id = uuid4()
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.get_by_name_for_user = AsyncMock(return_value=None)
        service.repository.create = AsyncMock(return_value=mock_subagent)

        result = await service.create_from_template(user_id, "research_assistant")

        assert result == mock_subagent
        create_call = service.repository.create.call_args
        assert create_call[0][0]["template_id"] == "research_assistant"

    async def test_create_from_template_unknown(self, service):
        """Raise ValidationError for unknown template."""
        from src.core.exceptions import ValidationError

        user_id = uuid4()

        with pytest.raises(ValidationError, match="Unknown template"):
            await service.create_from_template(user_id, "nonexistent_template")

    async def test_create_from_template_with_overrides(self, service, mock_subagent):
        """Create from template with name override."""
        user_id = uuid4()
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.get_by_name_for_user = AsyncMock(return_value=None)
        service.repository.create = AsyncMock(return_value=mock_subagent)

        overrides = SubAgentCreateFromTemplate(name="My Custom Researcher")
        result = await service.create_from_template(user_id, "research_assistant", overrides)

        assert result == mock_subagent
        create_call = service.repository.create.call_args
        assert create_call[0][0]["name"] == "My Custom Researcher"
        assert create_call[0][0]["template_id"] == "research_assistant"


class TestOwnership:
    """Tests for ownership checks."""

    async def test_get_with_ownership_check_success(self, service, mock_subagent):
        """Return sub-agent when ownership matches."""
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)

        result = await service.get_with_ownership_check(mock_subagent.id, mock_subagent.user_id)
        assert result == mock_subagent

    async def test_get_with_ownership_check_not_found(self, service):
        """Raise ResourceNotFoundError when not found."""
        from src.core.exceptions import ResourceNotFoundError

        service.repository.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundError):
            await service.get_with_ownership_check(uuid4(), uuid4())

    async def test_get_with_ownership_check_wrong_user(self, service, mock_subagent):
        """Raise ResourceNotFoundError for wrong user."""
        from src.core.exceptions import ResourceNotFoundError

        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)

        with pytest.raises(ResourceNotFoundError):
            await service.get_with_ownership_check(mock_subagent.id, uuid4())


class TestDelete:
    """Tests for SubAgentService.delete()."""

    async def test_delete_success(self, service, mock_subagent):
        """Delete a sub-agent successfully."""
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.delete = AsyncMock()

        await service.delete(mock_subagent.id, mock_subagent.user_id)
        service.repository.delete.assert_called_once_with(mock_subagent)

    async def test_delete_while_executing(self, service, mock_subagent):
        """Raise ResourceConflictError when deleting an executing sub-agent."""
        from src.core.exceptions import ResourceConflictError

        mock_subagent.status = SubAgentStatus.EXECUTING.value
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)

        with pytest.raises(ResourceConflictError, match="executing"):
            await service.delete(mock_subagent.id, mock_subagent.user_id)


class TestToggle:
    """Tests for SubAgentService.toggle()."""

    async def test_toggle_disable(self, service, mock_subagent):
        """Toggle from enabled to disabled."""
        mock_subagent.is_enabled = True
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.update = AsyncMock(return_value=mock_subagent)

        await service.toggle(mock_subagent.id, mock_subagent.user_id)

        update_call = service.repository.update.call_args
        assert update_call[0][1]["is_enabled"] is False

    async def test_toggle_enable_resets_error(self, service, mock_subagent):
        """Toggle from disabled to enabled resets error state."""
        mock_subagent.is_enabled = False
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.update = AsyncMock(return_value=mock_subagent)

        await service.toggle(mock_subagent.id, mock_subagent.user_id)

        update_call = service.repository.update.call_args
        update_data = update_call[0][1]
        assert update_data["is_enabled"] is True
        assert update_data["status"] == SubAgentStatus.READY.value
        assert update_data["consecutive_failures"] == 0
        assert update_data["last_error"] is None

    async def test_toggle_while_executing(self, service, mock_subagent):
        """Raise ResourceConflictError when toggling an executing sub-agent."""
        from src.core.exceptions import ResourceConflictError

        mock_subagent.status = SubAgentStatus.EXECUTING.value
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)

        with pytest.raises(ResourceConflictError, match="executing"):
            await service.toggle(mock_subagent.id, mock_subagent.user_id)


class TestRecordExecution:
    """Tests for SubAgentService.record_execution()."""

    async def test_record_success(self, service, mock_subagent):
        """Record successful execution."""
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.update = AsyncMock(return_value=mock_subagent)

        await service.record_execution(mock_subagent.id, success=True, summary="Found 3 results")

        update_call = service.repository.update.call_args
        update_data = update_call[0][1]
        assert update_data["consecutive_failures"] == 0
        assert update_data["last_execution_summary"] == "Found 3 results"
        assert update_data["status"] == SubAgentStatus.READY.value

    async def test_record_failure(self, service, mock_subagent):
        """Record failed execution."""
        mock_subagent.consecutive_failures = 0
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.update = AsyncMock(return_value=mock_subagent)

        await service.record_execution(mock_subagent.id, success=False, error="Timeout")

        update_call = service.repository.update.call_args
        update_data = update_call[0][1]
        assert update_data["consecutive_failures"] == 1
        assert update_data["last_error"] == "Timeout"

    @patch("src.domains.sub_agents.service.settings")
    async def test_auto_disable_after_max_failures(self, mock_settings, service, mock_subagent):
        """Auto-disable after reaching consecutive failure threshold."""
        mock_settings.subagent_max_consecutive_failures = 3
        mock_subagent.consecutive_failures = 2  # Next failure = 3 = threshold
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.update = AsyncMock(return_value=mock_subagent)

        await service.record_execution(mock_subagent.id, success=False, error="Third failure")

        update_call = service.repository.update.call_args
        update_data = update_call[0][1]
        assert update_data["is_enabled"] is False
        assert update_data["status"] == SubAgentStatus.ERROR.value
        assert update_data["consecutive_failures"] == 3


class TestUpdate:
    """Tests for SubAgentService.update()."""

    async def test_update_name_conflict(self, service, mock_subagent):
        """Raise ResourceConflictError on name conflict during update."""
        from src.core.exceptions import ResourceConflictError

        other_agent = MagicMock()
        other_agent.id = uuid4()

        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)
        service.repository.get_by_name_for_user = AsyncMock(return_value=other_agent)

        data = SubAgentUpdate(name="Taken Name")
        with pytest.raises(ResourceConflictError, match="already exists"):
            await service.update(mock_subagent.id, mock_subagent.user_id, data)

    async def test_update_empty_data(self, service, mock_subagent):
        """Return unchanged sub-agent when no fields are updated."""
        service.repository.get_by_id = AsyncMock(return_value=mock_subagent)

        data = SubAgentUpdate()
        result = await service.update(mock_subagent.id, mock_subagent.user_id, data)
        assert result == mock_subagent


class TestTemplates:
    """Tests for template listing."""

    def test_list_templates(self):
        """Verify templates are returned."""
        templates = SubAgentService.list_templates()
        assert len(templates) == len(SUBAGENT_TEMPLATES)
        assert templates[0]["id"] == "research_assistant"

    def test_templates_have_blocked_tools(self):
        """Verify all templates include default_blocked_tools."""
        for template in SUBAGENT_TEMPLATES:
            assert "default_blocked_tools" in template
            assert len(template["default_blocked_tools"]) > 0
            assert "send_email_tool" in template["default_blocked_tools"]
