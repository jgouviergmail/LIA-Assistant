"""The test session never opens the developer's live Redis databases.

``get_redis_cache`` / ``get_redis_session`` rebuild their URL from
``settings.redis_cache_db`` / ``settings.redis_session_db`` rather than from
the index carried by ``REDIS_URL`` — so pointing ``REDIS_URL`` at ``/15`` in
``tests/conftest.py`` isolated nothing (measured 2026-09-11: 2 639 test
``presence:last`` markers in the live cache). This pins the contract the
conftest now enforces: every client index resolves to the test database.
"""

from __future__ import annotations

import os

from src.core.config import settings

TEST_DB = 15


def test_redis_url_points_at_the_test_database() -> None:
    assert str(settings.redis_url).rstrip("/").endswith(f"/{TEST_DB}")


def test_cache_and_session_indices_follow_the_test_database() -> None:
    assert settings.redis_cache_db == TEST_DB
    assert settings.redis_session_db == TEST_DB
    assert os.environ["REDIS_CACHE_DB"] == str(TEST_DB)
    assert os.environ["REDIS_SESSION_DB"] == str(TEST_DB)
