"""A dead FCM token must be deactivated, not retried forever.

Firebase answers a permanently invalid token with ``messaging.UnregisteredError``,
whose message is the single word ``NotRegistered``. The service classified that
answer by searching the message for ``"unregistered"``::

    elif result.error and "unregistered" in result.error.lower():
        await self.repository.deactivate_token(...)

and ``"unregistered" not in "notregistered"`` — the substring needs a ``u``
before the ``n``. The branch never ran. Measured in production over 7 days
(2026-07-29 → 2026-08-05): 44 ``fcm_send_failed`` entries carrying
``error=NotRegistered``, all for the SAME token, retried for three days.

The fix classifies on the exception TYPE, which is the contract Firebase
actually publishes — the same doctrine the tool layer already applies with
``ToolErrorCode`` ("never by string-matching on exception messages").
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from firebase_admin import messaging

from src.domains.notifications.service import (
    FCMNotificationService,
    FCMSendResult,
    _is_permanently_invalid_token,
)

pytestmark = pytest.mark.unit


class TestPermanentInvalidityIsTyped:
    """The predicate reads Firebase's taxonomy, never its prose."""

    def test_unregistered_error_is_permanent(self) -> None:
        assert _is_permanently_invalid_token(messaging.UnregisteredError("NotRegistered"))

    def test_sender_id_mismatch_is_permanent(self) -> None:
        """The token belongs to another Firebase project: it will never work here."""
        assert _is_permanently_invalid_token(messaging.SenderIdMismatchError("SenderIdMismatch"))

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("connection reset"),
            TimeoutError("deadline exceeded"),
            messaging.QuotaExceededError("quota"),
            ValueError("boom"),
        ],
        ids=["connection", "timeout", "quota", "value"],
    )
    def test_transient_and_unrelated_failures_are_not_permanent(self, exc: Exception) -> None:
        """Deactivating on a transient failure would silently mute a live device."""
        assert not _is_permanently_invalid_token(exc)

    def test_the_string_oracle_that_used_to_be_used_would_miss_it(self) -> None:
        """Pins the exact defect, so nobody reintroduces the substring test."""
        message = str(messaging.UnregisteredError("NotRegistered"))

        assert "unregistered" not in message.lower(), (
            "the historical check `'unregistered' in error.lower()` is False for "
            "'NotRegistered' — that is precisely why dead tokens were retried forever."
        )
        assert _is_permanently_invalid_token(messaging.UnregisteredError(message))


def _service_with_repo() -> tuple[FCMNotificationService, MagicMock]:
    """A service whose repository is observable and whose DB is not touched."""
    service = FCMNotificationService.__new__(FCMNotificationService)
    repository = MagicMock()
    repository.deactivate_token = AsyncMock(return_value=True)
    repository.update_last_used = AsyncMock(return_value=True)
    repository.get_active_tokens_for_user = AsyncMock(return_value=[])
    service.repository = repository  # type: ignore[attr-defined]
    service._firebase_app = object()  # type: ignore[attr-defined]
    return service, repository


class TestSendResultCarriesTheVerdict:
    """``_send_to_token`` must publish the classification it already knows."""

    async def test_unregistered_send_marks_the_token_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, _ = _service_with_repo()

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise messaging.UnregisteredError("NotRegistered")

        monkeypatch.setattr(messaging, "send", _raise)

        result = await service._send_to_token(token="dead-token", title="t", body="b")

        assert result.success is False
        assert result.token_invalid is True

    async def test_transient_send_failure_does_not_mark_the_token_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, _ = _service_with_repo()

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise ConnectionError("connection reset by peer")

        monkeypatch.setattr(messaging, "send", _raise)

        result = await service._send_to_token(token="live-token", title="t", body="b")

        assert result.success is False
        assert result.token_invalid is False

    def test_default_is_valid(self) -> None:
        """A result built without the flag must never imply deactivation."""
        assert FCMSendResult(success=True).token_invalid is False


