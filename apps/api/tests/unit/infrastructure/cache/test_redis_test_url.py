"""Disposable Redis overrides retain the mandatory test database boundary."""

import pytest

from tests.redis_test_url import validated_test_redis_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "redis://127.0.0.1:16379/15",
        "rediss://test-user:test-only@redis.example:6379/15",
        "redis://[::1]:16379/15",
    ],
)
def test_accepts_explicit_disposable_redis_endpoint(url: str) -> None:
    assert validated_test_redis_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:16379/15",
        "redis:///15",
        "redis://127.0.0.1:16379/0",
        "redis://127.0.0.1:16379/1",
        "redis://127.0.0.1:16379",
        "redis://test-user:test-only@127.0.0.1:16379/15?db=0",
        "redis://127.0.0.1:16379/15#fragment",
        "redis://127.0.0.1:not-a-port/15",
        "",
        "redis://127.0.0.1:16379/15/",
    ],
)
def test_rejects_invalid_endpoint_without_echoing_credentials(url: str) -> None:
    with pytest.raises(ValueError, match="TEST_REDIS_URL") as raised:
        validated_test_redis_url(url)
    assert "test-only" not in str(raised.value)
    if url:
        assert url not in str(raised.value)


def test_absent_override_keeps_the_default_endpoint() -> None:
    assert validated_test_redis_url(None) is None
