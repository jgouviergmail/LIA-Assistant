"""A session reader refuses malformed data without putting bearer cookies in logs."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload,valid",
    [
        (None, False),
        ("{broken", False),
        ("[]", False),
        ('{"user_id":"owner","created_at":"invalid"}', False),
        (json.dumps({"user_id": "owner", "created_at": datetime.now(UTC).isoformat()}), True),
    ],
    # Fixed ids: the valid payload carries the current time, and an id derived from it
    # differs between pytest-xdist workers, which then refuse the whole collection.
    ids=["absent", "broken_json", "wrong_shape", "invalid_created_at", "valid"],
)
async def test_session_read_never_logs_its_cookie_and_handles_invalid_shapes(
    payload: str | None,
    valid: bool,
) -> None:
    cookie = "SECRET-BEARER-COOKIE-DO-NOT-LOG"
    redis = AsyncMock()
    redis.get.return_value = payload
    logger = MagicMock()
    with patch("src.infrastructure.cache.session_store.logger", logger):
        result = await SessionStore(redis).get_session(cookie)
    assert cookie not in repr(logger.mock_calls)
    assert (result is not None) is valid
