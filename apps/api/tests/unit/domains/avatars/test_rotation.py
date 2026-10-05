"""Key rotation must not silently reset the selected face."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.unit


async def test_rotation_preserves_face_without_preserving_stale_verification(monkeypatch):
    now = datetime.now(UTC)
    face = str(uuid4())
    row = Connector(
        id=uuid4(),
        user_id=uuid4(),
        connector_type=ConnectorType.SIMLI,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="old",
        scopes=[],
        connector_metadata={"avatar_face_id": face, "functionally_verified": False},
        created_at=now,
        updated_at=now,
    )
    db = AsyncMock()
    service = ConnectorService(db)
    repository = AsyncMock(spec=ConnectorRepository)
    repository.get_global_config_by_type.return_value = None
    repository.get_by_user_and_type.return_value = row
    service.repository = repository
    monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())
    await service.activate_api_key_connector(
        row.user_id, ConnectorType.SIMLI, "test-only-credential", metadata={"rotated_at": "new"}
    )
    assert row.connector_metadata["avatar_face_id"] == face
    assert row.connector_metadata["functionally_verified"] is True
    assert row.connector_metadata["rotated_at"] == "new"
    assert row.credentials_encrypted != "old"
