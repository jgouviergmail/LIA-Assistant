"""
Unit tests for Connector Repository.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 27.2
Created: 2025-11-21
Target: 32% → 80%+ coverage
Module: domains/connectors/repository.py (60 statements)

Test Coverage:
- __init__: Initialization with AsyncSession
- get_by_user_and_type: Query by user_id + connector_type
- get_all_by_user: Query all connectors for user (with/without status filter)
- revoke: Set connector status to REVOKED
- update_credentials: Update encrypted credentials
- get_all_global_configs: Query all global configs
- get_global_config_by_type: Query global config by type
- create_global_config: Create global config
- update_global_config: Update global config
- get_all_connectors_by_type: Query connectors by type (with/without status, with user eager loading)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.repository import ConnectorRepository


class TestConnectorRepositoryInit:
    """Tests for ConnectorRepository initialization."""

    @pytest.mark.asyncio
    async def test_init_sets_db_and_model(self):
        """Test __init__ sets db session and model class (Lines 35-36)."""
        mock_db = AsyncMock()

        repo = ConnectorRepository(mock_db)

        assert repo.db == mock_db
        assert repo.model == Connector
        assert repo.model_name == "Connector"


class TestGetByUserAndType:
    """Tests for get_by_user_and_type method."""

    @pytest.mark.asyncio
    async def test_get_by_user_and_type_found(self):
        """Test get_by_user_and_type returns connector when found (Lines 38-57)."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock connector found
        mock_connector = Connector(
            id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="encrypted_creds",
            scopes=["https://mail.google.com/"],
        )

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_connector)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 38-57 executed: Query by user_id + connector_type
        result = await repo.get_by_user_and_type(user_id, ConnectorType.GOOGLE_GMAIL)

        assert result == mock_connector
        assert result.id == connector_id
        assert result.user_id == user_id
        assert result.connector_type == ConnectorType.GOOGLE_GMAIL
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_user_and_type_not_found(self):
        """Test get_by_user_and_type returns None when not found (Line 57)."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        # Mock no connector found
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Line 57 executed: None returned
        result = await repo.get_by_user_and_type(user_id, ConnectorType.GOOGLE_DRIVE)

        assert result is None
        mock_db.execute.assert_called_once()


class TestGetAllByUser:
    """Tests for get_all_by_user method."""

    @pytest.mark.asyncio
    async def test_get_all_by_user_no_filter(self):
        """Test get_all_by_user returns all connectors (no status filter) (Lines 59-80)."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        # Mock 3 connectors
        connector1 = Connector(
            id=uuid.uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="creds1",
            scopes=[],
        )
        connector2 = Connector(
            id=uuid.uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_DRIVE,
            status=ConnectorStatus.REVOKED,
            credentials_encrypted="creds2",
            scopes=[],
        )
        connector3 = Connector(
            id=uuid.uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            status=ConnectorStatus.ERROR,
            credentials_encrypted="creds3",
            scopes=[],
        )

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[connector1, connector2, connector3])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 74-80 executed: Query without status filter
        result = await repo.get_all_by_user(user_id)

        assert len(result) == 3
        assert connector1 in result
        assert connector2 in result
        assert connector3 in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_by_user_with_status_filter(self):
        """Test get_all_by_user with status filter (Lines 76-80)."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        # Mock 1 active connector
        connector_active = Connector(
            id=uuid.uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="creds_active",
            scopes=[],
        )

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[connector_active])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 76-80 executed: Query with status filter
        result = await repo.get_all_by_user(user_id, status=ConnectorStatus.ACTIVE)

        assert len(result) == 1
        assert result[0].status == ConnectorStatus.ACTIVE
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_by_user_empty_list(self):
        """Test get_all_by_user returns empty list when no connectors (Line 80)."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Line 80 executed: Empty list returned
        result = await repo.get_all_by_user(user_id)

        assert result == []
        mock_db.execute.assert_called_once()


