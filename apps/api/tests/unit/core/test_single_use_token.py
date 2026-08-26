"""Unit tests for ``core/single_use_token.py``.

The store exists because three flows had independently written the same
mechanism — an opaque token, a JSON payload in Redis, a short TTL and a
``GETDEL`` consumption. These tests pin the properties every caller depends on,
so the day a fourth flow adopts it nobody has to re-derive them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.core.single_use_token import SingleUseTokenStore

pytestmark = pytest.mark.unit


@dataclass(frozen=True, slots=True)
class _Payload:
    """Minimal typed payload used by the tests."""

    user_id: str
    flag: bool


def _store() -> SingleUseTokenStore[_Payload]:
    return SingleUseTokenStore(
        prefix="test:token:",
        decode=lambda raw: _Payload(user_id=raw["user_id"], flag=bool(raw.get("flag"))),
    )


class TestIssue:
    """Issuing a token."""

    async def test_returns_an_opaque_token_and_stores_the_payload_with_a_ttl(self) -> None:
        redis = AsyncMock()
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            token = await _store().issue({"user_id": "u-1", "flag": True}, ttl_seconds=60)

        assert token
        redis.set.assert_awaited_once()
        key, value = redis.set.await_args.args
        assert key == f"test:token:{token}"
        assert json.loads(value) == {"user_id": "u-1", "flag": True}
        assert redis.set.await_args.kwargs["ex"] == 60

    async def test_tokens_are_unpredictable_and_never_repeat(self) -> None:
        redis = AsyncMock()
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            tokens = {await _store().issue({"user_id": "u"}, ttl_seconds=60) for _ in range(50)}

        assert len(tokens) == 50
        # A guessable token is the whole attack: require real entropy, not a
        # counter that merely happens not to collide in 50 draws.
        assert all(len(token) >= 32 for token in tokens)

    async def test_refuses_a_non_positive_ttl(self) -> None:
        redis = AsyncMock()
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            with pytest.raises(ValueError):
                await _store().issue({"user_id": "u"}, ttl_seconds=0)

        redis.set.assert_not_awaited()


class TestConsume:
    """Consuming a token."""

    async def test_returns_the_decoded_payload(self) -> None:
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps({"user_id": "u-7", "flag": True})
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            payload = await _store().consume("tok")

        assert payload == _Payload(user_id="u-7", flag=True)
        redis.getdel.assert_awaited_once_with("test:token:tok")

    async def test_decodes_a_bytes_reply(self) -> None:
        """Redis clients answer bytes or str depending on configuration."""
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps({"user_id": "u-8", "flag": False}).encode()
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            payload = await _store().consume("tok")

        assert payload == _Payload(user_id="u-8", flag=False)

    async def test_returns_none_when_unknown_expired_or_replayed(self) -> None:
        redis = AsyncMock()
        redis.getdel.return_value = None
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            assert await _store().consume("tok") is None

    async def test_returns_none_on_a_corrupt_payload_instead_of_raising(self) -> None:
        """A malformed value must not surface as a 500 on an auth path."""
        redis = AsyncMock()
        redis.getdel.return_value = "{not json"
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            assert await _store().consume("tok") is None

    async def test_returns_none_when_the_payload_lacks_a_required_field(self) -> None:
        redis = AsyncMock()
        redis.getdel.return_value = json.dumps({"flag": True})
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            assert await _store().consume("tok") is None

    async def test_returns_none_for_an_empty_token_without_touching_redis(self) -> None:
        """An empty token must never build the bare prefix as a key."""
        redis = AsyncMock()
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            assert await _store().consume("") is None

        redis.getdel.assert_not_awaited()


class TestSingleUse:
    """The property the name promises."""

    async def test_consumption_uses_getdel_so_a_replay_finds_nothing(self) -> None:
        redis = AsyncMock()
        redis.getdel.side_effect = [json.dumps({"user_id": "u-1"}), None]
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            store = _store()
            first = await store.consume("tok")
            second = await store.consume("tok")

        assert first is not None
        assert second is None
        # GET-then-DELETE would leave a window where two concurrent callers both
        # succeed; GETDEL is atomic and is what makes "single use" true.
        assert redis.get.await_count == 0
