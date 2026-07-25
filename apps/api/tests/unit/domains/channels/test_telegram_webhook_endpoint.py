"""The Telegram webhook endpoint: what it checks, and in which order (SEC-024).

``/channels/telegram/webhook`` is the only unauthenticated POST route in the
application — no session cookie, reachable by anyone who knows the public URL.
Two properties are asserted here that the handler's own unit tests cannot see,
because they are properties of the ENDPOINT rather than of the validator:

* the secret is verified before the request body is materialised;
* an ``update_id`` is claimed once, so a redelivered or replayed update is
  dropped instead of being processed a second time.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ForbiddenError
from src.domains.channels.router import _claim_telegram_update, telegram_webhook

SECRET = "s" * 40


def _request(signature: str, body: bytes = b'{"update_id": 1}') -> MagicMock:
    """Build a Request double whose body read is observable.

    Args:
        signature: Value served for the secret-token header.
        body: Bytes returned by ``await request.body()``.

    Returns:
        A mock exposing the two members the endpoint touches.
    """
    request = MagicMock()
    request.headers = {"X-Telegram-Bot-Api-Secret-Token": signature}
    request.body = AsyncMock(return_value=body)
    return request


@pytest.fixture
def configured_secret(monkeypatch: pytest.MonkeyPatch):
    """Configure a valid webhook secret on the settings the handler reads."""
    from src.core.config import settings as global_settings

    monkeypatch.setattr(global_settings, "telegram_webhook_secret", SECRET, raising=False)
    return SECRET


@pytest.fixture
def claimed(monkeypatch: pytest.MonkeyPatch):
    """Neutralise the dedup claim so ordering tests are not coupled to Redis."""
    claim = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.channels.router._claim_telegram_update", claim)
    return claim


def _closing_fire_and_forget() -> MagicMock:
    """A ``safe_fire_and_forget`` double that disposes of the coroutine it gets.

    A bare mock swallows the coroutine object without awaiting or closing it,
    which trips the suite's coroutine-leak guard with a RuntimeWarning at
    collection time. Closing it keeps the assertion (was it scheduled?) while
    leaving no un-awaited coroutine behind.
    """
    fire = MagicMock()
    fire.side_effect = lambda coro, name=None: coro.close()
    return fire


class TestTheSecretIsCheckedBeforeTheBodyIsRead:
    """An unauthenticated caller must not be able to make the API buffer bytes."""

    @pytest.mark.asyncio
    async def test_rejected_request_never_reads_the_body(self, configured_secret):
        """The ordering IS the fix — asserting the 403 alone would not show it.

        Telegram sends the shared secret verbatim in the header; it is not an
        HMAC over the payload, so nothing about the check needs the body. The
        endpoint used to read it first, letting anyone who found the URL make
        the API materialise a request before a single check ran.
        """
        request = _request(signature="wrong-secret")

        with pytest.raises(ForbiddenError):
            await telegram_webhook(request)

        request.body.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_header_is_rejected_without_reading_the_body(self, configured_secret):
        """No header at all is the commonest probe — same treatment."""
        request = _request(signature="")

        with pytest.raises(ForbiddenError):
            await telegram_webhook(request)

        request.body.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_accepted_request_does_read_the_body(self, configured_secret, claimed):
        """Counterpart: the legitimate path must still receive its payload."""
        request = _request(signature=SECRET)

        with patch(
            "src.domains.channels.router.safe_fire_and_forget", _closing_fire_and_forget()
        ) as fire:
            result = await telegram_webhook(request)

        assert result == {"ok": True}
        request.body.assert_awaited_once()
        fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_json_is_answered_without_scheduling_work(
        self, configured_secret, claimed
    ):
        """A valid secret with a broken payload must not reach the router."""
        request = _request(signature=SECRET, body=b"{not json")

        with patch("src.domains.channels.router.safe_fire_and_forget") as fire:
            result = await telegram_webhook(request)

        assert result == {"ok": False}
        fire.assert_not_called()

    @pytest.mark.parametrize(
        "body",
        [b"[]", b'"a string"', b"123", b"null", b"true"],
        ids=["list", "string", "number", "null", "bool"],
    )
    @pytest.mark.asyncio
    async def test_json_that_is_not_an_object_is_refused_cleanly(
        self, body, configured_secret, claimed
    ):
        """Valid JSON is not necessarily an object, and every read assumes one.

        `json.loads(b"[]")` returns a list; `payload.get(...)` on it raises
        AttributeError inside the request handler, which answers 500 — and a
        500 is precisely what makes Telegram redeliver the same payload
        forever. The endpoint must answer, not crash.
        """
        request = _request(signature=SECRET, body=body)

        with patch("src.domains.channels.router.safe_fire_and_forget") as fire:
            result = await telegram_webhook(request)

        assert result == {"ok": False}
        fire.assert_not_called()


class TestUpdateDeduplication:
    """The same update_id must be processed exactly once."""

    @pytest.mark.asyncio
    async def test_first_delivery_is_claimed(self):
        """A free key is claimed and the update proceeds."""
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)

        with patch(
            "src.infrastructure.cache.redis.get_redis_session", AsyncMock(return_value=redis)
        ):
            assert await _claim_telegram_update(4242) is True

        _key, _value = redis.set.await_args.args
        assert _key == "telegram_update:4242"
        assert redis.set.await_args.kwargs["nx"] is True
        assert redis.set.await_args.kwargs["ex"] > 0

    @pytest.mark.asyncio
    async def test_redelivery_is_refused(self):
        """`SET NX` returning falsy means someone already handled this update."""
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)

        with patch(
            "src.infrastructure.cache.redis.get_redis_session", AsyncMock(return_value=redis)
        ):
            assert await _claim_telegram_update(4242) is False

    @pytest.mark.asyncio
    async def test_a_duplicate_update_is_not_dispatched(self, configured_secret):
        """End-to-end: a refused claim answers ok and schedules nothing.

        Answering ok matters as much as skipping the work — a non-ok reply
        would keep Telegram redelivering the update it just told us about.
        """
        request = _request(signature=SECRET)
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=None)

        with (
            patch(
                "src.infrastructure.cache.redis.get_redis_session", AsyncMock(return_value=redis)
            ),
            patch("src.domains.channels.router.safe_fire_and_forget") as fire,
        ):
            result = await telegram_webhook(request)

        assert result == {"ok": True}
        fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_outage_fails_open(self):
        """A cache outage degrades duplicate protection, it does not kill the channel.

        Consistent with every other Redis dependency in this codebase. Failing
        closed here would make a Redis incident silently drop every inbound
        message, which is worse than the rare double answer it would prevent.
        """
        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            AsyncMock(side_effect=ConnectionError("redis down")),
        ):
            assert await _claim_telegram_update(4242) is True

    @pytest.mark.parametrize(
        "update_id",
        [None, "4242", 12.5, {"nested": 1}, ["list"], True],
        ids=["missing", "string", "float", "dict", "list", "bool"],
    )
    @pytest.mark.asyncio
    async def test_a_non_integer_update_id_builds_no_key(self, update_id):
        """The field is attacker-supplied — it must never reach a Redis key.

        ``True`` is in the table on purpose: ``isinstance(True, int)`` is True in
        Python, so a bare int check would happily build ``telegram_update:True``
        and collide with the claim for update 1.
        """
        redis = AsyncMock()

        with patch(
            "src.infrastructure.cache.redis.get_redis_session", AsyncMock(return_value=redis)
        ):
            assert await _claim_telegram_update(update_id) is True

        redis.set.assert_not_awaited()


class TestWeakSecretWarning:
    """A short secret is flagged at boot — and only flagged."""

    def test_a_short_secret_is_reported_without_its_value(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        """The length is actionable; the secret itself must never reach a log."""
        from src.core.config import settings as global_settings
        from src.infrastructure.startup.integrations import _warn_on_weak_telegram_webhook_secret

        monkeypatch.setattr(global_settings, "telegram_webhook_url", "https://x.test/hook")
        monkeypatch.setattr(global_settings, "telegram_webhook_secret", "hunter2")

        with patch("src.infrastructure.startup.integrations.logger") as logger:
            _warn_on_weak_telegram_webhook_secret()

        logger.warning.assert_called_once()
        kwargs = logger.warning.call_args.kwargs
        assert kwargs["length"] == len("hunter2")
        assert "hunter2" not in str(logger.warning.call_args)

    def test_a_strong_secret_says_nothing(self, monkeypatch: pytest.MonkeyPatch):
        """No warning on the recommended `openssl rand -hex 32` output."""
        from src.core.config import settings as global_settings
        from src.infrastructure.startup.integrations import _warn_on_weak_telegram_webhook_secret

        monkeypatch.setattr(global_settings, "telegram_webhook_url", "https://x.test/hook")
        monkeypatch.setattr(global_settings, "telegram_webhook_secret", "a" * 64)

        with patch("src.infrastructure.startup.integrations.logger") as logger:
            _warn_on_weak_telegram_webhook_secret()

        logger.warning.assert_not_called()

    def test_polling_mode_is_not_warned_about(self, monkeypatch: pytest.MonkeyPatch):
        """Without a webhook URL Telegram never calls the endpoint at all."""
        from src.core.config import settings as global_settings
        from src.infrastructure.startup.integrations import _warn_on_weak_telegram_webhook_secret

        monkeypatch.setattr(global_settings, "telegram_webhook_url", None)
        monkeypatch.setattr(global_settings, "telegram_webhook_secret", "short")

        with patch("src.infrastructure.startup.integrations.logger") as logger:
            _warn_on_weak_telegram_webhook_secret()

        logger.warning.assert_not_called()
