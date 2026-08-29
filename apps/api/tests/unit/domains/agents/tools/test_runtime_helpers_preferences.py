"""Tests for get_user_preferences caching and locale mapping (audit wave 3, N-129).

Before this fix, get_user_preferences opened a DB session and issued a User
query on EVERY call (25+ tools, several calls per plan), and derived the
locale as ``f"{lang}-{lang.upper()}"`` which produced nonexistent locales
("en-EN", "zh-CN-ZH-CN").

Criteria: at most one User query per TTL window per user; valid BCP 47
locale for every supported language.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime

from src.core.config import settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.runtime_helpers import get_user_preferences
from src.domains.users.preferences_cache import UserPreferencesCache
from tests.helpers.runtime_context import make_tool_runtime

_USER_ID = uuid4()


def _make_runtime(user_id: UUID | None = None) -> ToolRuntime[LiaRuntimeContext, Any]:
    """The runtime the tool layer injects, carrying the acting user (ADR-231)."""
    return make_tool_runtime(user_id=user_id or _USER_ID)


def _make_user(timezone: str | None, language: str | None) -> MagicMock:
    user = MagicMock()
    user.timezone = timezone
    user.language = language
    return user


@asynccontextmanager
async def _fake_db_context():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clean_cache():
    """Each test starts and ends with an empty preferences cache."""
    UserPreferencesCache.clear()
    yield
    UserPreferencesCache.clear()


def _patch_user_service(user: MagicMock | None) -> tuple[object, object, AsyncMock]:
    """Build patches for the lazy imports inside get_user_preferences."""
    get_user_by_id = AsyncMock(return_value=user)
    user_service = MagicMock()
    user_service.get_user_by_id = get_user_by_id
    service_patch = patch(
        "src.domains.users.service.UserService",
        return_value=user_service,
    )
    db_patch = patch(
        "src.infrastructure.database.session.get_db_context",
        side_effect=lambda: _fake_db_context(),
    )
    return service_patch, db_patch, get_user_by_id


@pytest.mark.unit
class TestLocaleMapping:
    """Locale derived from the language must be a real BCP 47 locale."""

    @pytest.mark.parametrize(
        ("language", "expected_locale"),
        [
            ("fr", "fr-FR"),
            ("en", "en-US"),
            ("es", "es-ES"),
            ("de", "de-DE"),
            ("it", "it-IT"),
            ("zh-CN", "zh-CN"),
        ],
    )
    async def test_supported_language_maps_to_valid_locale(
        self, language: str, expected_locale: str
    ) -> None:
        service_patch, db_patch, _ = _patch_user_service(_make_user("Europe/Paris", language))
        with service_patch, db_patch:
            timezone, lang, locale = await get_user_preferences(_make_runtime())

        assert timezone == "Europe/Paris"
        assert lang == language
        assert locale == expected_locale

    async def test_missing_user_falls_back_to_defaults(self) -> None:
        service_patch, db_patch, _ = _patch_user_service(None)
        with service_patch, db_patch:
            timezone, lang, locale = await get_user_preferences(_make_runtime())

        assert timezone == "UTC"
        assert lang == settings.default_language
        assert locale == "fr-FR"


@pytest.mark.unit
class TestPreferencesCache:
    """User query issued at most once per TTL window per user."""

    async def test_second_call_hits_cache(self) -> None:
        service_patch, db_patch, get_user_by_id = _patch_user_service(
            _make_user("Europe/Paris", "en")
        )
        with service_patch, db_patch:
            first = await get_user_preferences(_make_runtime())
            second = await get_user_preferences(_make_runtime())

        assert first == second == ("Europe/Paris", "en", "en-US")
        assert get_user_by_id.await_count == 1

    async def test_cache_is_per_user(self) -> None:
        other_id = uuid4()
        service_patch, db_patch, get_user_by_id = _patch_user_service(
            _make_user("Europe/Paris", "en")
        )
        with service_patch, db_patch:
            await get_user_preferences(_make_runtime())
            await get_user_preferences(_make_runtime(other_id))

        assert get_user_by_id.await_count == 2

    async def test_invalidate_forces_refetch(self) -> None:
        service_patch, db_patch, get_user_by_id = _patch_user_service(
            _make_user("Europe/Paris", "en")
        )
        with service_patch, db_patch:
            await get_user_preferences(_make_runtime())
            UserPreferencesCache.invalidate(str(_USER_ID))
            await get_user_preferences(_make_runtime())

        assert get_user_by_id.await_count == 2

    async def test_missing_user_is_not_cached(self) -> None:
        """Defaults must not be pinned: a user created later is picked up."""
        service_patch, db_patch, get_user_by_id = _patch_user_service(None)
        with service_patch, db_patch:
            await get_user_preferences(_make_runtime())
            await get_user_preferences(_make_runtime())

        assert get_user_by_id.await_count == 2

    async def test_ttl_zero_disables_caching(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "user_preferences_cache_ttl_seconds", 0)
        service_patch, db_patch, get_user_by_id = _patch_user_service(
            _make_user("Europe/Paris", "en")
        )
        with service_patch, db_patch:
            await get_user_preferences(_make_runtime())
            await get_user_preferences(_make_runtime())

        assert get_user_by_id.await_count == 2
