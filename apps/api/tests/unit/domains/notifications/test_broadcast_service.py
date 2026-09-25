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
    service.fcm_service = MagicMock()
    service.fcm_service.get_active_token_strings = AsyncMock(return_value=[])
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


def _sending_service(users_by_language: dict[str, list]) -> BroadcastService:
    """A service whose collaborators accept a send, recording what they were given."""
    service = _make_service()
    service.broadcast_repo.create_broadcast = AsyncMock(return_value=_make_broadcast())
    service.broadcast_repo.update_stats = AsyncMock()
    service.user_repo = MagicMock()
    service.user_repo.get_selected_users_grouped_by_language = AsyncMock(
        return_value=users_by_language
    )
    service.user_repo.get_active_users_grouped_by_language = AsyncMock(
        return_value=users_by_language
    )
    service._translate_to_languages = AsyncMock(return_value={})  # type: ignore[method-assign]
    service._broadcast_to_users_by_language = AsyncMock(  # type: ignore[method-assign]
        return_value=(0, 0)
    )
    return service


@pytest.mark.unit
class TestSendBroadcastRecordsTheAudience:
    """ADR-312: the row says who it was for — resolved BEFORE it is written."""

    async def test_targeted_send_persists_the_resolved_active_recipients(self) -> None:
        first, second = uuid4(), uuid4()
        service = _sending_service({"fr": [first], "en": [second]})

        result = await service.send_broadcast(
            message="Hello", admin_user_id=uuid4(), user_ids=[first, second, uuid4()]
        )

        kwargs = service.broadcast_repo.create_broadcast.await_args.kwargs
        # Only the accounts actually addressed (active ones) are recipients.
        assert sorted(kwargs["recipient_ids"]) == sorted([first, second])
        assert result.total_users == 2

    async def test_send_to_all_records_no_recipient(self) -> None:
        service = _sending_service({"fr": [uuid4()]})

        await service.send_broadcast(message="Hello", admin_user_id=uuid4())

        kwargs = service.broadcast_repo.create_broadcast.await_args.kwargs
        assert kwargs["recipient_ids"] is None
        service.user_repo.get_selected_users_grouped_by_language.assert_not_awaited()

    @pytest.mark.parametrize("user_ids", [[], [uuid4()]])
    async def test_a_selection_addressing_nobody_is_refused_before_any_write(
        self, user_ids: list
    ) -> None:
        """An empty list, or one whose accounts are all inactive, never becomes « all »."""
        from src.core.exceptions import ValidationError

        service = _sending_service({})

        with pytest.raises(ValidationError):
            await service.send_broadcast(message="Hello", admin_user_id=uuid4(), user_ids=user_ids)

        service.broadcast_repo.create_broadcast.assert_not_awaited()
        service._broadcast_to_users_by_language.assert_not_awaited()


_DATABASE_EVENTS = frozenset({"read", "write"})
_NETWORK_EVENTS = frozenset({"model", "publish", "push"})


def _logged(events: list[str], name: str, value: object = None) -> AsyncMock:
    """An awaitable collaborator that records, in order, that it was reached."""

    def _record(*_args: object, **_kwargs: object) -> object:
        events.append(name)
        return value

    return AsyncMock(side_effect=_record)


def _delivering_service(
    events: list[str], monkeypatch: pytest.MonkeyPatch, users: dict[str, list]
) -> BroadcastService:
    """A send that runs the REAL delivery, every database and network door logged."""
    service = _make_service()
    service.db.commit = _logged(events, "commit")
    service.user_repo = MagicMock()
    service.user_repo.get_active_users_grouped_by_language = _logged(events, "read", users)
    service.broadcast_repo.create_broadcast = _logged(events, "write", _make_broadcast())
    service.broadcast_repo.merge_translations = _logged(events, "write")
    service.broadcast_repo.update_stats = _logged(events, "write")
    service._translate_to_languages = _logged(  # type: ignore[method-assign]
        events, "model", {"en": "Hello everyone"}
    )
    service.fcm_service.get_active_token_strings = _logged(events, "read", ["t1", "t2"])
    service.fcm_service.send_multicast = _logged(events, "push", (2, 0))
    redis = MagicMock()
    redis.publish = _logged(events, "publish")
    monkeypatch.setattr(
        "src.domains.notifications.broadcast_service.get_redis_cache",
        AsyncMock(return_value=redis),
    )
    return service


@pytest.mark.unit
class TestDeliveryReadsTokensPerLanguageGroup:
    """One token query per language group — never one per recipient (N+1)."""

    async def test_tokens_are_fetched_once_per_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events: list[str] = []
        users = {"fr": [uuid4(), uuid4(), uuid4()], "en": [uuid4()]}
        service = _delivering_service(events, monkeypatch, users)

        result = await service.send_broadcast(message="Bonjour à tous", admin_user_id=uuid4())

        assert service.fcm_service.get_active_token_strings.await_count == 2
        assert events.count("publish") == 4  # SSE stays per recipient
        assert (result.fcm_sent, result.fcm_failed) == (4, 0)


@pytest.mark.unit
class TestNoTransactionIsHeldAcrossANetworkCall:
    """ADR-304: every read is committed before the model, Redis or FCM is reached.

    The delivery used to read a language group's device tokens between two
    pushes, so the request's transaction stayed open while FCM answered — one
    group after the other, for every group of an instance-wide broadcast.
    """

    async def test_no_network_call_runs_inside_an_open_transaction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []
        service = _delivering_service(events, monkeypatch, {"fr": [uuid4()], "en": [uuid4()]})

        await service.send_broadcast(message="Bonjour à tous", admin_user_id=uuid4())

        open_transaction = False
        for event in events:
            if event in _DATABASE_EVENTS:
                open_transaction = True
            elif event == "commit":
                open_transaction = False
            else:
                assert event in _NETWORK_EVENTS
                assert not open_transaction, f"a transaction spans a network call: {events}"
        # The model, one publish per recipient, one push per group — all reached.
        assert [e for e in events if e in _NETWORK_EVENTS] == [
            "model",
            "publish",
            "push",
            "publish",
            "push",
        ]
        assert not open_transaction, f"the send ends with its writes uncommitted: {events}"