class TestRevoke:
    """Tests for revoke method."""

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_revoke_sets_status_and_logs(self, mock_logger):
        """Test revoke sets status to REVOKED and logs event (Lines 84-103)."""
        mock_db = AsyncMock()
        connector_id = uuid.uuid4()

        connector = Connector(
            id=connector_id,
            user_id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="creds",
            scopes=[],
        )

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        repo = ConnectorRepository(mock_db)

        # Lines 84-103 executed: Set status to REVOKED
        result = await repo.revoke(connector)

        assert result.status == ConnectorStatus.REVOKED
        assert result == connector
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(connector)

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "connector_revoked",
            connector_id=str(connector_id),
            connector_type=ConnectorType.GOOGLE_GMAIL,
        )


class TestUpdateCredentials:
    """Tests for update_credentials method."""

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_update_credentials_updates_and_logs(self, mock_logger):
        """Test update_credentials updates encrypted creds and logs (Lines 105-123)."""
        mock_db = AsyncMock()
        connector_id = uuid.uuid4()

        connector = Connector(
            id=connector_id,
            user_id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_DRIVE,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="old_creds",
            scopes=[],
        )

        new_creds = "new_encrypted_credentials"

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        repo = ConnectorRepository(mock_db)

        # Lines 105-123 executed: Update credentials
        result = await repo.update_credentials(connector, new_creds)

        assert result.credentials_encrypted == new_creds
        assert result == connector
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(connector)

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "connector_credentials_updated", connector_id=str(connector_id)
        )


class TestGetAllGlobalConfigs:
    """Tests for get_all_global_configs method."""

    @pytest.mark.asyncio
    async def test_get_all_global_configs_returns_list(self):
        """Test get_all_global_configs returns all configs (Lines 127-137)."""
        mock_db = AsyncMock()

        # Mock 2 global configs
        config1 = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            is_enabled=True,
            disabled_reason=None,
        )
        config2 = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_DRIVE,
            is_enabled=False,
            disabled_reason="Maintenance",
        )

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[config1, config2])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 127-137 executed: Query all global configs
        result = await repo.get_all_global_configs()

        assert len(result) == 2
        assert config1 in result
        assert config2 in result
        mock_db.execute.assert_called_once()


class TestGetGlobalConfigByType:
    """Tests for get_global_config_by_type method."""

    @pytest.mark.asyncio
    async def test_get_global_config_by_type_found(self):
        """Test get_global_config_by_type returns config when found (Lines 139-156)."""
        mock_db = AsyncMock()

        config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            is_enabled=True,
            disabled_reason=None,
        )

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=config)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 139-156 executed: Query global config by type
        result = await repo.get_global_config_by_type(ConnectorType.GOOGLE_CONTACTS)

        assert result == config
        assert result.connector_type == ConnectorType.GOOGLE_CONTACTS
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_global_config_by_type_not_found(self):
        """Test get_global_config_by_type returns None when not found (Line 156)."""
        mock_db = AsyncMock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Line 156 executed: None returned
        result = await repo.get_global_config_by_type(ConnectorType.SLACK)

        assert result is None
        mock_db.execute.assert_called_once()


class TestCreateGlobalConfig:
    """Tests for create_global_config method."""

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_create_global_config_enabled(self, mock_logger):
        """Test create_global_config creates enabled config (Lines 158-186)."""
        mock_db = AsyncMock()

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        # Mock refresh to set ID
        async def mock_refresh(config):
            config.id = uuid.uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        repo = ConnectorRepository(mock_db)

        # Lines 158-186 executed: Create global config
        result = await repo.create_global_config(
            ConnectorType.GOOGLE_TASKS, is_enabled=True, disabled_reason=None
        )

        assert result.connector_type == ConnectorType.GOOGLE_TASKS
        assert result.is_enabled is True
        assert result.disabled_reason is None
        assert result.id is not None

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "connector_global_config_created",
            connector_type=ConnectorType.GOOGLE_TASKS.value,
            is_enabled=True,
        )

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_create_global_config_disabled_with_reason(self, mock_logger):
        """Test create_global_config creates disabled config with reason (Lines 172-186)."""
        mock_db = AsyncMock()

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        async def mock_refresh(config):
            config.id = uuid.uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        repo = ConnectorRepository(mock_db)

        # Lines 172-186 executed: Create disabled config
        result = await repo.create_global_config(
            ConnectorType.NOTION, is_enabled=False, disabled_reason="Not implemented yet"
        )

        assert result.connector_type == ConnectorType.NOTION
        assert result.is_enabled is False
        assert result.disabled_reason == "Not implemented yet"

        mock_logger.info.assert_called_once_with(
            "connector_global_config_created",
            connector_type=ConnectorType.NOTION.value,
            is_enabled=False,
        )


