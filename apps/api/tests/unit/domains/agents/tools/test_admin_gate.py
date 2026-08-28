"""Shared admin gate — single implementation of the superuser check for tools.

Fail-secure: missing user, DB error and non-superuser all resolve to False.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.agents.tools import admin_gate


def _db_returning(user: Any) -> Any:
    @asynccontextmanager
    async def fake_ctx() -> Any:
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        yield session

    return fake_ctx


@pytest.mark.unit
class TestUserIsSuperuser:
    async def test_superuser_is_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = MagicMock()
        user.is_superuser = True
        monkeypatch.setattr(admin_gate, "get_db_context", _db_returning(user))
        assert await admin_gate.user_is_superuser("8a7b6c5d-0000-0000-0000-000000000001") is True

    async def test_regular_user_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        user = MagicMock()
        user.is_superuser = False
        monkeypatch.setattr(admin_gate, "get_db_context", _db_returning(user))
        assert await admin_gate.user_is_superuser("8a7b6c5d-0000-0000-0000-000000000001") is False

    async def test_missing_user_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(admin_gate, "get_db_context", _db_returning(None))
        assert await admin_gate.user_is_superuser("8a7b6c5d-0000-0000-0000-000000000001") is False

    async def test_db_error_is_false_fail_secure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        @asynccontextmanager
        async def broken_ctx() -> Any:
            raise ConnectionError("db down")
            yield  # pragma: no cover

        monkeypatch.setattr(admin_gate, "get_db_context", broken_ctx)
        assert await admin_gate.user_is_superuser("8a7b6c5d-0000-0000-0000-000000000001") is False

    async def test_invalid_uuid_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(admin_gate, "get_db_context", _db_returning(None))
        assert await admin_gate.user_is_superuser("not-a-uuid") is False

    def test_devops_tools_delegate_to_the_shared_gate(self) -> None:
        """Factorisation proof: devops' patchable seam wraps the shared impl."""
        import inspect

        from src.domains.agents.tools import devops_tools

        assert "user_is_superuser" in inspect.getsource(devops_tools._check_user_is_admin)
