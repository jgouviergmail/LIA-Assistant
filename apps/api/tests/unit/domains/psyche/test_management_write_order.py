"""A dirty state cannot flush its child lock before a compatible management owner fence."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.psyche.models import PsycheState
from src.domains.psyche.repository import PsycheStateRepository

pytestmark = pytest.mark.unit


async def test_update_takes_parent_key_share_before_flushing_dirty_state() -> None:
    db = AsyncMock()
    db.no_autoflush = MagicMock()
    db.scalar.side_effect = RuntimeError("owner fence")
    row = PsycheState(user_id=uuid4())
    with pytest.raises(RuntimeError, match="owner fence"):
        await PsycheStateRepository(db).update(row)
    db.flush.assert_not_awaited()