class TestUpdateGlobalConfig:
    """Tests for update_global_config method."""

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_update_global_config_enable(self, mock_logger):
        """Test update_global_config enables config (Lines 188-220)."""
        mock_db = AsyncMock()

        config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            is_enabled=False,
            disabled_reason="Maintenance",
        )

        mock_result = AsyncMock()
        mock_result.scalar_one = MagicMock(return_value=config)
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        repo = ConnectorRepository(mock_db)

        # Lines 188-220 executed: Update global config (enable)
        result = await repo.update_global_config(
            ConnectorType.GOOGLE_CALENDAR, is_enabled=True, disabled_reason=None
        )

        assert result.is_enabled is True
        assert result.disabled_reason is None
        assert result == config

        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(config)

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "connector_global_config_updated",
            connector_type=ConnectorType.GOOGLE_CALENDAR.value,
            is_enabled=True,
        )

    @pytest.mark.asyncio
    @patch("src.domains.connectors.repository.logger")
    async def test_update_global_config_disable(self, mock_logger):
        """Test update_global_config disables config with reason (Lines 209-220)."""
        mock_db = AsyncMock()

        config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GITHUB,
            is_enabled=True,
            disabled_reason=None,
        )

        mock_result = AsyncMock()
        mock_result.scalar_one = MagicMock(return_value=config)
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        repo = ConnectorRepository(mock_db)

        # Lines 209-220 executed: Update global config (disable)
        result = await repo.update_global_config(
            ConnectorType.GITHUB, is_enabled=False, disabled_reason="Security audit"
        )

        assert result.is_enabled is False
        assert result.disabled_reason == "Security audit"

        mock_logger.info.assert_called_once_with(
            "connector_global_config_updated",
            connector_type=ConnectorType.GITHUB.value,
            is_enabled=False,
        )


class TestGetAllConnectorsByType:
    """Tests for get_all_connectors_by_type method."""

    @pytest.mark.asyncio
    async def test_get_all_connectors_by_type_no_filter(self):
        """Test get_all_connectors_by_type returns all (no status filter) (Lines 222-249)."""
        mock_db = AsyncMock()

        # Mock 2 connectors with user eager loaded
        connector1 = Connector(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="creds1",
            scopes=[],
        )
        connector2 = Connector(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ERROR,
            credentials_encrypted="creds2",
            scopes=[],
        )

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[connector1, connector2])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 239-249 executed: Query by type without status filter
        result = await repo.get_all_connectors_by_type(ConnectorType.GOOGLE_GMAIL)

        assert len(result) == 2
        assert connector1 in result
        assert connector2 in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_connectors_by_type_with_status_filter(self):
        """Test get_all_connectors_by_type with status filter (Lines 245-249)."""
        mock_db = AsyncMock()

        # Mock 1 active connector
        connector_active = Connector(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_DRIVE,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="creds_active",
            scopes=[],
        )

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[connector_active])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Lines 245-249 executed: Query by type with status filter
        result = await repo.get_all_connectors_by_type(
            ConnectorType.GOOGLE_DRIVE, status=ConnectorStatus.ACTIVE
        )

        assert len(result) == 1
        assert result[0].status == ConnectorStatus.ACTIVE
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_connectors_by_type_empty_list(self):
        """Test get_all_connectors_by_type returns empty list (Line 249)."""
        mock_db = AsyncMock()

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ConnectorRepository(mock_db)

        # Line 249 executed: Empty list returned
        result = await repo.get_all_connectors_by_type(ConnectorType.SLACK)

        assert result == []
        mock_db.execute.assert_called_once()
