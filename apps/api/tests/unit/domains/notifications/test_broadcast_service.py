"""Tests for broadcast translation persistence (audit wave 3, N-213.2).

Before this fix, every read of a broadcast (login, tab focus) re-translated
the message with an LLM call. Translations are now persisted in the
``admin_broadcasts.message_translations`` JSONB column: filled at send time, lazily
backfilled for historical broadcasts, and short-circuited on read.

Criterion: 0 LLM calls when reading an already-translated broadcast.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.notifications.broadcast_service import BroadcastService


def _make_service() -> BroadcastService:
    service = BroadcastService(MagicMock())
    service.db.commit = AsyncMock()
    service.broadcast_repo = MagicMock()
    service.broadcast_repo.merge_translations = AsyncMock()
    return service


def _make_broadcast(
    message: str = "Bonjour à tous",
    translations: dict[str, str] | None = None,
) -> MagicMock:
    broadcast = MagicMock()
    broadcast.id = uuid4()
    broadcast.message = message
    broadcast.message_translations = translations
    broadcast.sender = None
    broadcast.created_at = datetime.now(UTC)
    return broadcast


@pytest.mark.unit
class TestToBroadcastInfoTranslationCache:
    """Read path must use persisted translations before calling the LLM."""

    async def test_cached_translation_short_circuits_llm(self) -> None:
        """0 LLM calls when the translation is already persisted."""
        service = _make_service()
        service._translate_to_languages = AsyncMock()  # type: ignore[method-assign]
        broadcast = _make_broadcast(translations={"en": "Hello everyone"})

        info = await service._to_broadcast_info(broadcast, "en")

        assert info.message == "Hello everyone"
        service._translate_to_languages.assert_not_awaited()

    async def test_source_language_never_translates(self) -> None:
        service = _make_service()
        service._translate_to_languages = AsyncMock()  # type: ignore[method-assign]
        broadcast = _make_broadcast()

        info = await service._to_broadcast_info(broadcast, "fr")

        assert info.message == "Bonjour à tous"
        service._translate_to_languages.assert_not_awaited()

    async def test_missing_translation_backfilled_and_persisted(self) -> None:
        """Historical broadcast: translate lazily, persist for next reads."""
        service = _make_service()
        service._translate_to_languages = AsyncMock(  # type: ignore[method-assign]
            return_value={"en": "Hello everyone"}
        )
        broadcast = _make_broadcast(translations=None)

        info = await service._to_broadcast_info(broadcast, "en")

        assert info.message == "Hello everyone"
        service._translate_to_languages.assert_awaited_once()
        service.broadcast_repo.merge_translations.assert_awaited_once_with(
            broadcast.id, {"en": "Hello everyone"}
        )
        service.db.commit.assert_awaited()

    async def test_failed_translation_is_not_persisted(self) -> None:
        """The original-message fallback must never be frozen as a translation."""
        service = _make_service()
        # _translate_to_languages falls back to the original message on error
        service._translate_to_languages = AsyncMock(  # type: ignore[method-assign]
            return_value={"en": "Bonjour à tous"}
        )
        broadcast = _make_broadcast(translations=None)

        info = await service._to_broadcast_info(broadcast, "en")

        assert info.message == "Bonjour à tous"
        service.broadcast_repo.merge_translations.assert_not_awaited()


@pytest.mark.unit
class TestSendBroadcastPersistsTranslations:
    """Send path fills the translations cache for all recipient languages."""

    async def test_translations_persisted_at_send_time(self) -> None:
        service = _make_service()
        broadcast = _make_broadcast()
        service.broadcast_repo.create_broadcast = AsyncMock(return_value=broadcast)
        service.broadcast_repo.update_stats = AsyncMock()
        service.user_repo = MagicMock()
        service.user_repo.get_active_users_grouped_by_language = AsyncMock(
            return_value={"fr": [uuid4()], "en": [uuid4()]}
        )
        service._translate_to_languages = AsyncMock(  # type: ignore[method-assign]
            return_value={"en": "Hello everyone"}
        )
        service._broadcast_to_users_by_language = AsyncMock(  # type: ignore[method-assign]
            return_value=(2, 0)
        )

        result = await service.send_broadcast(message="Bonjour à tous", admin_user_id=uuid4())

        assert result.success is True
        service.broadcast_repo.merge_translations.assert_awaited_once_with(
            broadcast.id, {"en": "Hello everyone"}
        )
        # SSE/FCM delivery still receives the source message for fr users
        delivery_kwargs = service._broadcast_to_users_by_language.await_args.kwargs
        assert delivery_kwargs["translations"]["fr"] == "Bonjour à tous"
        assert delivery_kwargs["translations"]["en"] == "Hello everyone"

    async def test_failed_translations_not_persisted_at_send_time(self) -> None:
        service = _make_service()
        broadcast = _make_broadcast()
        service.broadcast_repo.create_broadcast = AsyncMock(return_value=broadcast)
        service.broadcast_repo.update_stats = AsyncMock()
        service.user_repo = MagicMock()
        service.user_repo.get_active_users_grouped_by_language = AsyncMock(
            return_value={"fr": [uuid4()], "en": [uuid4()]}
        )
        # Translation failed → fallback to original message
        service._translate_to_languages = AsyncMock(  # type: ignore[method-assign]
            return_value={"en": "Bonjour à tous"}
        )
        service._broadcast_to_users_by_language = AsyncMock(  # type: ignore[method-assign]
            return_value=(2, 0)
        )

        await service.send_broadcast(message="Bonjour à tous", admin_user_id=uuid4())

        service.broadcast_repo.merge_translations.assert_not_awaited()