class TestDeadTokensAreDeactivated:
    """The batch path must act on the verdict, not on the message text."""

    async def test_a_dead_token_is_deactivated_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, repository = _service_with_repo()
        token_row = MagicMock(id=uuid4(), token="dead-token")
        repository.get_active_tokens_for_user = AsyncMock(return_value=[token_row])

        async def _send(**_kwargs: Any) -> FCMSendResult:
            return FCMSendResult(
                success=False, error="NotRegistered", token="dead-token", token_invalid=True
            )

        monkeypatch.setattr(service, "_send_to_token", _send)

        await service.send_to_user(user_id=uuid4(), title="t", body="b")

        repository.deactivate_token.assert_awaited_once()
        assert repository.deactivate_token.await_args.args[0] == "dead-token"

    async def test_a_transient_failure_keeps_the_token_active(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, repository = _service_with_repo()
        token_row = MagicMock(id=uuid4(), token="live-token")
        repository.get_active_tokens_for_user = AsyncMock(return_value=[token_row])

        async def _send(**_kwargs: Any) -> FCMSendResult:
            return FCMSendResult(
                success=False, error="connection reset", token="live-token", token_invalid=False
            )

        monkeypatch.setattr(service, "_send_to_token", _send)

        await service.send_to_user(user_id=uuid4(), title="t", body="b")

        repository.deactivate_token.assert_not_awaited()

    async def test_a_successful_send_refreshes_last_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, repository = _service_with_repo()
        token_row = MagicMock(id=uuid4(), token="live-token")
        repository.get_active_tokens_for_user = AsyncMock(return_value=[token_row])

        async def _send(**_kwargs: Any) -> FCMSendResult:
            return FCMSendResult(success=True, message_id="m1", token="live-token")

        monkeypatch.setattr(service, "_send_to_token", _send)

        await service.send_to_user(user_id=uuid4(), title="t", body="b")

        repository.update_last_used.assert_awaited_once()
        repository.deactivate_token.assert_not_awaited()


class TestBroadcastAlsoRetiresDeadTokens:
    """A broadcast met the same dead tokens and kept every one of them active.

    ``send_multicast`` only decided whether to LOG the failure; it never
    deactivated. A token the per-user path would have retired therefore survived
    here and was retried at every broadcast — the same token, forever, on a path
    nobody was watching because its log line was deliberately suppressed.
    """

    async def test_dead_tokens_are_deactivated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, repository = _service_with_repo()

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise messaging.UnregisteredError("NotRegistered")

        monkeypatch.setattr(messaging, "send", _raise)

        sent, failed = await service.send_multicast(
            tokens=["dead-1", "dead-2"], title="t", body="b"
        )

        assert (sent, failed) == (0, 2)
        assert repository.deactivate_token.await_count == 2
        assert {call.args[0] for call in repository.deactivate_token.await_args_list} == {
            "dead-1",
            "dead-2",
        }

    async def test_transient_failures_keep_tokens_active(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, repository = _service_with_repo()

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise ConnectionError("connection reset")

        monkeypatch.setattr(messaging, "send", _raise)

        sent, failed = await service.send_multicast(tokens=["live-1"], title="t", body="b")

        assert (sent, failed) == (0, 1)
        repository.deactivate_token.assert_not_awaited()

    async def test_a_failed_deactivation_does_not_break_the_broadcast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cleanup runs after delivery: it may report, never cancel what was sent."""
        service, repository = _service_with_repo()
        repository.deactivate_token = AsyncMock(side_effect=RuntimeError("db down"))

        calls = {"n": 0}

        def _send(*_args: Any, **_kwargs: Any) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return "message-id"
            raise messaging.UnregisteredError("NotRegistered")

        monkeypatch.setattr(messaging, "send", _send)

        sent, failed = await service.send_multicast(
            tokens=["live-1", "dead-1"], title="t", body="b"
        )

        assert (sent, failed) == (1, 1), "the successful delivery must still be reported"
