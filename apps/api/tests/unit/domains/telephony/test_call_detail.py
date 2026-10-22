"""A relation deep link reads exactly one owned call, including older history."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.telephony import router as routes


@pytest.mark.unit
async def test_call_detail_uses_owner_scoped_read_and_the_shared_projection(monkeypatch):
    owner, call_id = uuid4(), uuid4()
    row = SimpleNamespace(id=call_id)
    repo = SimpleNamespace(get_for_user=AsyncMock(return_value=row))
    monkeypatch.setattr(routes, "TelephonyRepository", lambda _db: repo)
    projected = SimpleNamespace(id=call_id, callee_display="Alice")
    project = AsyncMock(return_value=[projected])
    monkeypatch.setattr(routes, "project_call_history", project)

    result = await routes.get_call(call_id=call_id, user=SimpleNamespace(id=owner), db=None)

    assert result is projected
    repo.get_for_user.assert_awaited_once_with(owner, call_id)
    project.assert_awaited_once_with(None, owner, [row])


@pytest.mark.unit
async def test_foreign_or_missing_call_is_indistinguishable_and_never_projected(monkeypatch):
    repo = SimpleNamespace(get_for_user=AsyncMock(return_value=None))
    monkeypatch.setattr(routes, "TelephonyRepository", lambda _db: repo)
    project = AsyncMock()
    monkeypatch.setattr(routes, "project_call_history", project)

    with pytest.raises(ResourceNotFoundError):
        await routes.get_call(call_id=uuid4(), user=SimpleNamespace(id=uuid4()), db=None)

    project.assert_not_awaited()
